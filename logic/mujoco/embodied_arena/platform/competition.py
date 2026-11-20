"""Immutable tournament schedules, mirrored spawns and published aggregate standings."""

import itertools
import json
import secrets
import time
import uuid


def upgrade(store):
    with store.connect(write=True) as db:
        columns = {r[1] for r in db.execute("PRAGMA table_info(jobs)")}
        additions = {
            "tournament_id": "TEXT",
            "spawn_swap": "INTEGER NOT NULL DEFAULT 0",
            "attempts": "INTEGER NOT NULL DEFAULT 0",
            "artifacts_expired": "INTEGER NOT NULL DEFAULT 0",
            "environment": "TEXT NOT NULL DEFAULT 'arena-python-v1'",
            "task_set": "TEXT NOT NULL DEFAULT 'legacy'",
        }
        for name, kind in additions.items():
            if name not in columns:
                db.execute(f"ALTER TABLE jobs ADD COLUMN {name} {kind}")
        db.execute("""CREATE TABLE IF NOT EXISTS tournaments (
            id TEXT PRIMARY KEY,name TEXT NOT NULL,scene TEXT NOT NULL,rounds INTEGER NOT NULL,
            duration REAL NOT NULL,environment TEXT NOT NULL,created REAL NOT NULL,published INTEGER NOT NULL DEFAULT 0)""")
        db.execute("""CREATE TABLE IF NOT EXISTS tournament_entries (
            tournament_id TEXT NOT NULL REFERENCES tournaments(id),user_id TEXT NOT NULL REFERENCES users(id),
            submission_id TEXT NOT NULL REFERENCES submissions(id),PRIMARY KEY(tournament_id,user_id))""")


def schedule(store, owner, name, scene, duration, rounds, user_ids):
    if len(set(user_ids)) != len(user_ids) or not 2 <= len(user_ids) <= 16:
        raise ValueError("请选择 2–16 名不同选手")
    if len(user_ids) * (len(user_ids) - 1) * rounds > 512:
        raise ValueError("每轮赛程最多 512 场，请减少选手或重复次数")
    tournament_id = uuid.uuid4().hex
    now = time.time()
    with store.connect(write=True) as db:
        entries = []
        for user_id in user_ids:
            row = db.execute(
                "SELECT e.*,s.environment,s.state,u.active FROM entries e JOIN submissions s ON s.id=e.submission_id JOIN users u ON u.id=e.user_id WHERE e.user_id=?",
                (user_id,),
            ).fetchone()
            if not row or row["state"] != "ready" or not row["active"]:
                raise ValueError("选手必须启用、报名并通过检查")
            entries.append(dict(row))
        environment = entries[0]["environment"]
        if any(e["environment"] != environment for e in entries):
            raise ValueError("同一赛事必须使用相同环境")
        db.execute(
            "INSERT INTO tournaments VALUES (?,?,?,?,?,?,?,0)",
            (tournament_id, name, scene, rounds, duration, environment, now),
        )
        for entry in entries:
            db.execute(
                "INSERT INTO tournament_entries VALUES (?,?,?)",
                (tournament_id, entry["user_id"], entry["submission_id"]),
            )
        for _ in range(rounds):
            seed = secrets.randbelow(2**31)
            for a, b in itertools.combinations(entries, 2):
                for swap in (0, 1):
                    db.execute(
                        """INSERT INTO jobs (id,kind,user_id,submission_a,submission_b,state,message,duration,scene,seed,created,tournament_id,spawn_swap,environment,task_set)
                        VALUES (?,'official',?,?,?,'queued','公平评测：同布局、交换出生位置',?,?,?,?,?,?,?,?)""",
                        (
                            uuid.uuid4().hex,
                            owner,
                            a["submission_id"],
                            b["submission_id"],
                            duration,
                            scene,
                            seed,
                            now,
                            tournament_id,
                            swap,
                            environment,
                            "mixed-v1",
                        ),
                    )
    return tournament_id


def standings(store, tournament_id):
    entries = store.all(
        """SELECT e.user_id,u.username,s.revision FROM tournament_entries e JOIN users u ON u.id=e.user_id
        JOIN submissions s ON s.id=e.submission_id WHERE tournament_id=?""",
        (tournament_id,),
    )
    board = {
        e["user_id"]: {
            **e,
            "played": 0,
            "wins": 0,
            "draws": 0,
            "losses": 0,
            "points": 0,
            "task_score": 0.0,
            "score_difference": 0.0,
        }
        for e in entries
    }
    jobs = store.all(
        """SELECT j.*,a.user_id AS a_owner,b.user_id AS b_owner FROM jobs j
        JOIN submissions a ON a.id=j.submission_a JOIN submissions b ON b.id=j.submission_b WHERE tournament_id=?""",
        (tournament_id,),
    )
    completed = 0
    for job in jobs:
        if job["state"] != "completed" or not job["result"]:
            continue
        completed += 1
        scores = json.loads(job["result"])["scores"]
        for pid, owner in enumerate((job["a_owner"], job["b_owner"])):
            row = board[owner]
            row["played"] += 1
            row["task_score"] += scores[pid]
            row["score_difference"] += scores[pid] - scores[1 - pid]
            outcome = (
                "wins"
                if scores[pid] > scores[1 - pid]
                else "draws"
                if scores[pid] == scores[1 - pid]
                else "losses"
            )
            row[outcome] += 1
            row["points"] += 3 if outcome == "wins" else 1 if outcome == "draws" else 0
    rows = sorted(
        board.values(),
        key=lambda x: (-x["points"], -x["score_difference"], -x["task_score"], x["username"]),
    )
    previous = None
    for index, row in enumerate(rows):
        key = (row["points"], row["score_difference"], row["task_score"])
        row["rank"] = index + 1 if key != previous else rows[index - 1]["rank"]
        previous = key
    return {
        "rows": rows,
        "completed": completed,
        "total": len(jobs),
        "failed": sum(j["state"] == "failed" for j in jobs),
        "rule": "胜 3 分、平 1 分、负 0 分；依次比较积分、任务净分、任务总分；仍相同则并列",
    }
