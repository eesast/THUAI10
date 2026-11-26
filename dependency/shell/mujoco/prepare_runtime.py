"""Build and validate one predefined runtime; no contestant installation scripts."""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "logic/mujoco"
sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    from embodied_arena.platform.app import create_app
    from embodied_arena.platform.settings import Settings

    parser = argparse.ArgumentParser()
    parser.add_argument("environment")
    parser.add_argument("--data", type=Path, default=ROOT / "var/platform")
    args = parser.parse_args()
    app = create_app(Settings(data=args.data, workers=False))
    catalog = app.state.catalog
    catalog.publish(args.environment)
    while catalog.building:
        print("Preparing " + catalog.building, flush=True)
        time.sleep(10)
    print(json.dumps(catalog.list(), ensure_ascii=False))
    raise SystemExit(1 if catalog.error else 0)
