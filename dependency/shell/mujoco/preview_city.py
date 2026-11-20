"""Render a real-physics city tour, static views and developer layout checks."""

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str((Path(__file__).resolve().parents[3] / "logic/mujoco")))

from embodied_arena.city import VENUES, hiding_spots
from embodied_arena.city_validation import draw_layout, validate_layout
from embodied_arena.config import MatchConfig
from embodied_arena.display import save_gif
from embodied_arena.engine import Arena
from embodied_arena.policies import WalkInPlace
from PIL import Image, ImageDraw, ImageFont


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="artifacts/cyber_city")
    parser.add_argument("--no-tour", action="store_true")
    args = parser.parse_args()
    path = Path(args.output)
    path.mkdir(parents=True, exist_ok=True)
    tour = [
        ("city_hero", "双街区 · 宽度 66 米 / 20 个可进入区域", 2.0),
        ("neon_street", "霓虹大道 · 蓝紫高楼与未来交通", 2.0),
        ("living_street", "烟火生活街 · 饮品 / 小吃 / 日常店铺", 3.0),
        ("street_furniture", "行道树 / 木质长椅 / 街牌 / 垃圾桶", 2.0),
        ("directory", "公共导览牌 · 两条商业街及日常店铺", 2.0),
        ("hotel_front", "云栖酒店 · 大堂 / 前台 / 行李寄存", 1.0),
        ("junction", "两条主街由连接路与后巷相通", 2.0),
        *[
            ("inside_" + v["id"], v["title"] + " · 可进入空间与遮挡藏点", 1.0)
            for v in VENUES
            if v.get("road_y") == 30.0
        ],
    ]
    duration = sum(section[2] for section in tour)
    arena = Arena(replace(MatchConfig.load(), scene="cyber_city", duration=duration), cameras=False)
    try:
        report = validate_layout(arena.model, arena.data)
        (path / "layout_validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        (path / "layout_metadata.json").write_text(
            json.dumps(
                {"venues": VENUES, "hide_spots": hiding_spots(), "targets": arena.targets},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        draw_layout(arena.model, arena.data, path / "layout.png")
        if (
            report["reachable_spots"] != len(hiding_spots())
            or report["visible_spots"] != len(hiding_spots())
            or not all(report["venues"].values())
            or not all(report["entrance_approaches"].values())
            or not all(report["spawn_clear"])
            or not all(r["clear"] for r in report["pedestrian_routes"].values())
        ):
            raise RuntimeError(
                "City layout contains a blocked route, spawn, approach or search position; see layout_validation.json"
            )
        for camera in [
            "city_hero",
            "overview",
            "aerial",
            "street",
            "neon_street",
            "living_street",
            "food_street",
            "street_furniture",
            "directory",
            "leisure_square",
            "hotel_front",
            "junction",
            "traffic",
            "skyline",
            "night_market",
            "west_plaza",
            "drone_sky",
            "park_trees",
            *["inside_" + v["id"] for v in VENUES],
        ]:
            Image.fromarray(arena.overview(1440, 900, camera)).save(path / f"{camera}.png")
            print("Rendered", camera, flush=True)
        if args.no_tour:
            return
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 19)
        except OSError:
            font = ImageFont.load_default()
        policies = [WalkInPlace(player_id=i) for i in (0, 1)]
        frames = []
        for index in range(round(duration * 5) + 1):
            target_time = index / 5
            while arena.time + 0.00001 < target_time:
                arena.step([policies[i].act(arena.observation(i)) for i in (0, 1)])
            boundary = 0.0
            for camera, label, section_duration in tour:
                boundary += section_duration
                if target_time < boundary:
                    break
            image = Image.fromarray(arena.overview(960, 600, camera))
            draw = ImageDraw.Draw(image)
            draw.rectangle((0, 0, 960, 42), fill="#0b1026")
            draw.text((20, 9), label, font=font, fill="#d5dbff")
            draw.text((790, 9), f"t={arena.time:.1f}s", font=font, fill="#80eaff")
            frames.append(image)
        save_gif(frames, path / "city_tour.gif", 0.2)
        arena.save(path / "tour_record")
        print("Tour saved", path.resolve(), flush=True)
    finally:
        arena.close()


if __name__ == "__main__":
    main()
