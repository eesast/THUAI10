"""Loopback-only disposable portal for manual/browser QA, never production data."""

import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "logic/mujoco"
sys.path.insert(0, str(ROOT))


def main():
    import json

    import uvicorn
    from embodied_arena.platform.app import create_app
    from embodied_arena.platform.packages import template_zip
    from embodied_arena.platform.settings import Settings
    from embodied_arena.platform.store import password_hash

    base = (ROOT / "artifacts/platform_validation").resolve()
    data = (base / ("manual-" + uuid.uuid4().hex)).resolve()
    if not data.is_relative_to(base) or data.exists():
        raise RuntimeError(
            "Validation data must be a new directory beneath artifacts/platform_validation"
        )
    settings = Settings(
        data=data, practice_duration=1.0, session_cookie="thuai10_mujoco_validation"
    )
    app = create_app(settings)
    password = "local-validation-only"
    with app.state.store.connect(write=True) as db:
        for username, role in (("demo_admin", "admin"), ("demo_player", "player")):
            db.execute(
                "INSERT INTO users (id,username,password,role,created) VALUES (?,?,?,?,?)",
                (uuid.uuid4().hex, username, password_hash(password), role, time.time()),
            )
    (data / "submission.zip").write_bytes(template_zip(settings.environment))
    (base / "manual-latest.json").write_text(
        json.dumps({"data": str(data), "url": "http://127.0.0.1:8766/"}), encoding="utf-8"
    )
    print(
        "Disposable QA portal: http://127.0.0.1:8766/ (demo_admin / demo_player, password local-validation-only)",
        flush=True,
    )
    uvicorn.run(app, host="127.0.0.1", port=8766, proxy_headers=False, workers=1)


if __name__ == "__main__":
    main()
