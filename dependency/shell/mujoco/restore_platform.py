"""Restore a complete snapshot into a NEW data directory; never overwrite live data."""

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "logic/mujoco"
sys.path.insert(0, str(ROOT))


def restore(snapshot, destination):
    from embodied_arena.platform.packages import inspect_package
    from embodied_arena.platform.settings import Settings

    snapshot = Path(snapshot).resolve()
    destination = Path(destination).resolve()
    if not (snapshot / "COMPLETE").is_file():
        raise ValueError("快照未完成，拒绝恢复")
    if destination.exists():
        raise ValueError("恢复目标必须是全新目录，不会覆盖现有账号或比赛")
    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    for package in manifest["packages"]:
        if not __import__("re").fullmatch("[0-9a-f]{32}", package["id"]):
            raise ValueError("无效包路径")
        archive = snapshot / "uploads" / f"{package['id']}.zip"
        if hashlib.sha256(archive.read_bytes()).hexdigest() != package["sha256"]:
            raise ValueError("提交包校验失败")
    destination.mkdir(parents=True)
    shutil.copy2(snapshot / "arena.sqlite3", destination / "arena.sqlite3")
    with sqlite3.connect(destination / "arena.sqlite3") as db:
        environments = tuple(row[0] for row in db.execute("SELECT id FROM environments"))
        statuses = dict(db.execute("SELECT id,state FROM submissions"))
        db.execute("DELETE FROM sessions")
        db.execute("UPDATE settings SET value=? WHERE key='installation'", (uuid.uuid4().hex,))
        db.execute(
            "UPDATE jobs SET artifacts_expired=1 WHERE state IN ('completed','failed','cancelled')"
        )
    (destination / "uploads").mkdir()
    for package in manifest["packages"]:
        identifier = package["id"]
        archive = snapshot / "uploads" / f"{identifier}.zip"
        shutil.copy2(archive, destination / "uploads" / archive.name)
        if statuses[identifier] != "static_failed":
            inspect_package(
                archive,
                destination / "submissions" / identifier,
                Settings(data=destination, available_environments=environments),
            )
    return {
        "data": str(destination),
        "submissions": len(manifest["packages"]),
        "sessions_revoked": True,
        "replays_restored": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(json.dumps(restore(args.snapshot, args.destination), ensure_ascii=False))
