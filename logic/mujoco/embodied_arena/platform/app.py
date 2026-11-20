from __future__ import annotations

import json
import mimetypes
import secrets
import sqlite3
import threading
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import Literal
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from embodied_arena.config import FRONTEND_ROOT, ROOT

from .deploy import DeploymentManager
from .packages import PackageError, discard_staging, file_digest, inspect_package, template_zip
from .queue import CompetitionQueue
from .robot_contract import descriptor
from .settings import Settings, allowed_hosts
from .store import Store, digest, password_hash, password_matches


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=24, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(min_length=10, max_length=128)


class Registration(Credentials):
    invite: str = Field(min_length=6, max_length=100)


class InviteInput(BaseModel):
    days: int = Field(default=7, ge=1, le=90)
    uses: int = Field(default=1, ge=1, le=100)


class PracticeInput(BaseModel):
    submission_id: str
    opponent_id: str | None = None
    scene: Literal["cyber_city", "room"] = "cyber_city"


class EntryInput(BaseModel):
    submission_id: str


class MatchInput(BaseModel):
    user_a: str
    user_b: str
    duration: float = Field(default=60, ge=1, le=120)
    scene: Literal["cyber_city", "room"] = "cyber_city"


class RequestInput(BaseModel):
    text: str = Field(min_length=3, max_length=2000)


class ReplyInput(BaseModel):
    reply: str = Field(min_length=1, max_length=2000)


def create_app(settings: Settings | None = None):
    # Windows registry MIME associations may map .js to text/plain. nosniff must
    # stay enabled; explicitly register web asset types instead of weakening it.
    mimetypes.add_type("application/javascript", ".js")
    mimetypes.add_type("text/css", ".css")
    mimetypes.add_type("image/svg+xml", ".svg")
    settings = settings or Settings.from_env()
    store = Store(settings.data)
    from .competition import upgrade
    from .environments import RuntimeCatalog, initialize
    from .operations import Operations

    upgrade(store)
    initialize(store, settings)
    ops = Operations(store, settings)
    catalog = RuntimeCatalog(store, settings)
    controller = CompetitionQueue(store, settings)
    catalog.controller = controller
    deployer = DeploymentManager(store, settings, controller)
    attempts = defaultdict(deque)
    upload_slots = set()
    slots_lock = threading.Lock()

    @asynccontextmanager
    async def lifespan(app):
        # Hold a cross-process lock: multiple web workers must never create two
        # simultaneous simulators or reset each other's running jobs.
        lock = (settings.data / "server.lock").open("a+b")
        lock.seek(0)
        lock.write(b"0")
        lock.flush()
        lock.seek(0)
        try:
            if __import__("os").name == "nt":
                import msvcrt

                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            lock.close()
            raise RuntimeError("此数据目录已经有平台服务运行，请使用已有页面") from None
        if settings.workers:
            controller.start()
            ops.start()
        try:
            yield
        finally:
            deployer.close()
            ops.close()
            controller.close()
            lock.close()

    app = FastAPI(
        title="THUAI10 MuJoCo", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan
    )
    app.state.store = store
    app.state.queue = controller
    app.state.settings = settings
    app.state.deployer = deployer
    app.state.ops = ops
    app.state.catalog = catalog
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts())

    @app.middleware("http")
    async def request_gate(request, call_next):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            origin = request.headers.get("origin")
            if origin and (
                urlsplit(origin).scheme not in ("http", "https")
                or urlsplit(origin).netloc != request.headers.get("host")
            ):
                return JSONResponse(
                    {"detail": "请求来源不匹配，请从平台页面重新操作"}, status_code=403
                )
            limit = settings.upload_bytes if request.url.path == "/api/submissions" else 65536
            length = request.headers.get("content-length")
            if length is None:
                return JSONResponse({"detail": "请求需要 Content-Length"}, status_code=411)
            if not length.isdecimal() or len(length) > 12 or int(length) > limit:
                return JSONResponse({"detail": "请求内容超过大小上限"}, status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def throttle(request, kind):
        key = (request.client.host, kind)
        now = time.monotonic()
        if len(attempts) > 4096:
            for old in list(attempts):
                if not attempts[old] or attempts[old][-1] < now - 600:
                    attempts.pop(old, None)
        bucket = attempts[key]
        while bucket and bucket[0] < now - 600:
            bucket.popleft()
        if len(bucket) >= 20:
            raise HTTPException(429, "尝试次数较多，请 10 分钟后再试")
        bucket.append(now)

    def actor(request: Request):
        token = request.cookies.get(settings.session_cookie, "")
        user = store.one(
            "SELECT u.id,u.username,u.role,s.csrf FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires>? AND u.active=1",
            (digest(token), time.time()),
        )
        if not user:
            raise HTTPException(401, "请先登录")
        if request.method not in ("GET", "HEAD") and not secrets.compare_digest(
            request.headers.get("x-csrf-token", ""), user["csrf"]
        ):
            raise HTTPException(403, "页面凭据已过期，请刷新后重试")
        return user

    def administrator(user=Depends(actor)):
        if user["role"] != "admin":
            raise HTTPException(403, "此操作需要管理员账号")
        return user

    def signed_in(response, user):
        token, csrf = store.session(user["id"], settings.session_seconds)
        response.set_cookie(
            settings.session_cookie,
            token,
            max_age=settings.session_seconds,
            httponly=True,
            samesite="strict",
            secure=settings.secure_cookie,
            path="/",
        )
        return {"id": user["id"], "username": user["username"], "role": user["role"], "csrf": csrf}

    def submission_for(submission_id, user, ready=False):
        submission = store.one("SELECT * FROM submissions WHERE id=?", (submission_id,))
        if not submission or (submission["user_id"] != user["id"] and user["role"] != "admin"):
            raise HTTPException(404, "找不到提交")
        if ready and submission["state"] != "ready":
            raise HTTPException(409, "该版本尚未通过隔离接口检查")
        return submission

    def job_for(job_id, user):
        job = store.one(
            "SELECT j.*,a.user_id AS player_a,b.user_id AS player_b FROM jobs j JOIN submissions a ON a.id=j.submission_a JOIN submissions b ON b.id=j.submission_b WHERE j.id=?",
            (job_id,),
        )
        if not job:
            raise HTTPException(404, "找不到场次")
        if (
            user["role"] != "admin"
            and user["id"] not in (job["player_a"], job["player_b"])
            and not (job["kind"] == "official" and job["published"] and job["state"] == "completed")
        ):
            raise HTTPException(404, "找不到场次")
        return job

    def public_job(job, user):
        item = {
            k: job[k]
            for k in (
                "id",
                "kind",
                "state",
                "progress",
                "duration",
                "scene",
                "created",
                "started",
                "finished",
                "published",
                "artifacts_expired",
                "attempts",
                "environment",
                "tournament_id",
            )
        }
        item["message"] = (
            job["message"]
            if user["role"] == "admin" or job["user_id"] == user["id"] or job["kind"] != "official"
            else {
                "failed": "运行异常，请联系管理员",
                "completed": "比赛完成",
                "running": "仿真运行中",
            }.get(job["state"], "等待管理员安排")
        )
        item["result"] = json.loads(job["result"]) if job["result"] else None
        item["players"] = [
            store.one(
                "SELECT u.username,s.name,s.revision FROM submissions s JOIN users u ON u.id=s.user_id WHERE s.id=?",
                (job[key],),
            )
            for key in ("submission_a", "submission_b")
        ]
        item["position"] = 0
        if job["state"] in ("queued", "waiting_node"):
            queue = store.all(
                "SELECT id FROM jobs WHERE state IN ('queued','waiting_node') ORDER BY CASE kind WHEN 'official' THEN 0 WHEN 'check' THEN 1 ELSE 2 END,created"
            )
            item["position"] = next(
                (i + 1 for i, row in enumerate(queue) if row["id"] == job["id"]), 0
            )
        return item

    def insert_job(db, kind, owner, a, b, scene, duration, auto_practice=False):
        environments = [
            db.execute("SELECT environment FROM submissions WHERE id=?", (key,)).fetchone()[0]
            for key in (a, b)
        ]
        if environments[0] != environments[1]:
            raise HTTPException(409, "对局双方必须使用相同运行环境")
        job_id = uuid.uuid4().hex
        db.execute(
            "INSERT INTO jobs (id,kind,user_id,submission_a,submission_b,state,message,duration,scene,seed,created,auto_practice) VALUES (?,?,?,?,?,'queued',?,?,?,?,?,?)",
            (
                job_id,
                kind,
                owner,
                a,
                b,
                "等待执行节点" if not controller.node.get("ready") else "已加入队列",
                duration,
                scene,
                secrets.randbelow(2**31),
                time.time(),
                int(auto_practice),
            ),
        )
        db.execute(
            "UPDATE jobs SET environment=?,task_set='mixed-v1' WHERE id=?",
            (environments[0], job_id),
        )
        return job_id

    @app.get("/api/status")
    def status():
        return {
            "setup_required": not bool(
                store.one("SELECT id FROM users WHERE role='admin' LIMIT 1")
            ),
            "name": "THUAI10 MuJoCo",
            "version": "0.4.0",
        }

    @app.post("/api/setup")
    def setup(body: Credentials, request: Request, response: Response):
        if request.client.host not in ("127.0.0.1", "::1"):
            raise HTTPException(403, "首次创建管理员需要在服务器本机打开 http://127.0.0.1:8767")
        throttle(request, "setup")
        user = {"id": uuid.uuid4().hex, "username": body.username, "role": "admin"}
        with store.connect(write=True) as db:
            if db.execute("SELECT id FROM users LIMIT 1").fetchone():
                raise HTTPException(409, "管理员已创建，请直接登录")
            db.execute(
                "INSERT INTO users (id,username,password,role,created) VALUES (?,?,?,?,?)",
                (user["id"], user["username"], password_hash(body.password), "admin", time.time()),
            )
        return signed_in(response, user)

    @app.post("/api/login")
    def login(body: Credentials, request: Request, response: Response):
        throttle(request, "login")
        user = store.one("SELECT * FROM users WHERE username=? COLLATE NOCASE", (body.username,))
        dummy = "0123456789abcdef0123456789abcdef$" + "0" * 128
        valid = password_matches(body.password, user["password"] if user else dummy)
        if not user or not valid or not user["active"]:
            raise HTTPException(401, "账号或密码不正确，或账号已停用")
        return signed_in(response, user)

    @app.post("/api/register")
    def register(body: Registration, request: Request, response: Response):
        throttle(request, "register")
        user = {"id": uuid.uuid4().hex, "username": body.username, "role": "player"}
        try:
            with store.connect(write=True) as db:
                invite = db.execute(
                    "SELECT * FROM invites WHERE token=?", (digest(body.invite.strip()),)
                ).fetchone()
                if not invite or not invite["active"]:
                    raise HTTPException(400, "邀请码无效或已停用")
                if invite["expires"] <= time.time():
                    raise HTTPException(400, "邀请码已过期，请向管理员申请新码")
                if invite["remaining"] <= 0:
                    raise HTTPException(400, "邀请码使用次数已用尽")
                db.execute(
                    "INSERT INTO users (id,username,password,role,created) VALUES (?,?,?,?,?)",
                    (
                        user["id"],
                        user["username"],
                        password_hash(body.password),
                        "player",
                        time.time(),
                    ),
                )
                db.execute("UPDATE invites SET remaining=remaining-1 WHERE id=?", (invite["id"],))
        except sqlite3.IntegrityError:
            raise HTTPException(409, "该账号已被使用，请换一个账号") from None
        return signed_in(response, user)

    @app.get("/api/me")
    def me(user=Depends(actor)):
        return user

    @app.post("/api/logout")
    def logout(request: Request, response: Response, user=Depends(actor)):
        store.execute(
            "DELETE FROM sessions WHERE token=?",
            (digest(request.cookies[settings.session_cookie]),),
        )
        response.delete_cookie(settings.session_cookie, path="/")
        return {"ok": True}

    @app.get("/api/environment")
    def environment(user=Depends(actor)):
        node = {k: v for k, v in controller.node.items() if k != "diagnostic"}
        calibration = json.loads((ROOT / "configs/g1_actuators.json").read_text(encoding="utf-8"))
        return {
            "node": node,
            "limits": settings.limits(),
            "joint_names": calibration["dof_names"],
            "robot": descriptor(),
            "practice_paused": store.setting("practice_paused") == "1",
        }

    @app.get("/api/template")
    def template(
        kind: Literal["minimal", "walking"] = "minimal",
        environment: str | None = None,
        user=Depends(actor),
    ):
        selected = environment or settings.environment
        if not store.one("SELECT id FROM environments WHERE id=?", (selected,)):
            raise HTTPException(400, "运行环境尚未发布")
        from .starter import walking_zip

        try:
            content = walking_zip(selected) if kind == "walking" else template_zip(selected)
        except FileNotFoundError as error:
            raise HTTPException(409, str(error)) from None
        return Response(
            content,
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="arena-submission-template.zip"'},
        )

    @app.get("/api/submissions")
    def submissions(user=Depends(actor)):
        sql = "SELECT s.*,u.username FROM submissions s JOIN users u ON u.id=s.user_id"
        rows = store.all(
            sql
            + ("" if user["role"] == "admin" else " WHERE s.user_id=?")
            + " ORDER BY s.created DESC",
            () if user["role"] == "admin" else (user["id"],),
        )
        for row in rows:
            row["report"] = json.loads(row["report"])
        return rows

    @app.post("/api/submissions")
    async def upload(
        request: Request,
        name: str = "",
        description: str = "",
        auto_practice: bool = False,
        user=Depends(actor),
    ):
        if len(name) > 60 or len(description) > 2000:
            raise HTTPException(400, "名称最长 60 字，说明最长 2000 字")
        with slots_lock:
            if user["id"] in upload_slots:
                raise HTTPException(409, "请等待当前上传完成")
            upload_slots.add(user["id"])
        upload_id = uuid.uuid4().hex
        folder = settings.data / "uploads"
        folder.mkdir(exist_ok=True)
        archive = folder / f"{upload_id}.zip"
        total = 0
        try:
            usage = store.one(
                "SELECT count(*) AS n,COALESCE(sum(bytes+expanded_bytes),0) AS total FROM submissions WHERE user_id=?",
                (user["id"],),
            )
            if usage["n"] >= settings.max_versions:
                raise HTTPException(409, "提交版本数量已达上限，请联系管理员")
            with archive.open("xb") as output:
                async for chunk in request.stream():
                    total += len(chunk)
                    if (
                        total > settings.upload_bytes
                        or total + usage["total"] > settings.user_bytes
                    ):
                        raise HTTPException(413, "上传超过文件或账号存储上限")
                    output.write(chunk)
            report = []
            state = "waiting_check"
            manifest = {"name": name or "未命名提交", "environment": settings.environment}
            try:
                inspection_settings = replace(
                    settings,
                    available_environments=tuple(
                        r["id"] for r in store.all("SELECT id FROM environments")
                    ),
                    expanded_bytes=min(
                        settings.expanded_bytes,
                        max(0, settings.user_bytes - usage["total"] - total),
                    ),
                )
                manifest, report = await run_in_threadpool(
                    inspect_package,
                    archive,
                    settings.data / "submissions" / upload_id,
                    inspection_settings,
                )
                if total + usage["total"] + manifest["_expanded_bytes"] > settings.user_bytes:
                    raise PackageError("解压后超过账号总存储上限，请联系管理员清理历史数据")
            except PackageError as e:
                state = "static_failed"
                discard_staging(
                    settings.data / "submissions" / upload_id, settings.data / "submissions"
                )
                manifest["_expanded_bytes"] = 0
                report = [{"name": "静态检查", "state": "failed", "detail": str(e)[:2000]}]
            with store.connect(write=True) as db:
                revision = db.execute(
                    "SELECT COALESCE(max(revision),0)+1 FROM submissions WHERE user_id=?",
                    (user["id"],),
                ).fetchone()[0]
                db.execute(
                    "INSERT INTO submissions (id,user_id,revision,name,description,sha256,bytes,expanded_bytes,environment,state,report,created) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        upload_id,
                        user["id"],
                        revision,
                        name.strip() or manifest["name"],
                        description,
                        file_digest(archive),
                        total,
                        manifest.get("_expanded_bytes", 0),
                        manifest.get("environment", settings.environment),
                        state,
                        json.dumps(report, ensure_ascii=False),
                        time.time(),
                    ),
                )
                if state == "waiting_check":
                    check_id = insert_job(
                        db,
                        "check",
                        user["id"],
                        upload_id,
                        upload_id,
                        "room",
                        1.0,
                        auto_practice=auto_practice,
                    )
            controller.wake.set()
            return {
                "id": upload_id,
                "revision": revision,
                "state": state,
                "report": report,
                "check_job_id": check_id if state == "waiting_check" else None,
                "auto_practice": auto_practice,
            }
        finally:
            with slots_lock:
                upload_slots.discard(user["id"])
            # If no version was committed, remove only this request's archive.
            if not store.one("SELECT id FROM submissions WHERE id=?", (upload_id,)):
                archive.unlink(missing_ok=True)
                discard_staging(
                    settings.data / "submissions" / upload_id, settings.data / "submissions"
                )

    @app.get("/api/submissions/{submission_id}/download")
    def download(submission_id: str, user=Depends(actor)):
        submission = submission_for(submission_id, user)
        return FileResponse(
            settings.data / "uploads" / f"{submission['id']}.zip",
            filename=f"submission-V{submission['revision']:03}.zip",
            media_type="application/zip",
        )

    @app.post("/api/submissions/{submission_id}/recheck")
    def recheck(submission_id: str, user=Depends(actor)):
        submission = submission_for(submission_id, user)
        if submission["state"] not in ("check_failed", "waiting_check", "checking"):
            raise HTTPException(409, "该版本无需运行重检；静态错误需要修复后上传新版本")
        with store.connect(write=True) as db:
            pending = db.execute(
                "SELECT id FROM jobs WHERE kind='check' AND submission_a=? AND state IN ('queued','waiting_node','preparing','running')",
                (submission_id,),
            ).fetchone()
            if pending:
                return {"id": pending[0], "already_queued": True}
            reports = json.loads(submission["report"])
            reports[-1] = {
                "name": "编译与隔离运行接口",
                "state": "waiting",
                "detail": "已重新排队，提交源文件保持同一版本",
            }
            db.execute(
                "UPDATE submissions SET state='waiting_check',report=? WHERE id=?",
                (json.dumps(reports, ensure_ascii=False), submission_id),
            )
            check_id = insert_job(
                db, "check", submission["user_id"], submission_id, submission_id, "room", 1.0
            )
        controller.wake.set()
        return {"id": check_id, "already_queued": False}

    @app.post("/api/practices")
    def practice(body: PracticeInput, user=Depends(actor)):
        a = submission_for(body.submission_id, user, True)
        b = submission_for(body.opponent_id or body.submission_id, user, True)
        if a["user_id"] != user["id"] or b["user_id"] != user["id"]:
            raise HTTPException(403, "练习仅使用自己的提交版本")
        with store.connect(write=True) as db:
            if (
                db.execute("SELECT value FROM settings WHERE key='practice_paused'").fetchone()[0]
                == "1"
            ):
                raise HTTPException(409, "管理员暂停接收新练习，已经开始的局继续运行")
            count = db.execute(
                "SELECT count(*) FROM jobs WHERE user_id=? AND kind='practice' AND state IN ('queued','waiting_node','preparing','running')",
                (user["id"],),
            ).fetchone()[0]
            if count >= 2:
                raise HTTPException(409, "每人最多两场未完成练习，请等待或取消旧练习")
            job_id = insert_job(
                db, "practice", user["id"], a["id"], b["id"], body.scene, settings.practice_duration
            )
        controller.wake.set()
        return {"id": job_id}

    @app.get("/api/jobs")
    def jobs(user=Depends(actor)):
        rows = store.all(
            "SELECT j.* FROM jobs j JOIN submissions a ON a.id=j.submission_a JOIN submissions b ON b.id=j.submission_b WHERE ?='admin' OR j.user_id=? OR (j.kind='official' AND (a.user_id=? OR b.user_id=? OR (j.published=1 AND j.state='completed'))) ORDER BY j.created DESC LIMIT 100",
            (user["role"], user["id"], user["id"], user["id"]),
        )
        return [public_job(row, user) for row in rows]

    @app.get("/api/jobs/{job_id}")
    def job_detail(job_id: str, user=Depends(actor)):
        return public_job(job_for(job_id, user), user)

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel(job_id: str, user=Depends(actor)):
        job = job_for(job_id, user)
        if user["role"] != "admin" and (job["kind"] != "practice" or job["user_id"] != user["id"]):
            raise HTTPException(403, "仅能取消自己的练习")
        if job["state"] not in ("queued", "waiting_node", "preparing", "running"):
            raise HTTPException(409, "该场次已经结束")
        store.execute(
            "UPDATE jobs SET state='cancelled',message='已取消',finished=? WHERE id=? AND state IN ('queued','waiting_node','preparing','running')",
            (time.time(), job_id),
        )
        return {"ok": True}

    @app.get("/api/jobs/{job_id}/replay")
    def replay(job_id: str, user=Depends(actor)):
        job_for(job_id, user)
        path = settings.data / "jobs" / job_id / "replay.json"
        if not path.exists():
            return {"fps": 2, "frames": []}
        return json.loads(path.read_text(encoding="utf-8"))

    @app.get("/api/jobs/{job_id}/frames/{index}")
    def frame(job_id: str, index: int, user=Depends(actor)):
        job_for(job_id, user)
        if not 0 <= index < 1000:
            raise HTTPException(404, "找不到画面")
        path = settings.data / "jobs" / job_id / "frames" / f"{index:04d}.jpg"
        if not path.is_file():
            raise HTTPException(404, "画面尚未生成")
        return FileResponse(path, media_type="image/jpeg")

    @app.get("/api/jobs/{job_id}/events")
    def events(job_id: str, user=Depends(actor)):
        job = job_for(job_id, user)
        path = settings.data / "jobs" / job_id / "events.jsonl"
        if not path.exists():
            return []
        result = []
        for line in path.read_text(encoding="utf-8").splitlines()[-300:]:
            event = json.loads(line)
            if user["role"] != "admin":
                owner = (
                    job["player_a"]
                    if event.get("player") == 0
                    else job["player_b"]
                    if event.get("player") == 1
                    else None
                )
                if owner != user["id"]:
                    event.pop("message", None)
            result.append(event)
        return result

    @app.get("/api/jobs/{job_id}/logs/{player}")
    def logs(job_id: str, player: int, user=Depends(actor)):
        job = job_for(job_id, user)
        if player not in (0, 1) or (
            user["role"] != "admin" and user["id"] != job["player_a" if player == 0 else "player_b"]
        ):
            raise HTTPException(404, "找不到日志")
        path = settings.data / "jobs" / job_id / f"player-{player}.log"
        return {
            "text": path.read_text(encoding="utf-8", errors="replace")[-32768:]
            if path.exists()
            else "日志将在运行结束后保存"
        }

    @app.get("/api/jobs/{job_id}/manifest")
    def reproduction(job_id: str, user=Depends(actor)):
        job_for(job_id, user)
        path = settings.data / "jobs" / job_id / "reproduction.json"
        if not path.exists():
            raise HTTPException(409, "复现清单尚未生成")
        data = json.loads(path.read_text(encoding="utf-8"))
        if user["role"] != "admin":
            data["config"].pop("seed", None)
            data["seed_visibility"] = "隐藏种子由管理员保管"
        return data

    @app.get("/api/entries")
    def entries(user=Depends(actor)):
        sql = "SELECT e.*,u.username,s.revision,s.name FROM entries e JOIN users u ON u.id=e.user_id JOIN submissions s ON s.id=e.submission_id"
        return store.all(
            sql + ("" if user["role"] == "admin" else " WHERE e.user_id=?"),
            () if user["role"] == "admin" else (user["id"],),
        )

    @app.post("/api/entries")
    def enter(body: EntryInput, user=Depends(actor)):
        submission = submission_for(body.submission_id, user, True)
        if submission["user_id"] != user["id"]:
            raise HTTPException(403, "只能报名自己的版本")
        try:
            store.execute(
                "INSERT INTO entries VALUES (?,?,?)", (user["id"], submission["id"], time.time())
            )
        except sqlite3.IntegrityError:
            raise HTTPException(
                409, "本轮报名已经锁定，不会被新上传覆盖；需要改动请联系管理员"
            ) from None
        return {"ok": True}

    @app.get("/api/leaderboard")
    def leaderboard(user=Depends(actor)):
        rows = store.all(
            "SELECT * FROM jobs WHERE kind='official' AND state='completed' AND published=1 ORDER BY finished DESC"
        )
        return [public_job(row, user) for row in rows]

    @app.get("/api/requests")
    def dependency_requests(user=Depends(actor)):
        sql = "SELECT r.*,u.username FROM requests r JOIN users u ON u.id=r.user_id"
        return store.all(
            sql
            + ("" if user["role"] == "admin" else " WHERE r.user_id=?")
            + " ORDER BY r.created DESC",
            () if user["role"] == "admin" else (user["id"],),
        )

    @app.post("/api/requests")
    def request_dependency(body: RequestInput, user=Depends(actor)):
        count = store.one(
            "SELECT count(*) AS n FROM requests WHERE user_id=? AND state='pending'", (user["id"],)
        )["n"]
        if count >= 5:
            raise HTTPException(409, "最多保留五条待处理申请，请等待管理员回复")
        store.execute(
            "INSERT INTO requests (id,user_id,text,created) VALUES (?,?,?,?)",
            (uuid.uuid4().hex, user["id"], body.text, time.time()),
        )
        return {"ok": True}

    @app.get("/api/admin/users")
    def users(user=Depends(administrator)):
        return store.all("SELECT id,username,role,active,created FROM users ORDER BY created")

    @app.post("/api/admin/users/{user_id}/toggle")
    def toggle_user(user_id: str, user=Depends(administrator)):
        target = store.one("SELECT * FROM users WHERE id=?", (user_id,))
        if not target or target["role"] == "admin":
            raise HTTPException(400, "此处只能启停选手账号")
        store.execute("UPDATE users SET active=1-active WHERE id=?", (user_id,))
        store.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        return {"ok": True}

    @app.get("/api/admin/invites")
    def invites(user=Depends(administrator)):
        return store.all(
            "SELECT id,hint,expires,remaining,active,created FROM invites ORDER BY created DESC"
        )

    @app.post("/api/admin/invites")
    def invite(body: InviteInput, user=Depends(administrator)):
        code = "NEON-" + secrets.token_urlsafe(12)
        invite_id = uuid.uuid4().hex
        store.execute(
            "INSERT INTO invites VALUES (?,?,?,?,?,1,?)",
            (
                invite_id,
                digest(code),
                code[:9] + "…",
                time.time() + body.days * 86400,
                body.uses,
                time.time(),
            ),
        )
        return {"id": invite_id, "code": code, "note": "完整邀请码只显示这一次，请复制给选手"}

    @app.post("/api/admin/invites/{invite_id}/disable")
    def disable_invite(invite_id: str, user=Depends(administrator)):
        store.execute("UPDATE invites SET active=0 WHERE id=?", (invite_id,))
        return {"ok": True}

    @app.post("/api/admin/queue/toggle")
    def pause(user=Depends(administrator)):
        with store.connect(write=True) as db:
            paused = (
                db.execute("SELECT value FROM settings WHERE key='practice_paused'").fetchone()[0]
                == "1"
            )
            db.execute(
                "UPDATE settings SET value=? WHERE key='practice_paused'", ("0" if paused else "1",)
            )
        return {"paused": not paused}

    @app.post("/api/admin/node/refresh")
    async def refresh_node(user=Depends(administrator)):
        return await run_in_threadpool(controller.refresh)

    @app.get("/api/admin/deployment")
    def deployment_status(user=Depends(administrator)):
        return deployer.snapshot()

    @app.post("/api/admin/deploy")
    def deploy(user=Depends(administrator)):
        if catalog.building:
            raise HTTPException(409, "模型运行环境正在准备，请等待完成")
        if store.one("SELECT count(*) AS n FROM jobs WHERE state IN ('preparing','running')")["n"]:
            raise HTTPException(409, "当前有场次正在运行，请等待结束后部署，已有队列会保留")
        started = deployer.start()
        if not started and deployer.snapshot()["state"] != "running":
            raise HTTPException(409, "场次已开始，请在其结束后部署")
        return deployer.snapshot()

    @app.post("/api/admin/matches")
    def schedule(body: MatchInput, user=Depends(administrator)):
        if body.user_a == body.user_b:
            raise HTTPException(400, "正式比赛需要两名不同选手")
        with store.connect(write=True) as db:
            entry_a = db.execute("SELECT * FROM entries WHERE user_id=?", (body.user_a,)).fetchone()
            entry_b = db.execute("SELECT * FROM entries WHERE user_id=?", (body.user_b,)).fetchone()
            if not entry_a or not entry_b:
                raise HTTPException(409, "两名选手都需要先报名并锁定版本")
            active = db.execute(
                "SELECT count(*) FROM jobs WHERE kind='official' AND submission_a=? AND submission_b=? AND state IN ('queued','waiting_node','preparing','running')",
                (entry_a["submission_id"], entry_b["submission_id"]),
            ).fetchone()[0]
            if active:
                raise HTTPException(409, "双方已有未完成的同向场次")
            job_id = insert_job(
                db,
                "official",
                user["id"],
                entry_a["submission_id"],
                entry_b["submission_id"],
                body.scene,
                body.duration,
            )
        controller.wake.set()
        return {"id": job_id}

    @app.post("/api/admin/jobs/{job_id}/publish")
    def publish(job_id: str, user=Depends(administrator)):
        job = job_for(job_id, user)
        if job["kind"] != "official" or job["state"] != "completed":
            raise HTTPException(409, "只能发布已完成的正式比赛")
        store.update_job(job_id, published=1)
        return {"ok": True}

    @app.post("/api/admin/entries/{user_id}/unlock")
    def unlock_entry(user_id: str, user=Depends(administrator)):
        store.execute("DELETE FROM entries WHERE user_id=?", (user_id,))
        return {"ok": True, "note": "仅解锁后续报名，已安排比赛的提交版本保持固定"}

    @app.post("/api/admin/requests/{request_id}/reply")
    def reply(request_id: str, body: ReplyInput, user=Depends(administrator)):
        store.execute(
            "UPDATE requests SET reply=?,state='replied' WHERE id=?", (body.reply, request_id)
        )
        return {"ok": True}

    static = FRONTEND_ROOT
    from .extensions import install

    install(
        app, store, settings, controller, ops, catalog, actor, administrator, job_for, public_job
    )
    app.mount("/static", StaticFiles(directory=static), name="static")

    @app.get("/")
    def index():
        return FileResponse(static / "index.html", media_type="text/html")

    return app
