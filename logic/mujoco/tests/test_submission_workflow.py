import io
import json
import subprocess
import zipfile

import numpy as np
import pytest
from embodied_arena.platform.packages import template_zip
from embodied_arena.platform.robot_contract import descriptor, reorder, validate_manifest

from tests.test_platform import admin, mark_ready, post, upload


@pytest.mark.parametrize(
    "field,value",
    [
        ("robot_id", "other_robot"),
        ("control_mode", "torque"),
        ("joint_unit", "deg"),
        ("action_joint_names", ["hip"] * 29),
        ("action_joint_names", ["hip"] * 12),
    ],
)
def test_reject_incompatible_robot_contract(field, value):
    with pytest.raises(ValueError):
        validate_manifest({field: value})


def test_declared_joint_order_maps_values_by_name_without_guessing():
    names = descriptor()["joint_names"]
    targets = np.arange(29, dtype=float)
    declared = names[::-1]
    assert validate_manifest({"action_joint_names": declared}) == declared
    np.testing.assert_array_equal(reorder(targets[::-1], declared, names), targets)
    with pytest.raises(ValueError):
        reorder(targets, declared, names[:-1])


def test_template_contains_readme_robot_and_compatible_manifest():
    with zipfile.ZipFile(io.BytesIO(template_zip("arena-python-v1"))) as package:
        assert {"README.md", "robot.json", "policy.py", "submission.json"} <= set(
            package.namelist()
        )
        manifest = json.loads(package.read("submission.json"))
        assert manifest["robot_id"] == descriptor()["id"]
        assert len(json.loads(package.read("robot.json"))["joint_names"]) == 29
        assert "优化模型参数" in package.read("README.md").decode("utf-8")


def test_auto_practice_request_is_persisted_until_runtime_check(portal):
    app, client = portal
    admin(client)
    first = post(
        client, "/api/submissions?auto_practice=true", raw=template_zip("arena-python-v1")
    ).json()
    check = app.state.store.one("SELECT * FROM jobs WHERE id=?", (first["check_job_id"],))
    assert check["auto_practice"] == 1
    assert check["kind"] == "check" and check["state"] == "queued"
    assert app.state.store.one("SELECT count(*) AS n FROM jobs WHERE kind='practice'")["n"] == 0
    # A static failure cannot start a practice even when requested.
    invalid = post(client, "/api/submissions?auto_practice=true", raw=b"not a zip").json()
    assert invalid["state"] == "static_failed" and invalid["check_job_id"] is None
    assert app.state.store.one("SELECT count(*) AS n FROM jobs WHERE kind='practice'")["n"] == 0


def test_deployment_is_admin_only_and_does_not_interrupt_active_match(portal):
    app, client = portal
    admin(client)
    submission = upload(client)
    mark_ready(app, submission)
    practice = post(client, "/api/practices", {"submission_id": submission["id"]}).json()["id"]
    app.state.store.update_job(practice, state="running")
    assert post(client, "/api/admin/deploy").status_code == 409
    assert app.state.deployer.snapshot()["state"] == "idle"
    code = post(client, "/api/admin/invites", {"days": 1, "uses": 1}).json()["code"]
    from tests.test_platform import register

    register(client, code, "ordinary_player")
    assert client.get("/api/admin/deployment").status_code == 403
    assert post(client, "/api/admin/deploy").status_code == 403


def test_deployment_refuses_to_rebuild_a_missing_pinned_environment(portal, monkeypatch):
    app, client = portal
    app.state.store.execute(
        "INSERT INTO settings VALUES (?,?)", ("image:arena-python-v1", "sha256:original")
    )
    calls = []

    def unavailable(args, timeout=8):
        calls.append(args)
        return subprocess.CompletedProcess(args, 1, "", "missing")

    monkeypatch.setattr("embodied_arena.platform.deploy.docker", unavailable)
    with pytest.raises(RuntimeError, match="镜像丢失"):
        app.state.deployer.ensure_image()
    assert not any("build" in args or "tag" in args for args in calls)


def test_recheck_preserves_version_deduplicates_jobs_and_checks_ownership(portal):
    app, client = portal
    admin(client)
    submission = upload(client)
    endpoint = f"/api/submissions/{submission['id']}/recheck"
    queued = post(client, endpoint).json()
    assert queued == {"id": submission["check_job_id"], "already_queued": True}
    before = app.state.store.one(
        "SELECT revision,sha256 FROM submissions WHERE id=?", (submission["id"],)
    )
    app.state.store.update_job(queued["id"], state="failed")
    app.state.store.execute(
        "UPDATE submissions SET state='check_failed' WHERE id=?", (submission["id"],)
    )
    retry = post(client, endpoint)
    assert retry.status_code == 200
    assert retry.json()["id"] != queued["id"] and not retry.json()["already_queued"]
    assert post(client, endpoint).json() == {"id": retry.json()["id"], "already_queued": True}
    assert (
        app.state.store.one(
            "SELECT revision,sha256 FROM submissions WHERE id=?", (submission["id"],)
        )
        == before
    )
    mark_ready(app, submission)
    assert post(client, endpoint).status_code == 409
    invalid = post(client, "/api/submissions", raw=b"not a zip").json()
    assert post(client, f"/api/submissions/{invalid['id']}/recheck").status_code == 409
    code = post(client, "/api/admin/invites", {"days": 1, "uses": 1}).json()["code"]
    from tests.test_platform import register

    register(client, code, "unrelated_player")
    assert post(client, endpoint).status_code in (403, 404)
