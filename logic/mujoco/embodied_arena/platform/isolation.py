from __future__ import annotations

import json
import queue
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path

from .protocol import MAX_MESSAGE, dumps, loads, validate_action
from .robot_contract import reorder


def docker_path():
    return shutil.which("docker") or str(
        Path("C:/Program Files/Docker/Docker/resources/bin/docker.exe")
    )


def docker(args, timeout=8):
    return subprocess.run(
        [docker_path(), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def probe(settings):
    base = {
        "ready": False,
        "environment": settings.environment,
        "image_id": None,
        "gpu": False,
        "libraries": {
            "python": "3.13",
            "numpy": "2.5.5",
            "Pillow": "13.0.0",
            "onnxruntime": "1.32.0",
        },
    }
    try:
        info = docker(["info", "--format", "{{.OSType}}"])
        if info.returncode or info.stdout.strip() != "linux":
            return {
                **base,
                "message": "Linux 执行引擎未就绪，请管理员启动 Docker Desktop 的 Linux 引擎。",
            }
        image = docker(["image", "inspect", settings.image])
        if image.returncode:
            return {
                **base,
                "message": "执行引擎已连接，尚未构建统一策略环境。请运行「配置运行环境」。",
            }
        details = json.loads(image.stdout)[0]
        label = (details.get("Config", {}).get("Labels") or {}).get(
            "org.thuai10.mujoco.environment"
        )
        if label != settings.environment:
            return {**base, "message": "策略镜像环境标识不匹配，停止执行。"}
        return {
            **base,
            "ready": True,
            "image_id": details["Id"],
            "gpu": settings.gpu,
            "message": ("GPU" if settings.gpu else "CPU")
            + " 隔离执行环境就绪，每名选手使用独立实例。",
        }
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError) as e:
        return {
            **base,
            "message": "执行节点未连接，上传与静态检查仍可使用。",
            "diagnostic": str(e)[:250],
        }


class Agent:
    def __init__(self, folder, image_id, settings, installation, job_id, player):
        self.name = "neon-" + installation[:10] + "-" + uuid.uuid4().hex[:16]
        self.responses = queue.Queue(maxsize=4)
        self.logs = bytearray()
        self.closed = False
        from .wirecache import ObservationCache

        self.cache = ObservationCache()
        self.transport = {"bytes": 0, "visual_cache_hits": 0, "task_cache_hits": 0}
        self.write_lock = threading.Lock()
        self.outgoing = queue.Queue(maxsize=1)
        args = [
            docker_path(),
            "run",
            "--rm",
            "-i",
            "--name",
            self.name,
            "--label",
            f"org.thuai10.mujoco.installation={installation}",
            "--label",
            f"org.thuai10.mujoco.job={job_id}",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--user",
            "65532:65532",
            "--pids-limit",
            str(settings.pids),
            "--cpus",
            str(settings.cpus),
            "--memory",
            f"{settings.memory_mb}m",
            "--memory-swap",
            f"{settings.memory_mb}m",
            "--ulimit",
            "nofile=64:64",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=128m,mode=1777",
            "--log-driver",
            "none",
            "--mount",
            f"type=bind,source={Path(folder).resolve()},target=/submission,readonly",
            "--env",
            "HOME=/tmp",
            "--env",
            "OMP_NUM_THREADS=1",
            "--env",
            "OPENBLAS_NUM_THREADS=1",
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            "--entrypoint",
            "python",
            image_id,
            "-I",
            "-B",
            "-c",
            Path(__file__)
            .with_name("preflight.py")
            .read_text(encoding="utf-8")
            .replace(
                'runpy.run_path("/runtime/agent.py", run_name="__main__")',
                "exec("
                + repr(Path(__file__).with_name("agent.py").read_text(encoding="utf-8"))
                + ", {'__name__':'__main__'})",
            ),
        ]
        if settings.gpu:
            args[2:2] = ["--gpus", "all", "--env", "ARENA_GPU=1"]
        self.process = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.stderr = threading.Thread(target=self._stderr, daemon=True)
        self.writer = threading.Thread(target=self._write, daemon=True)
        self.reader.start()
        self.stderr.start()
        self.writer.start()

    def _read(self):
        try:
            while not self.closed:
                raw = self.process.stdout.readline(MAX_MESSAGE + 1)
                if not raw:
                    raise RuntimeError("策略进程退出")
                response = loads(raw)
                if not isinstance(response, dict):
                    raise ValueError("策略消息必须是对象")
                self.responses.put_nowait(response)
        except Exception as e:
            try:
                self.responses.put_nowait({"error": str(e)[:500], "fatal": True})
            except queue.Full:
                pass

    def _stderr(self):
        while chunk := self.process.stderr.read(4096):
            self.logs.extend(chunk)
            if len(self.logs) > 32768:
                del self.logs[:-32768]

    def send(self, message):
        message, next_cache = self.cache.prepare(message)
        raw = dumps(message)
        try:
            self.outgoing.put_nowait(raw)
            self.cache.commit(next_cache)
            self.transport["bytes"] += len(raw)
            self.transport["visual_cache_hits"] += int(message.get("reuse_visual", False))
            self.transport["task_cache_hits"] += int(message.get("reuse_tasks", False))
            return True
        except queue.Full:
            return False

    def _write(self):
        # One bounded writer per agent: forged responses cannot create unbounded
        # blocked threads or queued observations on the trusted host.
        try:
            while not self.closed:
                try:
                    raw = self.outgoing.get(timeout=0.2)
                except queue.Empty:
                    continue
                self.process.stdin.write(raw)
                self.process.stdin.flush()
        except (OSError, ValueError):
            pass

    def receive(self, timeout):
        try:
            return self.responses.get(timeout=max(0.0, timeout))
        except queue.Empty:
            raise TimeoutError("策略响应超时") from None

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            docker(["rm", "-f", self.name], timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            pass
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait(timeout=5)
        self.reader.join(timeout=1)
        self.stderr.join(timeout=1)
        self.writer.join(timeout=1)
        for pipe in (self.process.stdin, self.process.stdout, self.process.stderr):
            try:
                pipe.close()
            except OSError:
                pass


class IsolatedPool:
    def __init__(
        self,
        folders,
        image_id,
        settings,
        installation,
        job_id,
        config,
        homes,
        cancelled=lambda: False,
        joint_orders=None,
    ):
        self.settings = settings
        self.agents = []
        self.pending = [None, None]
        self.last = [{"joint_targets": q.copy(), "fire": False} for q in homes]
        self.events = []
        self.latencies = [[], []]
        self.request_id = 0
        self.dead = [False, False]
        self.joint_orders = joint_orders or [None, None]
        try:
            for pid, folder in enumerate(folders):
                agent = Agent(folder, image_id, settings, installation, job_id, pid)
                self.agents.append(agent)
                agent.send({"op": "init", "id": 0, "player": pid, "config": config})
            deadline = time.monotonic() + settings.init_timeout
            for pid, agent in enumerate(self.agents):
                while True:
                    if cancelled():
                        raise RuntimeError("运行已取消")
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("策略初始化超时")
                    try:
                        response = agent.receive(min(0.25, remaining))
                        break
                    except TimeoutError:
                        continue
                if response.get("id") != 0 or response.get("ok") is not True:
                    raise RuntimeError(
                        f"选手 {pid + 1} 初始化失败：{response.get('error', '无效响应')}"
                    )
        except BaseException:
            self.close()
            raise

    def act(self, observations, strict=False):
        self.request_id += 1
        rid = self.request_id
        sent_at = time.monotonic()
        deadline = sent_at + self.settings.act_timeout
        result = [{"joint_targets": a["joint_targets"], "fire": False} for a in self.last]
        for pid, agent in enumerate(self.agents):
            if self.dead[pid]:
                continue
            try:
                while True:
                    response = agent.responses.get_nowait()
                    if response.get("fatal"):
                        raise RuntimeError(response.get("error", "策略退出"))
                    self.pending[pid] = None
            except queue.Empty:
                pass
            except Exception as e:
                self.dead[pid] = True
                self.events.append({"type": "policy_exit", "player": pid, "message": str(e)[:1500]})
                if strict:
                    raise
                continue
            if self.pending[pid] is None:
                if agent.send({"op": "act", "id": rid, "observation": observations[pid]}):
                    self.pending[pid] = rid
                else:
                    self.events.append(
                        {"type": "policy_timeout", "player": pid, "message": "策略输入阻塞"}
                    )
                    if strict:
                        raise TimeoutError("策略输入阻塞")
        for pid, agent in enumerate(self.agents):
            if self.dead[pid]:
                continue
            if self.pending[pid] != rid:
                self.events.append({"type": "policy_timeout", "player": pid})
                if strict:
                    raise TimeoutError("策略仍未完成上一周期")
                continue
            try:
                response = agent.receive(deadline - time.monotonic())
                if response.get("fatal"):
                    self.dead[pid] = True
                    raise RuntimeError(response.get("error", "策略退出"))
                self.pending[pid] = None
                if response.get("id") != rid:
                    raise ValueError("响应编号不匹配，已丢弃")
                if "error" in response:
                    raise ValueError(response["error"])
                result[pid] = validate_action(response.get("action"))
                result[pid]["joint_targets"] = reorder(
                    result[pid]["joint_targets"],
                    self.joint_orders[pid],
                    observations[pid]["proprio"]["joint_names"],
                )
                self.last[pid] = result[pid]
                self.latencies[pid].append((time.monotonic() - sent_at) * 1000)
            except Exception as e:
                self.events.append(
                    {
                        "type": "policy_timeout" if isinstance(e, TimeoutError) else "policy_error",
                        "player": pid,
                        "message": str(e)[:1500],
                    }
                )
                if strict:
                    raise
        return result

    def close(self):
        # Close independently; never let one failed cleanup skip the other.
        for agent in self.agents:
            try:
                agent.close()
            except (OSError, subprocess.TimeoutExpired):
                pass
