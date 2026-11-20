"""Controlled physical contact trial; initial test pose is placed on a car lane."""

import json
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str((Path(__file__).resolve().parents[3] / "logic/mujoco")))

import mujoco
import numpy as np
from embodied_arena.config import MatchConfig
from embodied_arena.display import save_gif
from embodied_arena.engine import Arena
from embodied_arena.policies import WalkInPlace
from PIL import Image, ImageDraw, ImageFont


def main():
    path = Path("artifacts/cyber_city/traffic_check")
    path.mkdir(parents=True, exist_ok=True)
    arena = Arena(replace(MatchConfig(), duration=1.2), cameras=False)
    try:
        robot = arena.robots[0]
        arena.data.qpos[robot.root_q : robot.root_q + 3] = [-16.4, -1.25, 0.79]
        mujoco.mj_forward(arena.model, arena.data)
        arena.traces.clear()
        arena.record()
        policies = [WalkInPlace(player_id=i) for i in (0, 1)]
        frames = []
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 18)
        except OSError:
            font = ImageFont.load_default()
        for frame in range(60):
            arena.step([policies[i].act(arena.observation(i)) for i in (0, 1)])
            if frame % 4 == 0:
                image = Image.fromarray(arena.overview(960, 600, "traffic"))
                draw = ImageDraw.Draw(image)
                draw.rectangle((0, 0, 960, 40), fill="#10152b")
                draw.text(
                    (18, 9),
                    f"车辆碰撞验证 · 选手 1 生命 {arena.referee.players[0].health:g} · t={arena.time:.2f}s",
                    font=font,
                    fill="#dfdbff",
                )
                frames.append(image)
        events = [e for e in arena.referee.events if e["type"] == "traffic_collision"]
        report = {
            "health_before": arena.config.health,
            "health_after": arena.referee.players[0].health,
            "events": events,
            "finite_state": bool(np.isfinite(arena.data.qpos).all()),
            "test_initial_position": [-16.4, -1.25, 0.79],
        }
        (path / "validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        arena.save(path)
        save_gif(frames, path / "impact.gif", 0.08)
        print(json.dumps(report, indent=2))
        assert (
            events
            and arena.referee.players[0].health == arena.config.health - arena.config.traffic_damage
        )
        assert len(events) == 1 and report["finite_state"]
    finally:
        arena.close()


if __name__ == "__main__":
    main()
