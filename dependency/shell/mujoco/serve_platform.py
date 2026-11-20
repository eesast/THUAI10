"""Windowless entry point for the on-demand Windows background task."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main():
    project_root = Path(__file__).resolve().parents[3] / "logic/mujoco"
    os.chdir(project_root)
    sys.path.insert(0, str(project_root))
    data = Path(os.environ.get("ARENA_DATA", project_root / "var/platform")).resolve()
    data.mkdir(parents=True, exist_ok=True)
    # pythonw has no console streams. Install UTF-8 logs before uvicorn creates
    # its logging formatters, and retain exceptions from startup failures.
    original_stdout, original_stderr = sys.stdout, sys.stderr
    try:
        with (data / "service.out.log").open("a", encoding="utf-8", buffering=1) as stdout:
            with (data / "service.err.log").open("a", encoding="utf-8", buffering=1) as stderr:
                sys.stdout, sys.stderr = stdout, stderr
                try:
                    from embodied_arena.platform.__main__ import main as serve

                    serve()
                except BaseException:
                    import traceback

                    traceback.print_exc()
                    raise
    finally:
        sys.stdout, sys.stderr = original_stdout, original_stderr


if __name__ == "__main__":
    main()
