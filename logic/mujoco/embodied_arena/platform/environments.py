"""Administrator-controlled runtime catalog. Never builds participant Dockerfiles."""

import json
import threading
import time
from dataclasses import replace

from embodied_arena.config import DOCKER_ROOT, ROOT

from .isolation import docker, probe

PROFILES = {
    "arena-python-v1": {
        "image": "thuai10-mujoco-policy:1",
        "gpu": False,
        "memory_mb": 1024,
        "dockerfile": "Dockerfile",
    },
    "arena-torch-cpu-v1": {
        "image": "thuai10-mujoco-torch-cpu:1",
        "gpu": False,
        "memory_mb": 2048,
        "dockerfile": "Dockerfile.torch",
    },
    "arena-cuda-v1": {
        "image": "thuai10-mujoco-cuda:1",
        "gpu": True,
        "memory_mb": 4096,
        "dockerfile": "Dockerfile.cuda",
    },
}


def initialize(store, settings):
    with store.connect(write=True) as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS environments (id TEXT PRIMARY KEY,image TEXT NOT NULL,image_id TEXT,gpu INTEGER NOT NULL,status TEXT NOT NULL,created REAL NOT NULL)"
        )
        db.execute(
            "INSERT OR IGNORE INTO environments VALUES (?,?,NULL,0,?,?)",
            (settings.environment, settings.image, "已注册，等待节点检测", time.time()),
        )
        db.execute(
            "UPDATE environments SET image_id=(SELECT value FROM settings WHERE key=?) WHERE id=? AND image_id IS NULL",
            ("image:" + settings.environment, settings.environment),
        )


def runtime_settings(store, settings, environment):
    row = store.one("SELECT * FROM environments WHERE id=?", (environment,))
    if not row:
        raise ValueError("该运行环境尚未由管理员发布")
    profile = PROFILES.get(environment, {})
    return replace(
        settings,
        environment=environment,
        image=row["image"],
        gpu=bool(row["gpu"]),
        memory_mb=profile.get("memory_mb", settings.memory_mb),
    )


class RuntimeCatalog:
    def __init__(self, store, settings):
        self.store, self.settings = store, settings
        self.lock = threading.Lock()
        self.building = None
        self.error = None
        self.thread = None

    def list(self):
        return {
            "published": self.store.all("SELECT * FROM environments ORDER BY created"),
            "profiles": [{"id": name, "gpu": p["gpu"]} for name, p in PROFILES.items()],
            "building": self.building,
            "error": self.error,
        }

    def publish(self, environment):
        if environment not in PROFILES:
            raise ValueError("只允许发布平台预定义的运行环境")
        if not self.lock.acquire(blocking=False):
            raise ValueError("已有环境正在准备")
        self.building = environment
        self.error = None
        controller = getattr(self, "controller", None)
        if controller:
            controller.deploying.set()
            with self.store.connect(write=True) as db:
                active = db.execute(
                    "SELECT count(*) FROM jobs WHERE state IN ('preparing','running')"
                ).fetchone()[0]
            if active:
                controller.deploying.clear()
                self.building = None
                self.lock.release()
                raise ValueError("场次已开始，请等待结束后准备环境")

        def build():
            try:
                profile = PROFILES[environment]
                pinned = self.store.one(
                    "SELECT image_id FROM environments WHERE id=?", (environment,)
                )
                if (pinned and pinned["image_id"]) or self.store.one(
                    "SELECT value FROM settings WHERE key=?", ("image:" + environment,)
                ):
                    raise ValueError("环境已固定，不能覆盖；恢复原镜像即可")
                if profile["gpu"]:
                    check = docker(
                        [
                            "run",
                            "--rm",
                            "--gpus",
                            "all",
                            "--network",
                            "none",
                            "--entrypoint",
                            "python",
                            self.settings.image,
                            "-c",
                            'import os; assert os.path.exists("/dev/nvidia0")',
                        ],
                        timeout=30,
                    )
                    if check.returncode:
                        raise RuntimeError("当前 Docker 节点没有可用 NVIDIA GPU；未发布 GPU 环境")
                existing = docker(["image", "inspect", profile["image"]])
                reuse = False
                if existing.returncode == 0:
                    details = json.loads(existing.stdout)[0]
                    reuse = (details.get("Config", {}).get("Labels") or {}).get(
                        "org.thuai10.mujoco.environment"
                    ) == environment
                if not reuse:
                    result = docker(
                        [
                            "build",
                            "-f",
                            str(DOCKER_ROOT / profile["dockerfile"]),
                            "-t",
                            profile["image"],
                            str(ROOT),
                        ],
                        timeout=1800,
                    )
                    if result.returncode:
                        raise RuntimeError(result.stderr[-2000:])
                check_settings = replace(
                    self.settings,
                    environment=environment,
                    image=profile["image"],
                    gpu=profile["gpu"],
                )
                node = probe(check_settings)
                if not node["ready"]:
                    raise RuntimeError(node["message"])
                code = "import torch,onnxruntime as ort,numpy; print(torch.__version__); " + (
                    'assert torch.cuda.is_available(); assert "CUDAExecutionProvider" in ort.get_available_providers(); print(torch.ones(1,device="cuda")+1)'
                    if profile["gpu"]
                    else "assert (torch.ones(1)+1).item()==2"
                )
                args = [
                    "run",
                    "--rm",
                    "--network",
                    "none",
                    "--read-only",
                    "--tmpfs",
                    "/tmp:rw,noexec,nosuid,size=128m",
                ]
                if profile["gpu"]:
                    args += ["--gpus", "all"]
                validation = docker(
                    [*args, "--entrypoint", "python", node["image_id"], "-c", code], timeout=120
                )
                if validation.returncode:
                    raise RuntimeError(validation.stderr[-2000:])
                with self.store.connect(write=True) as db:
                    db.execute(
                        "INSERT OR REPLACE INTO environments VALUES (?,?,?,?,?,?)",
                        (
                            environment,
                            profile["image"],
                            node["image_id"],
                            int(profile["gpu"]),
                            "实际推理自检通过",
                            time.time(),
                        ),
                    )
                    db.execute(
                        "INSERT OR IGNORE INTO settings VALUES (?,?)",
                        ("image:" + environment, node["image_id"]),
                    )
            except Exception as error:
                self.error = str(error)[-2000:]
            finally:
                self.building = None
                self.lock.release()
                if controller:
                    controller.deploying.clear()
                    controller.wake.set()

        self.thread = threading.Thread(target=build, name="runtime-publication", daemon=True)
        self.thread.start()
