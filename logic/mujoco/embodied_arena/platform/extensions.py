"""Competition, debugging and operations endpoints using the portal's existing permissions."""

import json
from typing import Literal

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from .competition import schedule, standings


class TournamentInput(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    users: list[str] = Field(min_length=2, max_length=16)
    rounds: int = Field(default=2, ge=1, le=5)
    duration: float = Field(default=60, ge=1, le=120)
    scene: Literal["room", "cyber_city"] = "cyber_city"


class EnvironmentInput(BaseModel):
    environment: str


def install(
    app, store, settings, controller, ops, catalog, actor, administrator, job_for, public_job
):
    @app.get("/api/tournaments")
    def tournaments(user=Depends(actor)):
        rows = store.all(
            "SELECT * FROM tournaments"
            + ("" if user["role"] == "admin" else " WHERE published=1")
            + " ORDER BY created DESC"
        )
        return [{**row, "standings": standings(store, row["id"])} for row in rows]

    @app.post("/api/admin/tournaments")
    def create(body: TournamentInput, user=Depends(administrator)):
        try:
            identifier = schedule(
                store, user["id"], body.name, body.scene, body.duration, body.rounds, body.users
            )
        except ValueError as error:
            raise HTTPException(400, str(error)) from None
        controller.wake.set()
        return {"id": identifier, "standings": standings(store, identifier)}

    @app.post("/api/admin/tournaments/{identifier}/publish")
    def publish(identifier: str, user=Depends(administrator)):
        summary = standings(store, identifier)
        if not summary["total"] or summary["completed"] != summary["total"]:
            raise HTTPException(409, "所有场次完成后才可发布总榜；失败场次请先重试")
        with store.connect(write=True) as db:
            db.execute("UPDATE tournaments SET published=1 WHERE id=?", (identifier,))
            db.execute("UPDATE jobs SET published=1 WHERE tournament_id=?", (identifier,))
        return {"ok": True}

    @app.get("/api/runtimes")
    def runtimes(user=Depends(actor)):
        return catalog.list()

    @app.post("/api/admin/runtimes")
    def publish_runtime(body: EnvironmentInput, user=Depends(administrator)):
        if app.state.deployer.snapshot()["state"] == "running":
            raise HTTPException(409, "基础环境正在部署，请等待完成")
        if store.one("SELECT count(*) AS n FROM jobs WHERE state IN ('preparing','running')")["n"]:
            raise HTTPException(409, "请等待当前场次结束后准备环境")
        try:
            catalog.publish(body.environment)
        except ValueError as error:
            raise HTTPException(409, str(error)) from None
        return catalog.list()

    @app.get("/api/admin/operations")
    def operations(user=Depends(administrator)):
        return ops.snapshot()

    @app.post("/api/admin/backup")
    async def backup(user=Depends(administrator)):
        return {"snapshot": await run_in_threadpool(ops.backup)}

    @app.post("/api/admin/maintenance")
    async def maintenance(user=Depends(administrator)):
        return await run_in_threadpool(ops.maintain)

    @app.post("/api/admin/alerts/{identifier}/resolve")
    def resolve(identifier: str, user=Depends(administrator)):
        store.execute("UPDATE alerts SET resolved=1 WHERE id=?", (identifier,))
        return {"ok": True}

    @app.post("/api/jobs/{identifier}/retry")
    def retry(identifier: str, user=Depends(actor)):
        job = job_for(identifier, user)
        if job["kind"] == "official" and user["role"] != "admin":
            raise HTTPException(403, "正式比赛只能由管理员重试")
        with store.connect(write=True) as db:
            current = db.execute(
                "SELECT state,attempts FROM jobs WHERE id=?", (identifier,)
            ).fetchone()
            if current["state"] not in ("failed", "cancelled") or current["attempts"] >= 5:
                raise HTTPException(409, "仅可重试中断或失败的场次，最多五次")
            db.execute(
                "UPDATE jobs SET state='queued',message='按原版本、种子与出生位置重新运行',progress=0,result=NULL,started=NULL,finished=NULL,artifacts_expired=0,attempts=attempts+1 WHERE id=?",
                (identifier,),
            )
            if job["kind"] == "check":
                db.execute(
                    "UPDATE submissions SET state='waiting_check' WHERE id=?",
                    (job["submission_a"],),
                )
        controller.wake.set()
        return {"id": identifier}

    @app.get("/api/jobs/{identifier}/diagnostics")
    def diagnostics(identifier: str, user=Depends(actor)):
        job = job_for(identifier, user)
        path = settings.data / "jobs" / identifier / "diagnostics.json"
        if not path.exists():
            return {"players": [], "timeline": [], "message": "运行开始后生成，刷新可查看"}
        data = json.loads(path.read_text(encoding="utf-8"))
        # Detailed timing belongs to the owner, while published scores remain public.
        allowed = [
            p
            for p, key in enumerate(("player_a", "player_b"))
            if user["role"] == "admin" or job[key] == user["id"]
        ]
        data["players"] = [p for p in data.get("players", []) if p["player"] in allowed]
        data["timeline"] = [
            {
                k: v
                for k, v in row.items()
                if k == "time" or any(k.endswith("_" + str(p)) for p in allowed)
            }
            for row in data.get("timeline", [])
        ]
        return data

    @app.get("/api/compare")
    def compare(first: str, second: str, user=Depends(actor)):
        jobs = [job_for(key, user) for key in (first, second)]
        output = []
        for job in jobs:
            allowed = [
                p
                for p, key in enumerate(("player_a", "player_b"))
                if user["role"] == "admin" or job[key] == user["id"]
            ]
            if not allowed:
                raise HTTPException(404, "只能比较自己的运行结果")
            result = json.loads(job["result"]) if job["result"] else {}
            for pid in allowed:
                output.append(
                    {
                        "job": job["id"],
                        "player": pid,
                        "state": job["state"],
                        "scene": job["scene"],
                        "score": result.get("scores", [None, None])[pid],
                        "health": result.get("health", [None, None])[pid],
                        "wall_seconds": result.get("wall_seconds"),
                        "duration": job["duration"],
                    }
                )
        return output
