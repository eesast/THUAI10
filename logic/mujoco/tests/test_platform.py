import io
import json
import stat
import time
import zipfile

import numpy as np
import pytest
from embodied_arena.platform.packages import PackageError, inspect_package, template_zip
from embodied_arena.platform.protocol import dumps, loads, validate_action
from embodied_arena.platform.settings import Settings

PASSWORD = "unit-test-password-only"


def post(client, path, body=None, raw=None):
    if raw is not None:
        return client.post(path, content=raw, headers={"content-type": "application/zip"})
    return client.post(path, json=body if body is not None else {})


def test_static_assets_have_explicit_browser_safe_mime_types(portal):
    app, client = portal
    script = client.get("/static/app.js")
    assert script.status_code == 200
    assert script.headers["content-type"].startswith("application/javascript")
    assert script.headers["x-content-type-options"] == "nosniff"
    assert client.get("/static/style.css").headers["content-type"].startswith("text/css")


def admin(client):
    result = post(client, "/api/setup", {"username": "organizer", "password": PASSWORD})
    assert result.status_code == 200, result.text
    client.headers["x-csrf-token"] = result.json()["csrf"]
    return result.json()


def login(client, name):
    result = post(client, "/api/login", {"username": name, "password": PASSWORD})
    assert result.status_code == 200, result.text
    client.headers["x-csrf-token"] = result.json()["csrf"]
    return result.json()


def register(client, code, name):
    result = post(client, "/api/register", {"username": name, "password": PASSWORD, "invite": code})
    assert result.status_code == 200, result.text
    client.headers["x-csrf-token"] = result.json()["csrf"]
    return result.json()


def upload(client):
    response = post(client, "/api/submissions?name=unit-test", raw=template_zip("arena-python-v1"))
    assert response.status_code == 200, response.text
    return response.json()


def mark_ready(app, submission):
    # Permission unit tests seed eligibility; actual isolated execution is tested
    # separately against Docker and MuJoCo, never through a production bypass.
    app.state.store.execute("UPDATE submissions SET state='ready' WHERE id=?", (submission["id"],))


def test_invite_setup_csrf_session_and_role_boundaries(portal):
    app, client = portal
    assert client.get("/api/status").json()["setup_required"]
    assert client.get("/api/submissions").status_code == 401
    admin(client)
    assert not client.get("/api/status").json()["setup_required"]
    assert (
        post(client, "/api/setup", {"username": "second_admin", "password": PASSWORD}).status_code
        == 409
    )
    saved = client.headers.pop("x-csrf-token")
    assert post(client, "/api/admin/invites", {"days": 1, "uses": 1}).status_code == 403
    client.headers["x-csrf-token"] = saved
    code = post(client, "/api/admin/invites", {"days": 1, "uses": 1}).json()["code"]
    invites = client.get("/api/admin/invites").json()
    assert code not in json.dumps(invites)
    register(client, code, "player_one")
    assert client.get("/api/admin/users").status_code == 403
    assert (
        post(
            client,
            "/api/register",
            {"username": "player_two", "password": PASSWORD, "invite": code},
        ).status_code
        == 400
    )
    assert post(client, "/api/logout").status_code == 200
    assert client.get("/api/me").status_code == 401


def test_registration_race_and_expiration_do_not_consume_extra_uses(portal):
    app, client = portal
    admin(client)
    item = post(client, "/api/admin/invites", {"days": 1, "uses": 2}).json()
    register(client, item["code"], "taken_name")
    assert (
        post(
            client,
            "/api/register",
            {"username": "taken_name", "password": PASSWORD, "invite": item["code"]},
        ).status_code
        == 409
    )
    assert (
        app.state.store.one("SELECT remaining FROM invites WHERE id=?", (item["id"],))["remaining"]
        == 1
    )
    app.state.store.execute(
        "UPDATE invites SET expires=? WHERE id=?", (time.time() - 1, item["id"])
    )
    result = post(
        client,
        "/api/register",
        {"username": "other_name", "password": PASSWORD, "invite": item["code"]},
    )
    assert result.status_code == 400 and "过期" in result.json()["detail"]


def test_static_upload_is_not_eligible_and_versions_are_immutable(portal):
    app, client = portal
    admin(client)
    first, second = upload(client), upload(client)
    assert (first["revision"], second["revision"]) == (1, 2)
    assert first["id"] != second["id"]
    assert first["state"] == "waiting_check"
    assert post(client, "/api/practices", {"submission_id": first["id"]}).status_code == 409
    assert post(client, "/api/entries", {"submission_id": first["id"]}).status_code == 409
    mark_ready(app, first)
    assert post(client, "/api/entries", {"submission_id": first["id"]}).status_code == 200
    third = upload(client)
    mark_ready(app, third)
    assert post(client, "/api/entries", {"submission_id": third["id"]}).status_code == 409
    assert client.get("/api/entries").json()[0]["submission_id"] == first["id"]
    original = client.get(f"/api/submissions/{first['id']}/download")
    assert original.content == template_zip("arena-python-v1") or zipfile.is_zipfile(
        io.BytesIO(original.content)
    )


def test_private_uploads_and_jobs_are_inaccessible_to_other_players(portal):
    app, client = portal
    admin(client)
    code = post(client, "/api/admin/invites", {"days": 1, "uses": 2}).json()["code"]
    register(client, code, "owner_one")
    submission = upload(client)
    mark_ready(app, submission)
    job = post(client, "/api/practices", {"submission_id": submission["id"]}).json()["id"]
    register(client, code, "owner_two")
    assert client.get("/api/submissions").json() == []
    assert client.get(f"/api/submissions/{submission['id']}/download").status_code == 404
    for suffix in ("", "/replay", "/frames/0", "/events", "/logs/0", "/manifest"):
        assert client.get(f"/api/jobs/{job}{suffix}").status_code == 404
    assert post(client, "/api/jobs/" + job + "/cancel").status_code == 404
    assert post(client, "/api/practices", {"submission_id": submission["id"]}).status_code == 404


def test_official_publication_keeps_source_logs_and_hidden_seed_private(portal):
    app, client = portal
    admin(client)
    code = post(client, "/api/admin/invites", {"days": 1, "uses": 3}).json()["code"]
    players = []
    for name in ("alpha_one", "beta_two"):
        user = register(client, code, name)
        submission = upload(client)
        mark_ready(app, submission)
        assert post(client, "/api/entries", {"submission_id": submission["id"]}).status_code == 200
        players.append((user, submission))
    register(client, code, "observer_three")
    login(client, "organizer")
    job_id = post(
        client,
        "/api/admin/matches",
        {"user_a": players[0][0]["id"], "user_b": players[1][0]["id"], "duration": 1},
    ).json()["id"]
    folder = app.state.settings.data / "jobs" / job_id
    folder.mkdir(parents=True)
    (folder / "events.jsonl").write_text(
        json.dumps(
            {"time": 0, "type": "policy_error", "player": 0, "message": "private-source-line"}
        )
        + "\n",
        encoding="utf-8",
    )
    (folder / "reproduction.json").write_text(
        json.dumps({"config": {"seed": 123, "scene": "room"}}), encoding="utf-8"
    )
    app.state.store.update_job(
        job_id,
        state="completed",
        result={"scores": [10, 0], "health": [100, 100], "winners": [0], "tie": False},
        finished=time.time(),
    )
    login(client, "observer_three")
    assert client.get("/api/leaderboard").json() == []
    assert client.get("/api/jobs/" + job_id).status_code == 404
    login(client, "organizer")
    assert post(client, f"/api/admin/jobs/{job_id}/publish").status_code == 200
    # Unlocking future registration cannot mutate an existing match's versions.
    assert post(client, "/api/admin/entries/" + players[0][0]["id"] + "/unlock").status_code == 200
    assert (
        app.state.store.one("SELECT submission_a FROM jobs WHERE id=?", (job_id,))["submission_a"]
        == players[0][1]["id"]
    )
    login(client, "observer_three")
    assert len(client.get("/api/leaderboard").json()) == 1
    assert "message" not in client.get(f"/api/jobs/{job_id}/events").json()[0]
    assert "seed" not in client.get(f"/api/jobs/{job_id}/manifest").json()["config"]
    assert client.get(f"/api/jobs/{job_id}/logs/0").status_code == 404
    assert client.get(f"/api/submissions/{players[0][1]['id']}/download").status_code == 404
    login(client, "alpha_one")
    assert client.get(f"/api/jobs/{job_id}/events").json()[0]["message"] == "private-source-line"


def test_queue_limits_pause_and_cancellation(portal):
    app, client = portal
    admin(client)
    submission = upload(client)
    mark_ready(app, submission)
    jobs = [
        post(client, "/api/practices", {"submission_id": submission["id"]}).json()["id"]
        for _ in range(2)
    ]
    assert post(client, "/api/practices", {"submission_id": submission["id"]}).status_code == 409
    assert post(client, "/api/jobs/" + jobs[0] + "/cancel").status_code == 200
    assert post(client, "/api/admin/queue/toggle").json()["paused"]
    assert post(client, "/api/practices", {"submission_id": submission["id"]}).status_code == 409
    assert not post(client, "/api/admin/queue/toggle").json()["paused"]
    assert post(client, "/api/practices", {"submission_id": submission["id"]}).status_code == 200


@pytest.mark.parametrize(
    "name",
    [
        "../outside.py",
        "/outside.py",
        "a/../../outside.py",
        "a\\outside.py",
        "C:/outside.py",
        "x:secret",
        "CON.txt",
        "dir./file",
    ],
)
def test_zip_paths_never_escape_submission_directory(tmp_path, name):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr(name, "no")
    with pytest.raises(PackageError):
        inspect_package(archive, tmp_path / "out", Settings(data=tmp_path))
    assert not (tmp_path / "outside.py").exists()


def test_zip_symlink_duplicate_bomb_and_no_host_execution(tmp_path):
    settings = Settings(data=tmp_path)
    for case in ("link", "duplicate", "bomb"):
        archive = tmp_path / f"{case}.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            if case == "link":
                item = zipfile.ZipInfo("link")
                item.create_system = 3
                item.external_attr = (stat.S_IFLNK | 0o777) << 16
                z.writestr(item, "../outside")
            elif case == "duplicate":
                z.writestr("Policy.py", "")
                z.writestr("policy.py", "")
            else:
                z.writestr("huge.bin", b"0" * 1000000)
        with pytest.raises(PackageError):
            inspect_package(archive, tmp_path / case, settings)
    archive = tmp_path / "valid.zip"
    with (
        zipfile.ZipFile(io.BytesIO(template_zip(settings.environment))) as original,
        zipfile.ZipFile(archive, "w") as z,
    ):
        for item in original.infolist():
            content = original.read(item)
            if item.filename == "policy.py":
                content = (
                    f"from pathlib import Path\nPath({str(tmp_path / 'host-canary')!r}).write_text('unsafe')\n".encode()
                    + content
                )
            z.writestr("wrapper/" + item.filename, content)
    manifest, reports = inspect_package(archive, tmp_path / "safe", settings)
    assert not (tmp_path / "host-canary").exists()
    assert (tmp_path / "safe/policy.py").exists()
    assert reports[-1]["state"] == "waiting"


def test_wire_roundtrip_and_reject_executable_array_payloads():
    observation = {
        "image": np.zeros((3, 4, 3), dtype=np.uint8),
        "q": np.arange(29, dtype=float),
        "nested": {"flag": True},
    }
    restored = loads(dumps(observation))
    np.testing.assert_array_equal(restored["image"], observation["image"])
    for payload in (
        {"__array__": 1, "dtype": "object", "shape": [1], "data": ""},
        {"__array__": 1, "dtype": "float64", "shape": [999999999], "data": ""},
        {"__array__": 1, "dtype": "float64", "shape": [29], "data": "AA=="},
    ):
        with pytest.raises(ValueError):
            loads(json.dumps(payload).encode())
    for action in (
        {"joint_targets": [0] * 28, "fire": False},
        {"joint_targets": [float("nan")] * 29, "fire": False},
        {"joint_targets": [0] * 29, "fire": "true"},
        {"joint_targets": [False] * 29, "fire": False},
    ):
        with pytest.raises(ValueError):
            validate_action(action)


def test_origin_host_and_account_revocation(portal):
    app, client = portal
    admin(client)
    assert client.get("/api/status", headers={"host": "evil.example"}).status_code == 400
    assert (
        client.post(
            "/api/admin/invites",
            json={"days": 1, "uses": 1},
            headers={"Origin": "https://evil.example"},
        ).status_code
        == 403
    )
    code = post(client, "/api/admin/invites", {"days": 1, "uses": 1}).json()["code"]
    user = register(client, code, "revoked_user")
    old_cookie = client.cookies.get("thuai10_mujoco_session")
    login(client, "organizer")
    assert post(client, f"/api/admin/users/{user['id']}/toggle").status_code == 200
    client.cookies.clear()
    client.cookies.set("thuai10_mujoco_session", old_cookie)
    assert client.get("/api/me").status_code == 401
