from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from pathlib import Path

from embodied_arena.config import ROOT


@dataclass(frozen=True)
class Settings:
    data: Path = ROOT / "var/platform"
    image: str = "thuai10-mujoco-policy:1"
    environment: str = "arena-python-v1"
    upload_bytes: int = 128 * 1024**2
    expanded_bytes: int = 512 * 1024**2
    user_bytes: int = 1024**3
    max_files: int = 2048
    max_versions: int = 100
    cpus: float = 1.0
    memory_mb: int = 1024
    pids: int = 64
    init_timeout: float = 90.0
    act_timeout: float = 1.0
    wall_timeout: float = 900.0
    session_seconds: int = 12 * 3600
    session_cookie: str = "thuai10_mujoco_session"
    practice_duration: float = 60.0
    workers: bool = True
    secure_cookie: bool = False
    gpu: bool = False
    available_environments: tuple[str, ...] = ("arena-python-v1",)
    retention_days: int = 30
    backup_keep: int = 7
    backup_interval: float = 86400.0

    @classmethod
    def from_env(cls):
        return cls(
            data=Path(os.environ.get("ARENA_DATA", ROOT / "var/platform")).resolve(),
            image=os.environ.get("ARENA_POLICY_IMAGE", "thuai10-mujoco-policy:1"),
            secure_cookie=os.environ.get("ARENA_HTTPS", "0") == "1",
        )

    def limits(self):
        return {
            "upload_mb": self.upload_bytes // 1024**2,
            "expanded_mb": self.expanded_bytes // 1024**2,
            "user_mb": self.user_bytes // 1024**2,
            "files": self.max_files,
            "versions": self.max_versions,
            "cpus": self.cpus,
            "memory_mb": self.memory_mb,
            "pids": self.pids,
            "init_seconds": self.init_timeout,
            "act_seconds": self.act_timeout,
            "wall_seconds": self.wall_timeout,
            "practice_seconds": self.practice_duration,
            "simultaneous_matches": 1,
        }


def allowed_hosts():
    hosts = {"localhost", "127.0.0.1", "[::1]", socket.gethostname().lower()}
    try:
        hosts.update(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass
    hosts.update(
        x.strip() for x in os.environ.get("ARENA_ALLOWED_HOSTS", "").split(",") if x.strip()
    )
    return sorted(hosts)
