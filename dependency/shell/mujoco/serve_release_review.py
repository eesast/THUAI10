"""Show an isolated completed validation dataset; never serves production fixtures."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "logic/mujoco"
sys.path.insert(0, str(ROOT))


if __name__ == "__main__":
    import uvicorn
    from embodied_arena.platform.app import create_app
    from embodied_arena.platform.settings import Settings

    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path)
    parser.add_argument("--run-jobs", action="store_true")
    args = parser.parse_args()
    path = args.data or Path(
        json.loads((ROOT / "artifacts/release_validation/latest.json").read_text(encoding="utf-8"))[
            "data"
        ]
    )
    path = path.resolve()
    if not path.is_relative_to((ROOT / "artifacts/release_validation").resolve()):
        raise RuntimeError("Only isolated release validation data may be reviewed")
    print(
        "Disposable review: http://127.0.0.1:8766/ ; release_admin / release-validation-only",
        flush=True,
    )
    uvicorn.run(
        create_app(
            Settings(data=path, workers=args.run_jobs, session_cookie="thuai10_mujoco_review")
        ),
        host="127.0.0.1",
        port=8766,
        proxy_headers=False,
    )
