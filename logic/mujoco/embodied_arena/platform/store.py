from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import time
from contextlib import contextmanager


def digest(value: str):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password: str, salt: str | None = None):
    salt = salt or secrets.token_hex(16)
    key = hashlib.scrypt(
        password.encode(), salt=salt.encode(), n=16384, r=8, p=1, maxmem=64 * 1024**2
    )
    return f"{salt}${key.hex()}"


def password_matches(password, stored):
    return secrets.compare_digest(password_hash(password, stored.split("$", 1)[0]), stored)


class Store:
    def __init__(self, folder):
        self.folder = folder
        folder.mkdir(parents=True, exist_ok=True)
        self.path = folder / "arena.sqlite3"
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL COLLATE NOCASE,
                    password TEXT NOT NULL, role TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), csrf TEXT NOT NULL, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS invites (
                    id TEXT PRIMARY KEY, token TEXT UNIQUE NOT NULL, hint TEXT NOT NULL,
                    expires REAL NOT NULL, remaining INTEGER NOT NULL, active INTEGER NOT NULL DEFAULT 1, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS submissions (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), revision INTEGER NOT NULL,
                    name TEXT NOT NULL, description TEXT NOT NULL, sha256 TEXT NOT NULL, bytes INTEGER NOT NULL,
                    expanded_bytes INTEGER NOT NULL DEFAULT 0,
                    environment TEXT NOT NULL, state TEXT NOT NULL, report TEXT NOT NULL, created REAL NOT NULL,
                    UNIQUE(user_id,revision));
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, user_id TEXT NOT NULL REFERENCES users(id),
                    submission_a TEXT NOT NULL REFERENCES submissions(id), submission_b TEXT NOT NULL REFERENCES submissions(id),
                    state TEXT NOT NULL, message TEXT NOT NULL, progress REAL NOT NULL DEFAULT 0,
                    duration REAL NOT NULL, scene TEXT NOT NULL, seed INTEGER NOT NULL,
                    image_id TEXT, result TEXT, published INTEGER NOT NULL DEFAULT 0,
                    created REAL NOT NULL, started REAL, finished REAL);
                CREATE TABLE IF NOT EXISTS entries (
                    user_id TEXT PRIMARY KEY REFERENCES users(id), submission_id TEXT NOT NULL REFERENCES submissions(id), created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS requests (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), text TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'pending', reply TEXT NOT NULL DEFAULT '', created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS jobs_state ON jobs(state,created);
                CREATE INDEX IF NOT EXISTS submissions_owner ON submissions(user_id,created);
            """)
            job_columns = {row[1] for row in db.execute("PRAGMA table_info(jobs)")}
            if "auto_practice" not in job_columns:
                db.execute("ALTER TABLE jobs ADD COLUMN auto_practice INTEGER NOT NULL DEFAULT 0")
            db.execute(
                "INSERT OR IGNORE INTO settings VALUES ('installation',?)", (secrets.token_hex(12),)
            )
            db.execute("INSERT OR IGNORE INTO settings VALUES ('practice_paused','0')")

    @contextmanager
    def connect(self, write=False):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def one(self, sql, params=()):
        with self.connect() as db:
            row = db.execute(sql, params).fetchone()
            return dict(row) if row else None

    def all(self, sql, params=()):
        with self.connect() as db:
            return [dict(row) for row in db.execute(sql, params).fetchall()]

    def execute(self, sql, params=()):
        with self.connect(write=True) as db:
            return db.execute(sql, params).rowcount

    def setting(self, key):
        return self.one("SELECT value FROM settings WHERE key=?", (key,))["value"]

    def session(self, user_id, seconds):
        token, csrf = secrets.token_urlsafe(40), secrets.token_urlsafe(32)
        with self.connect(write=True) as db:
            db.execute("DELETE FROM sessions WHERE expires<?", (time.time(),))
            db.execute(
                "INSERT INTO sessions VALUES (?,?,?,?)",
                (digest(token), user_id, csrf, time.time() + seconds),
            )
        return token, csrf

    def update_job(self, job_id, **values):
        allowed = {
            "state",
            "message",
            "progress",
            "image_id",
            "result",
            "started",
            "finished",
            "published",
        }
        if not values or not values.keys() <= allowed:
            raise ValueError("Invalid job update")
        if isinstance(values.get("result"), dict):
            values["result"] = json.dumps(values["result"], ensure_ascii=False)
        self.execute(
            "UPDATE jobs SET "
            + ",".join(f"{key}=?" for key in values)
            + " WHERE id=? AND state!='cancelled'",
            (*values.values(), job_id),
        )
