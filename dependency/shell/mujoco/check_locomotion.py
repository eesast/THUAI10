"""Headless transfer validation, using real dynamics and no supporting forces."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str((Path(__file__).resolve().parents[3] / "logic/mujoco")))

import mujoco
import numpy as np
from embodied_arena.config import MatchConfig
from embodied_arena.locomotion import HolosomaWalking
from embodied_arena.scene import make_world


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=20)
    parser.add_argument("--speed", type=float, default=0.25)
    args = parser.parse_args()
    config = MatchConfig()
    model, data, robots, _ = make_world(config, count=1, room=False)
    robot = robots[0]
    policy = HolosomaWalking()
    heights = []
    for step in range(round(args.seconds / config.physics_dt)):
        if step % 10 == 0:
            target = robot.home.copy()
            command = [args.speed if data.time > 2 else 0, 0, 0]
            target = policy.act(
                data.qpos[robot.q],
                data.qvel[robot.v],
                data.qvel[robot.root_v + 3 : robot.root_v + 6],
                data.qpos[robot.root_q + 3 : robot.root_q + 7],
                data.time,
                command,
            )
            data.ctrl[robot.actuators] = np.clip(target, robot.limits[:, 0], robot.limits[:, 1])
            heights.append(float(data.qpos[robot.root_q + 2]))
        mujoco.mj_step(model, data)
    report = {
        "seconds": args.seconds,
        "command_speed": args.speed,
        "min_pelvis_height": min(heights),
        "final_position": data.qpos[robot.root_q : robot.root_q + 3].tolist(),
        "final_quaternion": data.qpos[robot.root_q + 3 : robot.root_q + 7].tolist(),
        "finite": bool(np.isfinite(data.qpos).all()),
        "standing": bool(min(heights) > 0.5),
    }
    destination = Path("artifacts/validation")
    destination.mkdir(parents=True, exist_ok=True)
    (destination / f"locomotion_{args.speed:g}.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report))
    if not report["standing"] or not report["finite"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
