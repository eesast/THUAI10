"""Prepare only the platform's trusted assets and fixed policy runtime."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import asdict, replace
from pathlib import Path

from embodied_arena.config import DOCKER_ROOT, ROOT, SCRIPTS_ROOT

from .isolation import docker, docker_path, probe


class DeploymentManager:
    def __init__(self, store, settings, controller=None):
        self.store, self.settings, self.controller = store, settings, controller
        self.lock = threading.RLock()
        self.thread = None
        self.process = None
        self.state = {
            "state": "idle",
            "stage": "尚未部署",
            "progress": 0,
            "logs": [],
            "started": None,
            "finished": None,
        }
        saved = settings.data / "deployment.json"
        if saved.is_file():
            try:
                previous = json.loads(saved.read_text(encoding="utf-8"))
                if previous.get("state") in ("completed", "failed"):
                    self.state = previous
            except (OSError, ValueError):
                pass

    def snapshot(self):
        with self.lock:
            return {**self.state, "logs": list(self.state["logs"])}

    def update(self, **values):
        with self.lock:
            self.state.update(values)
            temporary = self.settings.data / "deployment.tmp"
            temporary.write_text(json.dumps(self.state, ensure_ascii=False), encoding="utf-8")
            temporary.replace(self.settings.data / "deployment.json")

    def log(self, text):
        with self.lock:
            self.state["logs"].append(str(text).strip()[-2000:])
            self.state["logs"] = self.state["logs"][-120:]

    def start(self):
        with self.lock:
            if self.state["state"] == "running":
                return False
            if self.controller:
                self.controller.deploying.set()
            if self.store.one(
                "SELECT count(*) AS n FROM jobs WHERE state IN ('preparing','running')"
            )["n"]:
                if self.controller:
                    self.controller.deploying.clear()
                return False
            self.update(
                state="running",
                stage="检查机器人与仿真资源",
                progress=5,
                logs=[],
                started=time.time(),
                finished=None,
            )
            self.thread = threading.Thread(target=self.run, name="arena-deploy", daemon=True)
            self.thread.start()
            return True

    def command(self, args, timeout=600):
        self.process = subprocess.Popen(
            args,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        process = self.process

        def read():
            while line := process.stdout.readline(4096):
                self.log(line)

        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        try:
            code = process.wait(timeout=timeout)
            reader.join(timeout=2)
            if code:
                raise RuntimeError("部署命令失败，请查看下方日志；没有执行任何选手安装脚本。")
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
            raise RuntimeError("部署超时，请检查官方资源下载连接后重试。") from None
        finally:
            self.process = None
            if process.poll() is not None:
                reader.join(timeout=1)
                process.stdout.close()

    def ensure_engine(self):
        info = docker(["info", "--format", "{{.OSType}}"], timeout=8)
        if not info.returncode and info.stdout.strip() == "linux":
            return
        desktop = Path("C:/Program Files/Docker/Docker/Docker Desktop.exe")
        if os.name != "nt" or not desktop.is_file():
            raise RuntimeError("请先安装并启动 Docker 的 Linux 引擎，再点击部署。")
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = subprocess.SW_HIDE
        subprocess.Popen(
            [str(desktop)],
            startupinfo=startup,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.log("正在启动已安装的 Docker Desktop Linux 引擎。")
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            try:
                info = docker(["info", "--format", "{{.OSType}}"], timeout=5)
                if not info.returncode and info.stdout.strip() == "linux":
                    return
            except subprocess.TimeoutExpired:
                pass
            time.sleep(2)
        raise RuntimeError("Linux 引擎启动超时，请查看 Docker Desktop 的启动提示后重试。")

    def ensure_image(self):
        pinned = self.store.one(
            "SELECT value FROM settings WHERE key=?", ("image:" + self.settings.environment,)
        )
        if pinned:
            original = docker(["image", "inspect", pinned["value"]])
            if original.returncode:
                raise RuntimeError(
                    "已使用的环境镜像丢失。请先恢复原镜像摘要，不能用新镜像覆盖历史环境。"
                )
            tagged = docker(["image", "inspect", self.settings.image])
            if tagged.returncode or json.loads(tagged.stdout)[0]["Id"] != pinned["value"]:
                result = docker(["image", "tag", pinned["value"], self.settings.image])
                if result.returncode:
                    raise RuntimeError("恢复原环境镜像标记失败。")
            self.log("复用已固定摘要的运行环境。")
            return
        current = docker(["image", "inspect", self.settings.image])
        if current.returncode:
            self.command(
                [
                    docker_path(),
                    "build",
                    "--file",
                    str(DOCKER_ROOT / "Dockerfile"),
                    "--tag",
                    self.settings.image,
                    ".",
                ],
                timeout=900,
            )
        else:
            self.log("统一环境已经存在，跳过重复构建。")

    def run(self):
        try:
            python = Path(sys.executable)
            if python.name.lower() == "pythonw.exe":
                python = python.with_name("python.exe")
            self.command([str(python), str(SCRIPTS_ROOT / "fetch_assets.py")], timeout=600)
            self.update(stage="连接 Linux 执行引擎", progress=30)
            self.ensure_engine()
            self.update(stage="准备统一运行环境", progress=55)
            self.ensure_image()
            self.update(stage="验证运行环境", progress=90)
            node = self.controller.refresh() if self.controller else probe(self.settings)
            if not node.get("ready"):
                raise RuntimeError(node["message"])
            # Verify the actual framework imports under the same unprivileged,
            # offline constraints used for contestants, before reporting ready.
            self.command(
                [
                    docker_path(),
                    "run",
                    "--rm",
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
                    "64",
                    "--memory",
                    "512m",
                    "--cpus",
                    "1",
                    "--entrypoint",
                    "python",
                    node["image_id"],
                    "-I",
                    "-B",
                    "-c",
                    "import numpy,PIL,onnxruntime;print('Runtime imports OK')",
                ],
                timeout=90,
            )
            self.update(stage="验证 MuJoCo、RGB-D 与策略通信", progress=95)
            self.simulation_check(node["image_id"])
            if self.controller:
                self.controller.wake.set()
            self.update(
                state="completed",
                stage="部署完成，上传检查与仿真队列可以运行",
                progress=100,
                finished=time.time(),
                image_id=node["image_id"],
            )
        except Exception as error:
            self.log(str(error))
            self.update(state="failed", stage=str(error)[:1000], finished=time.time())
        finally:
            if self.controller:
                self.controller.deploying.clear()
                self.controller.wake.set()

    def simulation_check(self, image_id):
        import numpy as np

        from embodied_arena.config import MatchConfig
        from embodied_arena.engine import Arena

        from .isolation import IsolatedPool
        from .packages import inspect_package, template_zip

        base = self.settings.data / "deployment-smoke"
        base.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="check-", dir=base) as temporary:
            work = Path(temporary).resolve()
            if not work.is_relative_to(base.resolve()):
                raise RuntimeError("自检目录不在预期位置")
            archive = work / "template.zip"
            archive.write_bytes(template_zip(self.settings.environment))
            inspect_package(archive, work / "submission", self.settings)
            config = replace(MatchConfig.load(), scene="room", duration=0.06, width=64, height=48)
            arena = Arena(config, cameras=True)
            pool = None
            try:
                public = asdict(config)
                public.pop("seed", None)
                pool = IsolatedPool(
                    [work / "submission"] * 2,
                    image_id,
                    self.settings,
                    self.store.setting("installation"),
                    "deployment-check",
                    public,
                    [r.home for r in arena.robots],
                )
                for _ in range(3):
                    observations = [arena.observation(pid) for pid in (0, 1)]
                    arena.step(pool.act(observations, strict=True))
                if not np.isfinite(arena.data.qpos).all():
                    raise RuntimeError("机器人仿真状态异常")
                self.log(
                    "MuJoCo / 双 RGB-D / 29 关节 / 两个策略容器通信自检通过；自检不计入比赛成绩。"
                )
            finally:
                if pool:
                    pool.close()
                arena.close()

    def close(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()


def main():
    from .settings import Settings
    from .store import Store

    parser = argparse.ArgumentParser(description="Prepare fixed THUAI10 MuJoCo runtime and assets")
    parser.parse_args()
    settings = Settings.from_env()
    manager = DeploymentManager(Store(settings.data), settings)
    manager.update(state="running", started=time.time(), logs=[], stage="准备部署", progress=0)
    manager.run()
    status = manager.snapshot()
    for line in status["logs"]:
        print(line)
    print(status["stage"])
    raise SystemExit(0 if status["state"] == "completed" else 1)


if __name__ == "__main__":
    main()
