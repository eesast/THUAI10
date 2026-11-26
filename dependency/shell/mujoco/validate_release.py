"""Long-city evaluation, walking starter, mirrored tournament and backup recovery."""

import json
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "logic/mujoco"
sys.path.insert(0, str(ROOT))


def main():
    from embodied_arena.platform.app import create_app
    from embodied_arena.platform.settings import Settings
    from embodied_arena.platform.starter import walking_zip
    from fastapi.testclient import TestClient

    data = ROOT / "artifacts/release_validation" / uuid.uuid4().hex
    app = create_app(Settings(data=data))
    report = {"data": str(data), "checks": [], "production_accounts_created": False}

    def check(ok, message):
        assert ok, message
        report["checks"].append(message)
        print(message, flush=True)

    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 55000)) as client:

        def post(path, body=None, raw=None):
            r = (
                client.post("/api" + path, content=raw, headers={"content-type": "application/zip"})
                if raw is not None
                else client.post("/api" + path, json=body or {})
            )
            assert r.status_code == 200, r.text
            result = r.json()
            if "csrf" in result:
                client.headers["x-csrf-token"] = result["csrf"]
            return result

        def wait(identifier, seconds=1100):
            started = time.monotonic()
            last = None
            while time.monotonic() - started < seconds:
                job = client.get("/api/jobs/" + identifier).json()
                if job.get("state") in ("completed", "failed", "cancelled"):
                    check(job["state"] == "completed", job.get("message", "job failed"))
                    return job
                progress = int(job.get("progress", 0) * 10)
                if progress != last:
                    print(
                        "Progress " + str(progress * 10) + "% " + job.get("message", ""), flush=True
                    )
                    last = progress
                time.sleep(2)
            raise TimeoutError(identifier)

        password = "release-validation-only"
        post("/setup", {"username": "release_admin", "password": password})
        code = post("/admin/invites", {"uses": 2})["code"]
        players = []
        versions = []
        for name in ("release_alpha", "release_beta"):
            player = post("/register", {"username": name, "password": password, "invite": code})
            players.append(player["id"])
            submission = post("/submissions", raw=walking_zip("arena-python-v1"))
            versions.append(submission["id"])
            wait(submission["check_job_id"], 150)
            post("/entries", {"submission_id": submission["id"]})
        practice = post("/practices", {"submission_id": versions[-1], "scene": "cyber_city"})
        long_job = wait(practice["id"])
        result = long_job["result"]
        report["city_result"] = result
        check(
            result["simulated_seconds"] >= 60,
            "Complete 60-second cyber-city evaluation with real RGB-D and two isolated walking policies",
        )
        check(
            client.get("/api/jobs/" + practice["id"] + "/replay").json()["frames"][-1]["time"]
            >= 60,
            "Full-duration real replay saved",
        )
        metrics = client.get("/api/jobs/" + practice["id"] + "/diagnostics").json()
        report["diagnostics"] = metrics
        check(
            len(metrics["players"]) == 2 and all(p["calls"] >= 2990 for p in metrics["players"]),
            "Per-policy latency metrics recorded across the complete city run",
        )
        trajectory = __import__("numpy").load(data / "jobs" / practice["id"] / "trajectory.npz")
        check(
            len(trajectory["time"]) == 3001
            and __import__("numpy").isfinite(trajectory["qpos"]).all(),
            "3001 finite trajectory frames saved",
        )
        displacement = [
            float(
                __import__("numpy").linalg.norm(
                    trajectory["qpos"][-1, :2] - trajectory["qpos"][0, :2]
                )
            )
        ]
        report["sample_displacement_m"] = displacement
        post("/login", {"username": "release_admin", "password": password})
        tournament = post(
            "/admin/tournaments",
            {
                "name": "Release mirrored tournament",
                "users": players,
                "rounds": 2,
                "duration": 1,
                "scene": "room",
            },
        )
        jobs = app.state.store.all("SELECT * FROM jobs WHERE tournament_id=?", (tournament["id"],))
        check(
            len(jobs) == 4 and sum(j["spawn_swap"] for j in jobs) == 2,
            "Mirrored round-robin uses two seeds and both spawn positions",
        )
        for job in jobs:
            wait(job["id"], 150)
        post("/admin/tournaments/" + tournament["id"] + "/publish")
        check(
            client.get("/api/tournaments").json()[0]["standings"]["completed"] == 4,
            "Tournament completes and aggregate standings publish",
        )
        backup = post("/admin/backup")
        check(
            (data / "backups" / backup["snapshot"] / "COMPLETE").exists(),
            "Automatic-format backup includes database and original submission ZIPs",
        )
        check(
            not post("/admin/maintenance")["expired_practices"],
            "Retention preserves recent evaluations",
        )
        report["tournament_id"] = tournament["id"]
        report["practice_id"] = practice["id"]
    report["passed"] = len(report["checks"])
    output = ROOT / "artifacts/release_validation/latest.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps({"passed": report["passed"], "report": str(output)}, ensure_ascii=False),
        flush=True,
    )


if __name__ == "__main__":
    main()
