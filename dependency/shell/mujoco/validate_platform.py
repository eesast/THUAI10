"""Real Docker -> policy check -> MuJoCo -> private replay -> official publication.

Uses a new, separate data directory. Never creates accounts in the live portal.
"""

from __future__ import annotations

import io
import json
import sys
import time
import uuid
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "logic/mujoco"
sys.path.insert(0, str(ROOT))


def wait_for(client, path, predicate, seconds=120):
    start = time.monotonic()
    while time.monotonic() - start < seconds:
        response = client.get(path)
        assert response.status_code == 200, response.text
        data = response.json()
        if predicate(data):
            return data
        time.sleep(0.5)
    raise TimeoutError(f"Timed out: {path}")


def main():
    from embodied_arena.platform.app import create_app
    from embodied_arena.platform.packages import template_zip
    from embodied_arena.platform.settings import Settings
    from fastapi.testclient import TestClient

    folder = ROOT / "artifacts/platform_validation" / uuid.uuid4().hex
    app = create_app(Settings(data=folder, practice_duration=2.0))
    results = {"data": str(folder), "checks": [], "production_accounts_created": False}
    password = "validation-only-no-live-account"

    def check(condition, message):
        assert condition, message
        results["checks"].append(message)
        print(message, flush=True)

    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as client:

        def post(path, body=None, raw=None):
            response = (
                client.post("/api" + path, content=raw, headers={"content-type": "application/zip"})
                if raw is not None
                else client.post("/api" + path, json=body or {})
            )
            assert response.status_code == 200, response.text
            data = response.json()
            if "csrf" in data:
                client.headers["x-csrf-token"] = data["csrf"]
            return data

        post("/setup", {"username": "validation_admin", "password": password})
        post("/admin/deploy")
        deployment = wait_for(
            client,
            "/api/admin/deployment",
            lambda d: d["state"] in ("completed", "failed"),
            seconds=240,
        )
        check(
            deployment["state"] == "completed",
            "Admin one-click deployment and actual simulation self-check succeed: "
            + deployment["stage"],
        )
        check(
            any("MuJoCo /" in line for line in deployment["logs"]),
            "Deployment verifies real MuJoCo RGB-D and container communication",
        )
        node = wait_for(client, "/api/environment", lambda e: e["node"].get("ready"), seconds=30)
        results["image_id"] = node["node"]["image_id"]
        check(node["node"]["ready"], "Real isolated execution node is ready")
        code = post("/admin/invites", {"days": 1, "uses": 3})["code"]

        def login(username):
            return post("/login", {"username": username, "password": password})

        def enroll(username):
            return post("/register", {"username": username, "password": password, "invite": code})

        safe_policy = """import os
from pathlib import Path
import socket
import numpy as np
import onnxruntime

class Policy:
    def __init__(self, player_id=0, config=None):
        assert os.getuid() == 65532
        assert not Path('/var/run/docker.sock').exists()
        assert not Path('/runtime/scene.xml').exists()
        Path('/tmp/private-scratch').write_text('allowed')
        try:
            Path('/submission/host-write-canary').write_text('forbidden')
            raise AssertionError('Submission mount must be read-only')
        except OSError:
            pass
        sock = socket.socket()
        sock.settimeout(.2)
        try:
            sock.connect(('1.1.1.1',443))
            raise AssertionError('Internet must be unavailable')
        except OSError:
            pass
        finally:
            sock.close()
        print('isolation uid/read-only/network/tmp/onnxruntime verified',flush=True)
    def act(self, observation):
        assert observation['visual']['rgb'].dtype == np.uint8
        assert observation['proprio']['q'].shape == (29,)
        assert 'seed' not in self.__dict__
        return {'joint_targets': observation['proprio']['q'].copy(), 'fire':False}
"""

        def package(source, extra=None, manifest_updates=None):
            out = io.BytesIO()
            with (
                zipfile.ZipFile(io.BytesIO(template_zip("arena-python-v1"))) as z,
                zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dest,
            ):
                for item in z.infolist():
                    content = source if item.filename == "policy.py" else z.read(item)
                    if item.filename == "submission.json" and manifest_updates:
                        manifest = json.loads(content)
                        manifest.update(manifest_updates)
                        content = json.dumps(manifest)
                    dest.writestr(item.filename, content)
                for name, content in (extra or {}).items():
                    dest.writestr(name, content)
            return out.getvalue()

        players = []
        for name in ("validation_alpha", "validation_beta"):
            user = enroll(name)
            if name == "validation_alpha":
                broken = post(
                    "/submissions?name=unimported-syntax-error",
                    raw=package(
                        safe_policy, extra={"src/unimported.py": "def broken(:\n    pass\n"}
                    ),
                )
                rows = wait_for(
                    client,
                    "/api/submissions",
                    lambda rows: any(
                        r["id"] == broken["id"] and r["state"] in ("ready", "check_failed")
                        for r in rows
                    ),
                )
                failed = next(r for r in rows if r["id"] == broken["id"])
                check(
                    failed["state"] == "check_failed"
                    and "src/unimported.py" in failed["report"][-1]["detail"],
                    "Compilation rejects an unused broken helper and identifies its filename",
                )
                wrong = post(
                    "/submissions?name=invalid-action",
                    raw=package(safe_policy.replace("['q'].copy()", "['q'][:28].copy()")),
                )
                rows = wait_for(
                    client,
                    "/api/submissions",
                    lambda rows: any(
                        r["id"] == wrong["id"] and r["state"] in ("ready", "check_failed")
                        for r in rows
                    ),
                )
                failed = next(r for r in rows if r["id"] == wrong["id"])
                check(
                    failed["state"] == "check_failed" and "29" in failed["report"][-1]["detail"],
                    "Actual runtime rejects a 28-joint policy before competition",
                )
                from embodied_arena.platform.robot_contract import descriptor

                source = safe_policy.replace("['q'].copy()", "['q'][::-1].copy()")
                data = package(
                    source,
                    manifest_updates={"action_joint_names": descriptor()["joint_names"][::-1]},
                )
            else:
                data = package(safe_policy)
            sub = post(
                "/submissions?name="
                + name
                + ("&auto_practice=true" if name == "validation_alpha" else ""),
                raw=data,
            )
            row = wait_for(
                client,
                "/api/submissions",
                lambda rows: any(
                    r["id"] == sub["id"] and r["state"] in ("ready", "check_failed") for r in rows
                ),
            )
            row = next(r for r in row if r["id"] == sub["id"])
            check(
                row["state"] == "ready",
                f"{name}: actual Docker initialization, framework import and 3 action checks passed: "
                + str(row["report"][-1]["detail"]),
            )
            check(
                not (folder / "submissions" / sub["id"] / "host-write-canary").exists(),
                "Policy cannot modify the host submission folder",
            )
            post("/entries", {"submission_id": sub["id"]})
            players.append((user, sub))
        login("validation_alpha")
        checked = client.get("/api/jobs/" + players[0][1]["check_job_id"]).json()
        practice = checked["result"]["followup_job_id"]
        check(
            bool(practice),
            "Upload continues automatically into a practice without a second start request",
        )
        result = wait_for(
            client,
            "/api/jobs/" + practice,
            lambda j: j["state"] in ("completed", "failed"),
            seconds=120,
        )
        check(
            result["state"] == "completed",
            "Real 2-second MuJoCo cyber-city practice completes: " + result["message"],
        )
        check(
            not result["result"]["events"].get("policy_error", 0),
            "Explicit reversed joint declaration is correctly adapted during actual simulation",
        )
        frames = client.get("/api/jobs/" + practice + "/replay").json()["frames"]
        check(len(frames) >= 5, "Real multi-view replay frames were saved")
        check(
            client.get("/api/jobs/" + practice + "/frames/0").status_code == 200,
            "Authenticated owner can retrieve a real replay image",
        )
        results["practice_id"] = practice
        enroll("validation_observer")
        check(
            client.get("/api/jobs/" + practice + "/frames/0").status_code == 404,
            "Other contestants cannot retrieve private practice frames",
        )
        check(
            client.get("/api/submissions/" + players[0][1]["id"] + "/download").status_code == 404,
            "Other contestants cannot download source or model packages",
        )
        login("validation_admin")
        match = post(
            "/admin/matches",
            {
                "user_a": players[0][0]["id"],
                "user_b": players[1][0]["id"],
                "scene": "room",
                "duration": 1.0,
            },
        )["id"]
        result = wait_for(
            client,
            "/api/jobs/" + match,
            lambda j: j["state"] in ("completed", "failed"),
            seconds=120,
        )
        check(
            result["state"] == "completed",
            "Actual official match completes with pinned submissions: " + result["message"],
        )
        post("/admin/jobs/" + match + "/publish")
        login("validation_observer")
        check(
            any(j["id"] == match for j in client.get("/api/leaderboard").json()),
            "Published official scores become visible to another authenticated contestant",
        )
        check(
            client.get("/api/jobs/" + match + "/frames/0").status_code == 200,
            "Published official replay is available to other contestants",
        )
        check(
            client.get("/api/jobs/" + match + "/logs/0").status_code == 404,
            "Public official replay does not expose private strategy logs",
        )
        check(
            "seed" not in client.get("/api/jobs/" + match + "/manifest").json()["config"],
            "Hidden layout seed is redacted from contestant reproduction metadata",
        )
        results["official_id"] = match
        results["scores"] = result["result"]["scores"]
    results["passed"] = len(results["checks"])
    target = ROOT / "artifacts/platform_validation/integration.json"
    target.parent.mkdir(exist_ok=True, parents=True)
    target.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": results["passed"], "report": str(target)}), flush=True)


if __name__ == "__main__":
    main()
