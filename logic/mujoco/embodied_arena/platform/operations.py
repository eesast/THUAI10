"""Local maintenance with scoped retention, automatic snapshots and durable alerts."""

import json
import re
import shutil
import sqlite3
import threading
import time
import uuid


class Operations:
    def __init__(self, store, settings):
        self.store, self.settings = store, settings
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.thread = None
        with store.connect(write=True) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS alerts (id TEXT PRIMARY KEY,kind TEXT,message TEXT,created REAL,resolved INTEGER DEFAULT 0)"
            )

    def alert(self, kind, message):
        with self.store.connect(write=True) as db:
            old = db.execute(
                "SELECT id FROM alerts WHERE kind=? AND message=? AND resolved=0", (kind, message)
            ).fetchone()
            if not old:
                db.execute(
                    "INSERT INTO alerts VALUES (?,?,?,?,0)",
                    (uuid.uuid4().hex, kind, message[:1000], time.time()),
                )
            db.execute(
                "DELETE FROM alerts WHERE id NOT IN (SELECT id FROM alerts ORDER BY created DESC LIMIT 1000)"
            )

    def backup(self):
        with self.lock:
            root = (self.settings.data / "backups").resolve()
            root.mkdir(exist_ok=True)
            target = root / (time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
            target.mkdir()
            (target / "IN_PROGRESS").write_text(str(time.time()), encoding="utf-8")
            # Hold a write reservation while copying immutable upload archives so
            # the database and snapshot package set represent one committed state.
            with self.store.connect(write=True) as db:
                packages = [dict(r) for r in db.execute("SELECT id,sha256 FROM submissions")]
                with (
                    sqlite3.connect(self.store.path) as source,
                    sqlite3.connect(target / "arena.sqlite3") as dest,
                ):
                    source.backup(dest)
            (target / "uploads").mkdir()
            for package in packages:
                source = self.settings.data / "uploads" / f"{package['id']}.zip"
                if source.exists():
                    shutil.copy2(source, target / "uploads" / source.name)
                else:
                    raise RuntimeError("备份缺少提交原包，快照不可用于恢复")
            (target / "manifest.json").write_text(
                json.dumps(
                    {
                        "created": time.time(),
                        "packages": packages,
                        "includes": "database and original ZIPs; replay files remain in live data",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (target / "COMPLETE").write_text("verified snapshot\n", encoding="utf-8")
            (target / "IN_PROGRESS").unlink(missing_ok=True)
            self.store.execute(
                "INSERT OR REPLACE INTO settings VALUES ('last_backup',?)", (str(time.time()),)
            )
            return target.name

    def maintain(self):
        now = time.time()
        removed = 0
        cutoff = now - self.settings.retention_days * 86400
        for job in self.store.all(
            "SELECT id FROM jobs WHERE kind='practice' AND state IN ('completed','failed','cancelled') AND finished<? AND artifacts_expired=0",
            (cutoff,),
        ):
            base = (self.settings.data / "jobs").resolve()
            folder = (base / job["id"]).resolve()
            if (
                folder.parent != base
                or len(job["id"]) != 32
                or any(c not in "0123456789abcdef" for c in job["id"])
            ):
                raise RuntimeError("拒绝清理非平台任务路径")
            if folder.exists():
                shutil.rmtree(folder)
            self.store.execute("UPDATE jobs SET artifacts_expired=1 WHERE id=?", (job["id"],))
            removed += 1
        base = (self.settings.data / "backups").resolve()
        if base.exists():
            complete = sorted(
                (
                    p
                    for p in base.iterdir()
                    if p.is_dir()
                    and re.fullmatch(r"\d{8}-\d{6}-[a-f0-9]{8}", p.name)
                    and (p / "COMPLETE").exists()
                ),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            for folder in complete[self.settings.backup_keep :]:
                if folder.resolve().parent != base:
                    raise RuntimeError("备份目录越界")
                shutil.rmtree(folder)
        self.store.execute("DELETE FROM sessions WHERE expires<?", (now,))
        if shutil.disk_usage(self.settings.data).free < 2 * 1024**3:
            self.alert("disk", "可用磁盘不足 2 GB，请清理或扩容")
        return {"expired_practices": removed}

    def snapshot(self):
        last = self.store.one("SELECT value FROM settings WHERE key='last_backup'")
        return {
            "last_backup": float(last["value"]) if last else None,
            "backup_keep": self.settings.backup_keep,
            "practice_retention_days": self.settings.retention_days,
            "free_gb": round(shutil.disk_usage(self.settings.data).free / 1024**3, 2),
            "alerts": self.store.all(
                "SELECT * FROM alerts WHERE resolved=0 ORDER BY created DESC LIMIT 50"
            ),
        }

    def start(self):
        def run():
            while not self.stop.is_set():
                try:
                    last = self.store.one("SELECT value FROM settings WHERE key='last_backup'")
                    if (
                        not last
                        or time.time() - float(last["value"]) > self.settings.backup_interval
                    ):
                        self.backup()
                    self.maintain()
                except Exception as error:
                    self.alert("maintenance", str(error))
                self.stop.wait(60)

        self.thread = threading.Thread(target=run, name="arena-maintenance", daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=20)
