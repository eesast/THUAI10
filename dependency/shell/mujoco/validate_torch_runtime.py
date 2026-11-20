"""Exercise an actual uploaded PyTorch policy through the versioned queue."""

import io
import json
import sys
import time
import uuid
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "logic/mujoco"
sys.path.insert(0, str(ROOT))


def main():
    from embodied_arena.platform.app import create_app
    from embodied_arena.platform.packages import template_zip
    from embodied_arena.platform.settings import Settings
    from fastapi.testclient import TestClient

    folder = ROOT / "artifacts/torch_validation" / uuid.uuid4().hex
    app = create_app(Settings(data=folder, practice_duration=1))
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 55001)) as client:

        def post(path, body=None, raw=None):
            r = (
                client.post("/api" + path, content=raw, headers={"content-type": "application/zip"})
                if raw
                else client.post("/api" + path, json=body or {})
            )
            assert r.status_code == 200, r.text
            data = r.json()
            if "csrf" in data:
                client.headers["x-csrf-token"] = data["csrf"]
            return data

        post("/setup", {"username": "torch_validation", "password": "torch-validation-only"})
        post("/admin/runtimes", {"environment": "arena-torch-cpu-v1"})
        while app.state.catalog.building:
            time.sleep(1)
        assert not app.state.catalog.error, app.state.catalog.error
        buffer = io.BytesIO()
        with (
            zipfile.ZipFile(io.BytesIO(template_zip("arena-torch-cpu-v1"))) as original,
            zipfile.ZipFile(buffer, "w") as output,
        ):
            for name in original.namelist():
                output.writestr(
                    name,
                    "import torch\nclass Policy:\n def __init__(self,player_id=0,config=None):\n  assert torch.__version__.startswith('2.7.0')\n def act(self,o):\n  return {'joint_targets':torch.from_numpy(o['proprio']['q']).clone().numpy(),'fire':False}\n"
                    if name == "policy.py"
                    else original.read(name),
                )
        submission = post("/submissions", raw=buffer.getvalue())

        def wait(identifier):
            start = time.monotonic()
            while time.monotonic() - start < 180:
                row = client.get("/api/jobs/" + identifier).json()
                if row["state"] in ("completed", "failed"):
                    assert row["state"] == "completed", row["message"]
                    return row
                time.sleep(1)
            raise TimeoutError(identifier)

        wait(submission["check_job_id"])
        print("Actual uploaded torch policy passes isolated checks", flush=True)
        practice = post("/practices", {"submission_id": submission["id"], "scene": "room"})
        job = wait(practice["id"])
        assert job["environment"] == "arena-torch-cpu-v1"
        report = {
            "passed": 3,
            "environment": job["environment"],
            "image_id": app.state.store.one("SELECT image_id FROM jobs WHERE id=?", (job["id"],))[
                "image_id"
            ],
            "job_id": job["id"],
            "data": str(folder),
            "production_accounts_created": False,
        }
        path = ROOT / "artifacts/torch_validation/latest.json"
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
