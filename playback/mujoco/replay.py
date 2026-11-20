"""Display recorded MuJoCo states without importing contestant policies."""

import sys
from pathlib import Path


def main():
    repository = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repository / "logic/mujoco"))
    from embodied_arena.cli import main as run

    sys.argv[1:] = ["replay", *sys.argv[1:]]
    run()


if __name__ == "__main__":
    main()
