from __future__ import annotations

import importlib.metadata
import json
import math
import re
import secrets
import threading
import time
import traceback
import uuid
from dataclasses import asdict, replace

from .isolation import IsolatedPool, docker, probe
from .robot_contract import validate_manifest


class CompetitionQueue:
    def __init__(self, store, settings):
        self.store, self.settings = store, settings
        from .versioning import source_digest

        self.source_sha256 = source_digest()
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.deploying = threading.Event()
        self.thread = None
        self.node = {
            "ready": False,
            "environment": settings.environment,
            "message": "正在检测执行环境…",
            "gpu": False,
        }
        self.nodes = {}
        self.node_checked = 0.0

    def refresh(self):
        from .environments import runtime_settings

        nodes = {}
        for row in self.store.all("SELECT id FROM environments"):
            runtime = runtime_settings(self.store, self.settings, row["id"])
            node = probe(runtime)
            if node.get("ready"):
                key = "image:" + row["id"]
                with self.store.connect(write=True) as db:
                    db.execute(
                        "INSERT OR IGNORE INTO settings VALUES (?,?)", (key, node["image_id"])
                    )
                    pinned = db.execute(
                        "SELECT value FROM settings WHERE key=?", (key,)
                    ).fetchone()[0]
                if node["image_id"] != pinned:
                    node = {
                        **node,
                        "ready": False,
                        "message": "镜像摘要变化，请恢复已固定的运行环境",
                    }
            if node.get("ready"):
                self.store.execute(
                    "UPDATE environments SET image_id=?,status=? WHERE id=?",
                    (node["image_id"], node["message"], row["id"]),
                )
            nodes[row["id"]] = node
        self.nodes = nodes
        self.node = nodes.get(self.settings.environment, {"ready": False, "message": "环境未发布"})
        self.node_checked = time.monotonic()
        return self.node

    def start(self):
        with self.store.connect(write=True) as db:
            db.execute(
                "UPDATE jobs SET state='failed',message='多次重启中断，请管理员检查并重试',finished=? WHERE state IN ('preparing','running') AND attempts>=2",
                (time.time(),),
            )
            db.execute(
                "UPDATE jobs SET state='queued',message='服务恢复：使用原种子、版本和出生位置重跑',attempts=attempts+1,progress=0 WHERE state IN ('preparing','running') AND attempts<2"
            )
            db.execute("UPDATE submissions SET state='waiting_check' WHERE state='checking'")
        self.thread = threading.Thread(target=self.loop, name="arena-queue", daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        self.wake.set()
        if self.thread:
            self.thread.join(timeout=20)

    def loop(self):
        # Only reap containers labelled for this installation after acquiring
        # the server lock. Never affect unrelated containers on the machine.
        try:
            old = docker(
                [
                    "ps",
                    "-aq",
                    "--filter",
                    f"label=org.thuai10.mujoco.installation={self.store.setting('installation')}",
                ],
                timeout=10,
            )
            for container in old.stdout.split():
                if re.fullmatch(r"[0-9a-f]{12,64}", container):
                    docker(["rm", "-f", container], timeout=10)
        except Exception:
            pass
        while not self.stop.is_set():
            try:
                if time.monotonic() - self.node_checked > 15:
                    self.refresh()
                nodes = self.nodes
                if any(n.get("ready") for n in nodes.values()) and not self.deploying.is_set():
                    with self.store.connect(write=True) as db:
                        available = [key for key, node in nodes.items() if node.get("ready")]
                        placeholders = ",".join("?" for _ in available)
                        row = (
                            None
                            if self.deploying.is_set()
                            else db.execute(
                                "SELECT * FROM jobs WHERE state IN ('queued','waiting_node') AND environment IN ("
                                + placeholders
                                + ") ORDER BY CASE kind WHEN 'official' THEN 0 WHEN 'check' THEN 1 ELSE 2 END,created LIMIT 1",
                                available,
                            ).fetchone()
                        )
                        job = dict(row) if row else None
                        if not job:
                            for name, node in nodes.items():
                                if not node.get("ready"):
                                    db.execute(
                                        "UPDATE jobs SET state='waiting_node',message=? WHERE environment=? AND state='queued'",
                                        (node["message"], name),
                                    )
                        if job:
                            db.execute(
                                "UPDATE jobs SET state='preparing',message='准备隔离环境与机器人',started=?,image_id=? WHERE id=?",
                                (time.time(), nodes[job["environment"]]["image_id"], job["id"]),
                            )
                            if job["kind"] == "check":
                                db.execute(
                                    "UPDATE submissions SET state='checking' WHERE id=?",
                                    (job["submission_a"],),
                                )
                    if job:
                        self.run(job, nodes[job["environment"]]["image_id"])
                        continue
                else:
                    self.store.execute(
                        "UPDATE jobs SET state='waiting_node',message=? WHERE state='queued'",
                        (
                            "正在部署运行环境，就绪后自动继续"
                            if self.deploying.is_set()
                            else self.node["message"],
                        ),
                    )
            except Exception:
                # Server-side failures are private, and cannot silently launch a
                # trusted-process fallback. The queue remains usable afterwards.
                error = traceback.format_exc(limit=5)
                try:
                    with (self.settings.data / "worker-errors.log").open(
                        "a", encoding="utf-8"
                    ) as log:
                        log.write(error[-8000:] + "\n")
                except OSError:
                    pass
            self.wake.wait(2)
            self.wake.clear()

    def cancelled(self, job_id):
        row = self.store.one("SELECT state FROM jobs WHERE id=?", (job_id,))
        return self.stop.is_set() or not row or row["state"] == "cancelled"

    def run(self, job, image_id):
        from embodied_arena.config import MatchConfig
        from embodied_arena.display import composite
        from embodied_arena.engine import Arena

        arena = pool = None
        folder = self.settings.data / "jobs" / job["id"]
        import shutil

        from .environments import runtime_settings

        runtime = runtime_settings(
            self.store, self.settings, job.get("environment", self.settings.environment)
        )
        if folder.exists():
            if folder.resolve().parent != (
                self.settings.data / "jobs"
            ).resolve() or not re.fullmatch("[0-9a-f]{32}", job["id"]):
                raise ValueError("Invalid job directory")
            shutil.rmtree(folder)
        folder.mkdir(parents=True, exist_ok=True)
        diagnostics = {
            "players": [],
            "timeline": [],
            "phases": {"policy": 0.0, "physics": 0.0, "render": 0.0},
        }

        def save_diagnostics():
            if pool:
                import numpy as np

                diagnostics["players"] = [
                    {
                        "player": pid,
                        "transport": pool.agents[pid].transport,
                        "calls": len(values),
                        "mean_ms": round(float(np.mean(values)), 3) if values else 0,
                        "p95_ms": round(float(np.percentile(values, 95)), 3) if values else 0,
                        "max_ms": round(max(values), 3) if values else 0,
                    }
                    for pid, values in enumerate(pool.latencies)
                ]
            temp = folder / "diagnostics.tmp"
            temp.write_text(json.dumps(diagnostics), encoding="utf-8")
            temp.replace(folder / "diagnostics.json")

        start = time.monotonic()
        try:
            from .versioning import source_digest

            if source_digest() != self.source_sha256:
                raise RuntimeError("平台源代码或配置已更新，请重启服务后继续评测")
            config = replace(
                MatchConfig.load(),
                scene=job["scene"],
                duration=job["duration"],
                seed=job["seed"],
                spawn_swap=bool(job.get("spawn_swap", 0)),
                task_set=job.get("task_set", "legacy"),
                render_shadows=False,
            )
            arena = Arena(config, cameras=True)
            if self.cancelled(job["id"]):
                return
            public = asdict(config)
            public.pop("seed", None)
            submissions = [
                self.store.one("SELECT * FROM submissions WHERE id=?", (job[key],))
                for key in ("submission_a", "submission_b")
            ]
            orders = [
                validate_manifest(
                    json.loads(
                        (
                            self.settings.data / "submissions" / s["id"] / "submission.json"
                        ).read_text(encoding="utf-8-sig")
                    )
                )
                for s in submissions
            ]
            pool = IsolatedPool(
                [self.settings.data / "submissions" / s["id"] for s in submissions],
                image_id,
                runtime,
                self.store.setting("installation"),
                job["id"],
                public,
                [r.home for r in arena.robots],
                cancelled=lambda: self.cancelled(job["id"]),
                joint_orders=orders,
            )
            if job["kind"] == "check":
                for _ in range(3):
                    pool.act([arena.observation(p) for p in (0, 1)], strict=True)
                submission = submissions[0]
                reports = json.loads(submission["report"])
                reports[-1] = {
                    "name": "编译与隔离运行接口",
                    "state": "passed",
                    "detail": "包内全部 Python 文件编译成功；两个独立实例导入成功并连续 3 次返回有效动作；不代表策略能完成任务",
                }
                followup = None
                with self.store.connect(write=True) as db:
                    current = db.execute(
                        "SELECT state FROM jobs WHERE id=?", (job["id"],)
                    ).fetchone()
                    if current[0] == "cancelled":
                        return
                    if job.get("auto_practice"):
                        paused = (
                            db.execute(
                                "SELECT value FROM settings WHERE key='practice_paused'"
                            ).fetchone()[0]
                            == "1"
                        )
                        active = db.execute(
                            "SELECT active FROM users WHERE id=?", (submission["user_id"],)
                        ).fetchone()[0]
                        count = db.execute(
                            "SELECT count(*) FROM jobs WHERE user_id=? AND kind='practice' AND state IN ('queued','waiting_node','preparing','running')",
                            (submission["user_id"],),
                        ).fetchone()[0]
                        if active and not paused and count < 2:
                            followup = uuid.uuid4().hex
                            db.execute(
                                "INSERT INTO jobs (id,kind,user_id,submission_a,submission_b,state,message,duration,scene,seed,created) VALUES (?,'practice',?,?,?,'queued',?,?,?,?,?)",
                                (
                                    followup,
                                    submission["user_id"],
                                    submission["id"],
                                    submission["id"],
                                    "接口检查通过，已自动加入练习队列",
                                    self.settings.practice_duration,
                                    "cyber_city",
                                    secrets.randbelow(2**31),
                                    time.time(),
                                ),
                            )
                            db.execute(
                                "UPDATE jobs SET environment=?,task_set='mixed-v1' WHERE id=?",
                                (submission["environment"], followup),
                            )
                            reports[-1]["detail"] += "；已自动加入城市练习队列"
                        else:
                            reports[-1]["detail"] += (
                                "；自动练习暂未启动，请在队列恢复或空位后手动发起"
                            )
                    db.execute(
                        "UPDATE submissions SET state='ready',report=? WHERE id=?",
                        (json.dumps(reports, ensure_ascii=False), submission["id"]),
                    )
                    db.execute(
                        "UPDATE jobs SET state='completed',message='接口检查通过，可发起练习或报名',progress=1,finished=?,result=? WHERE id=?",
                        (
                            time.time(),
                            json.dumps(
                                {
                                    "checked_calls": 3,
                                    "image_id": image_id,
                                    "followup_job_id": followup,
                                    "compiled_all_python": True,
                                }
                            ),
                            job["id"],
                        ),
                    )
                return
            frames = []
            frame_folder = folder / "frames"
            frame_folder.mkdir(exist_ok=True)

            def capture():
                image = composite(arena)
                image.save(frame_folder / f"{len(frames):04d}.jpg", quality=82)
                frames.append(
                    {
                        "time": round(arena.time, 3),
                        "health": [p.health for p in arena.referee.players],
                        "scores": [p.score for p in arena.referee.players],
                    }
                )
                temp = folder / "replay.tmp"
                temp.write_text(json.dumps({"fps": 2, "frames": frames}), encoding="utf-8")
                temp.replace(folder / "replay.json")

            capture()
            self.store.update_job(job["id"], state="running", message="仿真运行中")
            last_capture = last_update = 0.0
            for _ in range(math.ceil(config.duration / config.control_dt)):
                if self.cancelled(job["id"]):
                    return
                if time.monotonic() - start > self.settings.wall_timeout:
                    raise TimeoutError(
                        f"本局超过实际运行时间上限 {self.settings.wall_timeout:g} 秒"
                    )
                tick = time.monotonic()
                observations = [arena.observation(p) for p in (0, 1)]
                diagnostics["phases"]["render"] += time.monotonic() - tick
                tick = time.monotonic()
                actions = pool.act(observations)
                diagnostics["phases"]["policy"] += time.monotonic() - tick
                for event in pool.events:
                    kind = event.pop("type")
                    arena.referee.event(arena.time, kind, **event)
                pool.events.clear()
                tick = time.monotonic()
                arena.step(actions)
                diagnostics["phases"]["physics"] += time.monotonic() - tick
                if arena.time - last_capture >= 0.5 - 1e-8:
                    tick = time.monotonic()
                    capture()
                    last_capture = arena.time
                    diagnostics["phases"]["render"] += time.monotonic() - tick
                if time.monotonic() - last_update >= 1:
                    last_update = time.monotonic()
                    diagnostics["timeline"].append(
                        {
                            "time": round(arena.time, 2),
                            **{
                                f"health_{pid}": p.health
                                for pid, p in enumerate(arena.referee.players)
                            },
                            **{
                                f"score_{pid}": p.score
                                for pid, p in enumerate(arena.referee.players)
                            },
                        }
                    )
                    diagnostics["timeline"][-1].update(
                        {
                            f"latency_{pid}": round(sum(v[-50:]) / len(v[-50:]), 3) if v else 0
                            for pid, v in enumerate(pool.latencies)
                        }
                    )
                    save_diagnostics()
                    self.store.update_job(
                        job["id"],
                        progress=min(1.0, arena.time / config.duration),
                        message=f"仿真 {arena.time:.1f} / {config.duration:g} 秒",
                    )
            if frames[-1]["time"] < arena.time - 1e-8:
                capture()
            result = arena.save(folder)
            if source_digest() != self.source_sha256:
                raise RuntimeError("评测过程中平台源代码或配置发生变化，请重试")
            reproduction = {
                "job_id": job["id"],
                "image_id": image_id,
                "environment": runtime.environment,
                "submissions": [
                    {"id": s["id"], "sha256": s["sha256"], "user_id": s["user_id"]}
                    for s in submissions
                ],
                "config": asdict(config),
                "wall_seconds": round(time.monotonic() - start, 2),
                "platform_version": importlib.metadata.version("embodied-arena"),
                "platform_source_sha256": self.source_sha256,
                "runner_limits": runtime.limits(),
                "wire_protocol": "bounded-json-array-cache-v2",
            }
            (folder / "reproduction.json").write_text(
                json.dumps(reproduction, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            for pid, metrics in enumerate(diagnostics["players"]):
                metrics["events"] = dict(
                    __import__("collections").Counter(
                        e["type"] for e in arena.referee.events if e.get("player") == pid
                    )
                )
            diagnostics["real_time_factor"] = round(
                config.duration / max(0.001, time.monotonic() - start), 3
            )
            result.pop("seed", None)
            result["wall_seconds"] = reproduction["wall_seconds"]
            self.store.update_job(
                job["id"],
                state="completed",
                message="成绩与回放已保存",
                progress=1.0,
                finished=time.time(),
                result=result,
            )
        except Exception as error:
            detail = str(error)[-4000:]
            from .operations import Operations

            try:
                Operations(self.store, self.settings).alert(
                    "job_failed", "场次 " + job["id"][:8] + " 运行失败，请查看管理员日志"
                )
            except Exception:
                pass
            (folder / "error.txt").write_text(
                traceback.format_exc(limit=8)[-16000:], encoding="utf-8"
            )
            self.store.update_job(job["id"], state="failed", message=detail, finished=time.time())
            if job["kind"] == "check":
                submission = self.store.one(
                    "SELECT report FROM submissions WHERE id=?", (job["submission_a"],)
                )
                reports = json.loads(submission["report"])
                reports[-1] = {"name": "编译与隔离运行接口", "state": "failed", "detail": detail}
                self.store.execute(
                    "UPDATE submissions SET state='check_failed',report=? WHERE id=?",
                    (json.dumps(reports, ensure_ascii=False), job["submission_a"]),
                )
        finally:
            save_diagnostics()
            if arena:
                diagnostics["event_counts"] = [
                    dict(
                        __import__("collections").Counter(
                            e["type"] for e in arena.referee.events if e.get("player") == pid
                        )
                    )
                    for pid in (0, 1)
                ]
                save_diagnostics()
            if pool:
                for pid, agent in enumerate(pool.agents):
                    (folder / f"player-{pid}.log").write_bytes(bytes(agent.logs))
                pool.close()
            if arena:
                arena.close()
