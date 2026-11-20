import io
import json
import time
import zipfile

import numpy as np
import pytest
from embodied_arena.city import city_targets
from embodied_arena.engine import reference_image
from embodied_arena.objects import SHAPES
from embodied_arena.platform.competition import standings
from embodied_arena.platform.wirecache import ObservationCache

from tests.test_platform import admin, login, mark_ready, post, register, upload


def players(app, client):
    admin(client)
    code = post(client, "/api/admin/invites", {"uses": 2}).json()["code"]
    output = []
    for name in ("fair_alpha", "fair_beta"):
        user = register(client, code, name)
        submission = upload(client)
        mark_ready(app, submission)
        assert post(client, "/api/entries", {"submission_id": submission["id"]}).status_code == 200
        output.append(user["id"])
    login(client, "organizer")
    return output


def test_mirrored_tournament_seeds_rankings_and_publication(portal):
    app, client = portal
    users = players(app, client)
    created = post(
        client,
        "/api/admin/tournaments",
        {"name": "公平赛", "users": users, "rounds": 2, "duration": 1, "scene": "room"},
    )
    assert created.status_code == 200, created.text
    identifier = created.json()["id"]
    jobs = app.state.store.all("SELECT * FROM jobs WHERE tournament_id=?", (identifier,))
    assert len(jobs) == 4
    for seed in {j["seed"] for j in jobs}:
        assert sorted(j["spawn_swap"] for j in jobs if j["seed"] == seed) == [0, 1]
    assert post(client, f"/api/admin/tournaments/{identifier}/publish").status_code == 409
    for job in jobs:
        app.state.store.update_job(
            job["id"], state="completed", result={"scores": [10, 0]}, finished=time.time()
        )
    summary = standings(app.state.store, identifier)
    assert summary["rows"][0]["points"] == 12 and summary["rows"][0]["played"] == 4
    login(client, "fair_alpha")
    assert client.get("/api/tournaments").json() == []
    assert (
        post(client, "/api/admin/tournaments", {"name": "bad", "users": users}).status_code == 403
    )
    login(client, "organizer")
    assert post(client, f"/api/admin/tournaments/{identifier}/publish").status_code == 200
    login(client, "fair_beta")
    assert len(client.get("/api/tournaments").json()) == 1


def test_transport_cache_is_transactional_and_does_not_mutate_observation():
    cache = ObservationCache()
    obs = {"visual": {"time": 0, "rgb": np.ones((2, 2, 3), dtype=np.uint8)}, "tasks": [{"id": "a"}]}
    first, state = cache.prepare({"op": "act", "observation": obs})
    assert "visual" in first["observation"]
    cache.commit(state)
    second, state = cache.prepare({"op": "act", "observation": obs})
    assert second["reuse_visual"] and second["reuse_tasks"]
    assert "visual" in obs and "tasks" in obs
    fresh, _ = cache.prepare(
        {"op": "act", "observation": {**obs, "visual": {"time": 0.1}, "tasks": []}}
    )
    assert not fresh.get("reuse_visual") and not fresh.get("reuse_tasks")


def test_mixed_task_shapes_are_deterministic_and_reference_images_differ():
    targets = city_targets(7, "mixed-v1")
    assert targets == city_targets(7, "mixed-v1") and {t["shape"] for t in targets} == set(SHAPES)
    assert len({reference_image("red", shape).tobytes() for shape in SHAPES}) == 5
    assert [t["position"] for t in targets] == [t["position"] for t in city_targets(7)]


def test_walking_download_contains_offline_model_and_license(portal):
    app, client = portal
    admin(client)
    response = client.get("/api/template?kind=walking")
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        assert z.getinfo("models/walk.onnx").file_size > 500000
        assert "LICENSES/Holosoma-Apache-2.0.txt" in z.namelist()
        assert "speed" in json.loads(z.read("starter.json"))


def test_backup_restore_keeps_sources_and_revokes_sessions(portal, tmp_path):
    app, client = portal
    admin(client)
    submission = upload(client)
    snapshot = post(client, "/api/admin/backup")
    assert snapshot.status_code == 200, snapshot.text
    from dependency.shell.mujoco.restore_platform import restore

    target = tmp_path / "restored"
    report = restore(app.state.settings.data / "backups" / snapshot.json()["snapshot"], target)
    assert (
        report["submissions"] == 1
        and (target / "submissions" / submission["id"] / "policy.py").exists()
    )
    import sqlite3

    with sqlite3.connect(target / "arena.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM sessions").fetchone()[0] == 0
    with pytest.raises(ValueError):
        restore(app.state.settings.data / "backups" / snapshot.json()["snapshot"], target)


def test_retention_keeps_official_and_recent_jobs_and_retry_permissions(portal):
    app, client = portal
    admin(client)
    submission = upload(client)
    mark_ready(app, submission)
    job = post(client, "/api/practices", {"submission_id": submission["id"]}).json()["id"]
    app.state.store.update_job(job, state="failed", finished=time.time() - 40 * 86400)
    folder = app.state.settings.data / "jobs" / job
    folder.mkdir(parents=True)
    (folder / "test.log").write_text("old")
    assert post(client, "/api/admin/maintenance").json()["expired_practices"] == 1
    assert (
        not folder.exists()
        and app.state.store.one("SELECT * FROM jobs WHERE id=?", (job,))["artifacts_expired"] == 1
    )
    assert post(client, f"/api/jobs/{job}/retry").status_code == 200
    assert post(client, f"/api/jobs/{job}/retry").status_code == 409
    assert client.get("/api/admin/operations").json()["practice_retention_days"] == 30


def test_unavailable_gpu_profile_is_not_published(portal, monkeypatch):
    app, client = portal
    admin(client)
    import subprocess

    monkeypatch.setattr(
        "embodied_arena.platform.environments.docker",
        lambda *a, **k: subprocess.CompletedProcess([], 1, "", "no GPU"),
    )
    app.state.catalog.publish("arena-cuda-v1")
    app.state.catalog.thread.join(timeout=3)
    assert "NVIDIA" in app.state.catalog.error
    assert not app.state.store.one("SELECT * FROM environments WHERE id='arena-cuda-v1'")


def test_spawn_swap_also_exchanges_private_tasks_without_mutating_legacy():
    from dataclasses import replace

    from embodied_arena.config import MatchConfig
    from embodied_arena.scene import get_targets

    config = MatchConfig(scene="cyber_city", task_set="mixed-v1")
    original = get_targets(config)
    swapped = get_targets(replace(config, spawn_swap=True))
    for a, b in zip(original, swapped):
        assert a["position"] == b["position"] and a["id"] == b["id"]
        assert b["owner"] == (None if a["owner"] is None else 1 - a["owner"])
    assert get_targets(config) == original


def test_runtime_versions_are_bound_to_submissions_and_mixed_matches_rejected(portal):
    from embodied_arena.platform.packages import template_zip

    app, client = portal
    admin(client)
    app.state.store.execute(
        "INSERT INTO environments VALUES (?,?,?,0,?,?)",
        ("arena-torch-cpu-v1", "local-image", "sha256:unit", "unit", time.time()),
    )
    first = upload(client)
    mark_ready(app, first)
    second = post(client, "/api/submissions", raw=template_zip("arena-torch-cpu-v1")).json()
    mark_ready(app, second)
    row = app.state.store.one("SELECT environment FROM submissions WHERE id=?", (second["id"],))
    assert row["environment"] == "arena-torch-cpu-v1"
    practice = post(client, "/api/practices", {"submission_id": second["id"]}).json()
    assert (
        app.state.store.one("SELECT environment FROM jobs WHERE id=?", (practice["id"],))[
            "environment"
        ]
        == "arena-torch-cpu-v1"
    )
    assert (
        post(
            client, "/api/practices", {"submission_id": first["id"], "opponent_id": second["id"]}
        ).status_code
        == 409
    )


def test_restart_recovers_original_job_and_bounds_automatic_retries(portal, monkeypatch):
    app, client = portal
    admin(client)
    submission = upload(client)
    mark_ready(app, submission)
    first = post(client, "/api/practices", {"submission_id": submission["id"]}).json()["id"]
    second = post(client, "/api/practices", {"submission_id": submission["id"]}).json()["id"]
    app.state.store.execute("UPDATE jobs SET state='running',attempts=0 WHERE id=?", (first,))
    app.state.store.execute("UPDATE jobs SET state='running',attempts=2 WHERE id=?", (second,))
    original = app.state.store.one(
        "SELECT seed,submission_a,submission_b FROM jobs WHERE id=?", (first,)
    )
    monkeypatch.setattr(app.state.queue, "loop", lambda: None)
    app.state.queue.start()
    app.state.queue.thread.join(timeout=2)
    recovered = app.state.store.one("SELECT * FROM jobs WHERE id=?", (first,))
    assert recovered["state"] == "queued" and recovered["attempts"] == 1
    assert {k: recovered[k] for k in original} == original
    assert app.state.store.one("SELECT state FROM jobs WHERE id=?", (second,))["state"] == "failed"


def test_runtime_publication_reuses_image_and_never_retags_pinned_environment(portal, monkeypatch):
    import subprocess

    app, client = portal
    admin(client)
    calls = []

    def engine(args, **kwargs):
        calls.append(args)
        assert "build" not in args
        return subprocess.CompletedProcess(
            args,
            0,
            json.dumps(
                [
                    {
                        "Id": "sha256:existing",
                        "Config": {
                            "Labels": {"org.thuai10.mujoco.environment": "arena-torch-cpu-v1"}
                        },
                    }
                ]
            ),
            "",
        )

    monkeypatch.setattr("embodied_arena.platform.environments.docker", engine)
    monkeypatch.setattr(
        "embodied_arena.platform.environments.probe",
        lambda settings: {"ready": True, "image_id": "sha256:existing"},
    )
    app.state.catalog.publish("arena-torch-cpu-v1")
    app.state.catalog.thread.join(timeout=3)
    assert not app.state.catalog.error
    assert (
        app.state.store.one("SELECT image_id FROM environments WHERE id='arena-torch-cpu-v1'")[
            "image_id"
        ]
        == "sha256:existing"
    )
    calls.clear()
    app.state.catalog.publish("arena-torch-cpu-v1")
    app.state.catalog.thread.join(timeout=3)
    assert "固定" in app.state.catalog.error and not calls
