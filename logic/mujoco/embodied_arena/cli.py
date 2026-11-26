from __future__ import annotations

import argparse
import json
import math
import time
from contextlib import ExitStack
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np

from .config import MatchConfig
from .display import composite, save_gif
from .engine import Arena
from .viewer import passive_viewer
from .workers import PolicyPool, load_policy

DEFAULT_POLICY = "embodied_arena.policies:DiagnosticVision"
CITY_CAMERAS = [
    "city_hero",
    "street",
    "inside_chapel",
    "inside_market",
    "inside_charge",
    "inside_park",
    "inside_cafe",
    "inside_lab",
    "aerial",
    "p0/eye",
]
CITY_EXTRA_CAMERAS = {
    ord("N"): "night_market",
    ord("D"): "drone_sky",
    ord("P"): "park_trees",
    ord("W"): "west_plaza",
    ord("S"): "inside_station",
    ord("T"): "inside_tea",
    ord("F"): "inside_noodle",
    ord("G"): "inside_arcade",
    ord("H"): "skyline",
    ord("U"): "living_street",
    ord("K"): "food_street",
    ord("L"): "hotel_front",
    ord("J"): "junction",
    ord("B"): "neon_street",
}


def run(args):
    config = MatchConfig.load(args.config)
    config = replace(
        config,
        **{
            k: v
            for k, v in {"duration": args.duration, "seed": args.seed, "scene": args.scene}.items()
            if v is not None
        },
    )
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    arena = Arena(config, cameras=not args.no_cameras)
    default_policy = (
        "embodied_arena.policies:WalkInPlace" if config.scene == "cyber_city" else DEFAULT_POLICY
    )
    specs = [args.policy_a or default_policy, args.policy_b or default_policy]
    public_config = asdict(config)
    public_config.pop("seed", None)
    camera = args.camera or ("city_hero" if config.scene == "cyber_city" else "overview")
    pending_camera = []

    def camera_key(key):
        if config.scene == "cyber_city" and ord("0") <= key <= ord("9"):
            pending_camera.append(CITY_CAMERAS[key - ord("0")])
        elif config.scene == "cyber_city" and key in CITY_EXTRA_CAMERAS:
            pending_camera.append(CITY_EXTRA_CAMERAS[key])

    pool = viewer = None
    windows = ExitStack()
    frames = []
    start = time.monotonic()
    try:
        if args.inline:
            policies = [load_policy(spec, pid, public_config) for pid, spec in enumerate(specs)]
        else:
            pool = PolicyPool(
                specs, public_config, [r.home for r in arena.robots], timeout=args.timeout
            )
        if args.viewer:
            import mujoco.viewer

            viewer = windows.enter_context(
                passive_viewer(arena.model, arena.data, key_callback=camera_key)
            )
            with viewer.lock():
                viewer.cam.type = mujoco.mjtCamera.mjCAMERA_FIXED
                viewer.cam.fixedcamid = arena.model.camera(camera).id
                viewer.opt.geomgroup[:] = [
                    1,
                    0,
                    0,
                    1,
                    1,
                    0 if camera in ("overview", "aerial") else 1,
                ]
                viewer.opt.sitegroup[:] = 0
        last_print = last_snapshot = -1
        real_start = time.monotonic()
        for _ in range(math.ceil(config.duration / config.control_dt)):
            observations = [arena.observation(pid) for pid in (0, 1)]
            if pool:
                actions = pool.act(observations)
                for event in pool.events:
                    kind = event.pop("type")
                    arena.referee.event(arena.time, kind, **event)
                pool.events.clear()
            else:
                actions = [
                    policy.act(observation)
                    for policy, observation in zip(policies, observations, strict=True)
                ]
            arena.step(actions)
            if viewer:
                if not viewer.is_running():
                    break
                if pending_camera:
                    camera = pending_camera[-1]
                    pending_camera.clear()
                    with viewer.lock():
                        viewer.cam.type = mujoco.mjtCamera.mjCAMERA_FIXED
                        viewer.cam.fixedcamid = arena.model.camera(camera).id
                        viewer.opt.geomgroup[5] = 0 if camera in ("overview", "aerial") else 1
                viewer.set_texts(
                    (
                        None,
                        None,
                        "Time\nP1 score / HP\nP2 score / HP",
                        f"{arena.time:.1f} / {config.duration:g}\n{arena.referee.players[0].score:g} / {arena.referee.players[0].health:g}\n{arena.referee.players[1].score:g} / {arena.referee.players[1].health:g}",
                    )
                )
                if config.scene == "cyber_city":
                    viewer.set_texts(
                        [
                            (
                                None,
                                None,
                                "Time\nP1 score / HP\nP2 score / HP",
                                f"{arena.time:.1f} / {config.duration:g}\n{arena.referee.players[0].score:g} / {arena.referee.players[0].health:g}\n{arena.referee.players[1].score:g} / {arena.referee.players[1].health:g}",
                            ),
                            (
                                mujoco.mjtFontScale.mjFONTSCALE_100,
                                mujoco.mjtGridPos.mjGRID_BOTTOMLEFT,
                                "0 BOTH STREETS | 1 STREET | 2-7 INTERIORS | 8 MAP | 9 EYE\nU LIVING STREET | K FOOD | L HOTEL | J JUNCTION | B NEON\nN MARKET | D DRONES | P TREES | W WEST | H SKYLINE\nS STATION | T MIXUE | F FOOD HALL | G ARCADE",
                                "",
                            ),
                        ]
                    )
                viewer.sync()
            second = int(arena.time + 1e-8)
            if second != last_print:
                last_print = second
                print(
                    f"t={arena.time:5.1f}  score={[p.score for p in arena.referee.players]}  hp={[p.health for p in arena.referee.players]}",
                    flush=True,
                )
            if args.gif and second != last_snapshot:
                last_snapshot = second
                frame = composite(arena)
                frames.append(frame.resize((720, 570)))
            if args.realtime:
                delay = arena.time - (time.monotonic() - real_start)
                if delay > 0:
                    time.sleep(delay)
        result = arena.save(output)
        (output / "submissions.json").write_text(
            json.dumps(
                {"policies": specs, "runner": "inline" if args.inline else "independent_processes"},
                indent=2,
            ),
            encoding="utf-8",
        )
        if not args.no_preview:
            composite(arena).save(output / "preview.png")
        if args.gif:
            save_gif(frames, output / "match.gif")
        result["wall_seconds"] = round(time.monotonic() - start, 2)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print(f"Saved: {output.resolve()}")
    finally:
        windows.close()
        if pool:
            pool.close()
        arena.close()


def replay(args):
    import mujoco.viewer

    from .scene import load_model

    directory = Path(args.directory)
    xml = (directory / "scene.xml").read_text(encoding="utf-8")
    model = load_model(xml)
    camera = args.camera or ("city_hero" if "city_sky" in xml else "overview")
    pending_camera = []

    def camera_key(key):
        if "city_sky" in xml and ord("0") <= key <= ord("9"):
            pending_camera.append(CITY_CAMERAS[key - ord("0")])
        elif "city_sky" in xml and key in CITY_EXTRA_CAMERAS:
            name = CITY_EXTRA_CAMERAS[key]
            if mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, name) >= 0:
                pending_camera.append(name)

    data = mujoco.MjData(model)
    with np.load(directory / "trajectory.npz", allow_pickle=False) as record:
        with passive_viewer(model, data, key_callback=camera_key) as viewer:
            with viewer.lock():
                viewer.cam.type = mujoco.mjtCamera.mjCAMERA_FIXED
                viewer.cam.fixedcamid = model.camera(camera).id
                viewer.opt.geomgroup[:] = [
                    1,
                    0,
                    0,
                    1,
                    1,
                    0 if camera in ("overview", "aerial") else 1,
                ]
                viewer.opt.sitegroup[:] = 0
            stride = max(1, round(args.speed))
            indices = list(range(0, len(record["time"]), stride))
            if indices[-1] != len(record["time"]) - 1:
                indices.append(len(record["time"]) - 1)
            replay_start = time.monotonic()
            for index in indices:
                if not viewer.is_running():
                    break
                if pending_camera:
                    camera = pending_camera[-1]
                    pending_camera.clear()
                    with viewer.lock():
                        viewer.cam.type = mujoco.mjtCamera.mjCAMERA_FIXED
                        viewer.cam.fixedcamid = model.camera(camera).id
                        viewer.opt.geomgroup[5] = 0 if camera in ("overview", "aerial") else 1
                t = record["time"][index]
                qpos = record["qpos"][index]
                qvel = record["qvel"][index]
                stats = record["health_score"][index]
                data.qpos[:] = qpos
                data.qvel[:] = qvel
                if "mocap_pos" in record:
                    data.mocap_pos[:] = record["mocap_pos"][index]
                    data.mocap_quat[:] = record["mocap_quat"][index]
                mujoco.mj_forward(model, data)
                viewer.set_texts(
                    (
                        None,
                        None,
                        "REPLAY\nTime\nP1 score / HP\nP2 score / HP",
                        f"\n{t:.2f}\n{stats[0, 1]:g} / {stats[0, 0]:g}\n{stats[1, 1]:g} / {stats[1, 0]:g}",
                    )
                )
                viewer.sync()
                time.sleep(max(0.0, float(t) / args.speed - (time.monotonic() - replay_start)))


def main():
    parser = argparse.ArgumentParser(description="G1 visual search competition prototype")
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run")
    r.add_argument("--config")
    r.add_argument("--duration", type=float)
    r.add_argument("--seed", type=int)
    r.add_argument("--scene", choices=["room", "cyber_city"])
    r.add_argument("--camera", help="Named spectator camera, e.g. city_hero, street, inside_market")
    r.add_argument("--output", default="artifacts/latest")
    r.add_argument("--policy-a")
    r.add_argument("--policy-b")
    r.add_argument("--timeout", type=float, default=1.0)
    r.add_argument("--viewer", action="store_true")
    r.add_argument("--realtime", action="store_true")
    r.add_argument(
        "--inline", action="store_true", help="Trusted debug only; runs policies in parent"
    )
    r.add_argument("--no-cameras", action="store_true", help="Physics/rule diagnostics only")
    r.add_argument("--no-preview", action="store_true")
    r.add_argument("--gif", action="store_true")
    p = sub.add_parser("replay")
    p.add_argument("directory")
    p.add_argument("--speed", type=float, default=1.0)
    p.add_argument("--camera")
    args = parser.parse_args()
    if getattr(args, "speed", 1) <= 0 or getattr(args, "timeout", 1) <= 0:
        parser.error("speed and timeout must be positive")
    return run(args) if args.command == "run" else replay(args)
