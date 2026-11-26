"""Walkable neon district. Geometry, hide spots and prescribed actors share a layout."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import numpy as np

from .city_art import SIGNS, ensure_art

PALETTE = {
    "road": (0.035, 0.045, 0.085, 1),
    "paving": (0.30, 0.34, 0.45, 1),
    "wall": (0.17, 0.19, 0.31, 1),
    "panel": (0.09, 0.12, 0.22, 1),
    "metal": (0.27, 0.31, 0.43, 1),
    "dark": (0.035, 0.05, 0.10, 1),
    "glass": (0.08, 0.19, 0.30, 1),
    "seat": (0.32, 0.22, 0.43, 1),
    "cyan": (0.06, 0.78, 1, 1),
    "purple": (0.56, 0.26, 1, 1),
    "pink": (1, 0.20, 0.68, 1),
    "mint": (0.18, 0.95, 0.70, 1),
    "amber": (1, 0.64, 0.18, 1),
    "leaf": (0.06, 0.29, 0.25, 1),
}
SPAWNS = [(-16.0, -4.15, 0.79), (-13.7, -4.15, 0.79)]
CITY_BOUNDS = (-30.2, 30.2, -16.2, 49.2)
CITY_LIMITS = (-30.6, 30.6, -16.5, 49.5)
STREETS = [
    {"id": "neon", "title": "霓虹大道", "y": 0.0, "half_width": 2.7},
    {"id": "living", "title": "烟火生活街", "y": 30.0, "half_width": 3.1},
]
CONNECTORS = (-16.7, 15.6)
VENUES = [
    {"id": "chapel", "title": "流明教堂", "x": -11.4, "side": 1, "width": 7.0, "depth": 6.2},
    {
        "id": "market",
        "title": "沙县小吃 · 星港店",
        "x": -2.2,
        "side": 1,
        "width": 7.0,
        "depth": 5.7,
        "shop": "shaxian",
        "sign": "shaxian",
    },
    {"id": "charge", "title": "离子充电区", "x": 8.0, "side": 1, "width": 8.0, "depth": 5.8},
    {"id": "park", "title": "以太公园", "x": -10.0, "side": -1, "width": 10.0, "depth": 6.2},
    {
        "id": "cafe",
        "title": "瑞幸咖啡 · 南街店",
        "x": 0.8,
        "side": -1,
        "width": 7.0,
        "depth": 5.6,
        "shop": "luckin",
        "sign": "luckin",
    },
    {"id": "lab", "title": "记忆档案馆", "x": 10.5, "side": -1, "width": 7.0, "depth": 6.0},
    {"id": "station", "title": "空港驿站", "x": -23.0, "side": 1, "width": 9.0, "depth": 6.2},
    {
        "id": "tea",
        "title": "蜜雪冰城 · 金箔店",
        "x": -23.0,
        "side": -1,
        "width": 9.0,
        "depth": 6.2,
        "shop": "mixue",
        "sign": "mixue",
    },
    {"id": "noodle", "title": "金灯夜市", "x": 22.0, "side": -1, "width": 10.0, "depth": 7.0},
    {"id": "arcade", "title": "绯红机厅", "x": 22.0, "side": 1, "width": 10.0, "depth": 7.0},
    {
        "id": "mixue",
        "title": "蜜雪冰城",
        "x": -23.0,
        "side": -1,
        "width": 9.0,
        "depth": 5.4,
        "road_y": 30.0,
        "front": 6.2,
        "shop": "mixue",
    },
    {
        "id": "luckin",
        "title": "瑞幸咖啡",
        "x": -11.4,
        "side": -1,
        "width": 7.0,
        "depth": 5.4,
        "road_y": 30.0,
        "front": 6.2,
        "shop": "luckin",
    },
    {
        "id": "shaxian",
        "title": "沙县小吃",
        "x": -2.2,
        "side": -1,
        "width": 7.0,
        "depth": 5.4,
        "road_y": 30.0,
        "front": 6.2,
        "shop": "shaxian",
    },
    {
        "id": "skewers",
        "title": "老街烤串",
        "x": 8.0,
        "side": -1,
        "width": 8.0,
        "depth": 5.4,
        "road_y": 30.0,
        "front": 6.2,
        "shop": "skewers",
    },
    {
        "id": "hardware",
        "title": "邻里五金店",
        "x": 22.0,
        "side": -1,
        "width": 10.0,
        "depth": 5.4,
        "road_y": 30.0,
        "front": 6.2,
        "shop": "hardware",
    },
    {
        "id": "hotel",
        "title": "云栖酒店",
        "x": -23.0,
        "side": 1,
        "width": 9.0,
        "depth": 5.8,
        "road_y": 30.0,
        "front": 6.2,
        "shop": "hotel",
    },
    {
        "id": "netcafe",
        "title": "星际网吧",
        "x": -11.4,
        "side": 1,
        "width": 7.0,
        "depth": 5.8,
        "road_y": 30.0,
        "front": 6.2,
        "shop": "netcafe",
    },
    {
        "id": "tanghulu",
        "title": "巷口糖葫芦",
        "x": -2.2,
        "side": 1,
        "width": 7.0,
        "depth": 5.8,
        "road_y": 30.0,
        "front": 6.2,
        "shop": "tanghulu",
    },
    {
        "id": "convenience",
        "title": "便利蜂巢 · 24H",
        "x": 8.0,
        "side": 1,
        "width": 8.0,
        "depth": 5.8,
        "road_y": 30.0,
        "front": 6.2,
        "shop": "convenience",
    },
    {
        "id": "laundry",
        "title": "净界自助洗衣",
        "x": 22.0,
        "side": 1,
        "width": 10.0,
        "depth": 5.8,
        "road_y": 30.0,
        "front": 6.2,
        "shop": "laundry",
    },
]


def numbers(values):
    return " ".join(f"{float(v):.8g}" for v in values)


def add_camera(world, name, pos, target, fovy=55):
    p = np.array(pos, dtype=float)
    direction = np.array(target, dtype=float) - p
    direction /= np.linalg.norm(direction)
    right = np.cross(direction, [0, 0, 1])
    right /= np.linalg.norm(right)
    up = np.cross(right, direction)
    ET.SubElement(
        world, "camera", name=name, pos=numbers(pos), xyaxes=numbers([*right, *up]), fovy=str(fovy)
    )


def geom(
    parent,
    name,
    kind="box",
    pos=(0, 0, 0),
    size=(0.1, 0.1, 0.1),
    material="wall",
    solid=True,
    group=None,
    **kwargs,
):
    attributes = {
        "name": name,
        "type": kind,
        "pos": numbers(pos),
        "size": numbers(size),
        "material": "city_" + material,
        "group": str(group if group is not None else (0 if solid else 3)),
    }
    if not solid:
        attributes.update(contype="0", conaffinity="0", mass="0")
    attributes.update(
        {
            key: (numbers(value) if isinstance(value, (list, tuple, np.ndarray)) else str(value))
            for key, value in kwargs.items()
        }
    )
    return ET.SubElement(parent, "geom", **attributes)


def beam(parent, name, start, end, radius=0.025, material="cyan", solid=False):
    return geom(
        parent,
        name,
        "capsule",
        size=(radius,),
        material=material,
        solid=solid,
        fromto=[*start, *end],
    )


def ring(parent, name, center, radius, material="cyan", segments=32, thickness=0.025, tilt=0):
    x, y, z = center
    for i in range(segments):
        a, b = 2 * np.pi * i / segments, 2 * np.pi * (i + 1) / segments
        p = [
            x + radius * np.cos(a),
            y + radius * np.sin(a) * np.cos(tilt),
            z + radius * np.sin(a) * np.sin(tilt),
        ]
        q = [
            x + radius * np.cos(b),
            y + radius * np.sin(b) * np.cos(tilt),
            z + radius * np.sin(b) * np.sin(tilt),
        ]
        beam(parent, f"{name}_{i}", p, q, thickness, material)


def world_position(venue, u, v, z=0):
    s = venue["side"]
    return np.array(
        [venue["x"] + s * u, venue.get("road_y", 0.0) + s * (venue.get("front", 5.7) + v), z]
    )


def hiding_spots():
    spots = []
    # Each search pose is a walkable point facing a shelf, screen or planter.
    layouts = {
        "chapel": [
            (-2.5, 2.3, 0.64, -1.6, 2.3),
            (2.45, 4.3, 0.85, 1.65, 4.45),
            (0, 5.15, 1.0, 0, 4.25),
            (-2.5, 4.65, 0.75, -1.6, 4.65),
        ],
        "market": [
            (-2.6, 2.3, 0.9, -1.55, 2.3),
            (2.55, 4.2, 0.9, 1.5, 4.2),
            (-0.8, 4.85, 1.0, -0.8, 3.9),
            (2.5, 1.3, 0.62, 1.5, 1.3),
        ],
        "charge": [
            (-2.8, 2.3, 0.9, -1.8, 2.3),
            (2.75, 4.55, 0.8, 1.7, 4.55),
            (0, 4.9, 0.85, 0, 3.9),
            (-2.7, 4.65, 0.65, -1.7, 4.65),
        ],
        "park": [
            (-3.7, 2.2, 0.7, -2.6, 2.2),
            (3.6, 4.7, 0.65, 2.5, 4.7),
            (0, 5.1, 0.8, 0, 4.1),
            (-3.6, 4.7, 0.75, -2.5, 4.7),
        ],
        "cafe": [
            (-2.5, 2.25, 0.85, -1.5, 2.25),
            (2.45, 4.4, 0.85, 1.4, 4.4),
            (-0.8, 4.9, 0.95, -0.8, 3.9),
            (2.45, 1.35, 0.65, 1.5, 1.35),
        ],
        "lab": [
            (-2.5, 2.4, 0.95, -1.5, 2.4),
            (2.45, 4.7, 0.9, 1.4, 4.7),
            (0, 5.2, 1.0, 0, 4.2),
            (-2.5, 4.85, 0.65, -1.5, 4.85),
        ],
        "station": [
            (-3.4, 2.3, 0.85, -2.3, 2.3),
            (3.4, 4.4, 0.9, 2.3, 4.4),
            (0, 5.2, 0.9, 0, 4.2),
            (3.3, 1.3, 0.7, 2.2, 1.3),
        ],
        "tea": [
            (-3.4, 2.3, 0.8, -2.3, 2.3),
            (3.4, 4.4, 0.85, 2.3, 4.4),
            (0, 5.2, 0.85, 0, 4.2),
            (-3.3, 4.8, 0.65, -2.2, 4.8),
        ],
        "noodle": [
            (-3.8, 2.3, 0.85, -2.7, 2.3),
            (3.8, 5.2, 0.9, 2.7, 5.2),
            (0, 6.0, 0.85, 0, 5.0),
            (-3.8, 5.6, 0.7, -2.7, 5.6),
        ],
        "arcade": [
            (-3.8, 2.3, 0.9, -2.7, 2.3),
            (3.8, 5.2, 0.95, 2.7, 5.2),
            (0, 6.0, 1.0, 0, 5.0),
            (-3.8, 5.6, 0.75, -2.7, 5.6),
        ],
    }
    for venue in VENUES:
        w, d = venue["width"], venue["depth"]
        layout = layouts.get(
            venue["id"],
            [
                (-w / 2 + 1.05, 1.9, 0.85, -w / 2 + 2.1, 1.9),
                (w / 2 - 1.05, d - 1.1, 0.9, w / 2 - 2.1, d - 1.1),
                (0, d - 1.0, 0.9, 1.1, d - 1.0),
                (w / 2 - 1.05, 1.0, 0.7, w / 2 - 2.1, 1.0),
            ],
        )
        for index, (u, v, z, su, sv) in enumerate(layout):
            if abs(u) < 1:
                su, sv = u + 1.1, v
            spots.append(
                {
                    "id": f"{venue['id']}_{index}",
                    "zone": venue["id"],
                    "zone_title": venue["title"],
                    "position": world_position(venue, u, v, z).tolist(),
                    "search_position": world_position(venue, su, sv).tolist(),
                }
            )
    return spots


def city_targets(seed, task_set="legacy"):
    rng = np.random.default_rng(seed)
    # Every district participates; different seeds choose different recesses.
    selected = []
    for i, venue in enumerate(VENUES):
        choices = [s for s in hiding_spots() if s["zone"] == venue["id"]]
        spot = choices[int(rng.integers(len(choices)))]
        owner = [None, 0, 1][i % 3] if i < (len(VENUES) // 3) * 3 else None
        color = {None: "red", 0: "blue", 1: "green"}[owner]
        color_cn = {"red": "红色", "blue": "蓝色", "green": "绿色"}[color]
        selected.append(
            {
                "id": f"city_target_{venue['id']}",
                "owner": owner,
                "color": color,
                "text": f"进入{venue['title']}，找到并命中藏在内部的{color_cn}杯子。",
                **spot,
            }
        )
        selected[-1]["id"] = f"city_target_{venue['id']}"
    if task_set == "mixed-v1":
        from .objects import NAMES, SHAPES

        for i, target in enumerate(selected):
            target["shape"] = SHAPES[(i + seed) % len(SHAPES)]
            target["text"] = target["text"].replace("杯子", NAMES[target["shape"]])
    return selected


class Builder:
    def __init__(self, world):
        self.world = world
        self.static_colliders = []

    def box(self, parent, name, pos, size, material="wall", solid=True, group=None, **kwargs):
        return geom(
            parent, name, pos=pos, size=size, material=material, solid=solid, group=group, **kwargs
        )

    def sign(self, parent, name, kind, pos, width=2.8, height=0.64):
        self.box(
            parent,
            name + "_frame",
            pos,
            (width / 2 + 0.05, 0.045, height / 2 + 0.05),
            "dark",
            False,
        )
        # Texture is mapped on local XY, then turned upright towards local -Y.
        geom(
            parent,
            name + "_label",
            pos=(pos[0], pos[1] - 0.052, pos[2]),
            size=(width / 2, height / 2, 0.008),
            material="sign_" + kind,
            solid=False,
            euler=(np.pi / 2, 0, 0),
        )

    def shelf(self, parent, name, u, v, z=0.75, wide=0.6, depth=0.32):
        self.box(parent, name + "_base", (u, v, z / 2), (wide, depth, z / 2), "panel")
        self.box(
            parent, name + "_top", (u, v, z + 0.025), (wide + 0.04, depth + 0.04, 0.025), "metal"
        )
        beam(
            parent,
            name + "_edge",
            (u - wide, v - depth - 0.02, z),
            (u + wide, v - depth - 0.02, z),
            0.016,
            "cyan",
        )

    def planter(self, parent, name, u, v, width=0.65, depth=0.32):
        self.box(parent, name + "_box", (u, v, 0.27), (width, depth, 0.27), "panel")
        self.box(parent, name + "_leaves", (u, v, 0.65), (width * 0.86, depth * 0.8, 0.22), "leaf")
        beam(
            parent,
            name + "_rim",
            (u - width, v - depth - 0.01, 0.55),
            (u + width, v - depth - 0.01, 0.55),
            0.018,
            "mint",
        )

    def venue(self, venue):
        key = venue["id"]
        w, d = venue["width"], venue["depth"]
        parent = ET.SubElement(
            self.world,
            "body",
            name="venue_" + key,
            pos=numbers(world_position(venue, 0, 0)),
            quat="1 0 0 0" if venue["side"] == 1 else "0 0 0 1",
        )
        self.box(parent, key + "_floor", (0, d / 2, -0.025), (w / 2, d / 2, 0.025), "paving")
        if key != "park":
            self.box(parent, key + "_back", (0, d, 1.65), (w / 2, 0.14, 1.65))
            for side in (-1, 1):
                self.box(
                    parent, f"{key}_side_{side}", (side * w / 2, d / 2, 1.65), (0.14, d / 2, 1.65)
                )
                self.box(
                    parent,
                    f"{key}_front_{side}",
                    (side * (w / 4 + 0.7), 0, 1.55),
                    (w / 4 - 0.7, 0.14, 1.55),
                )
                beam(
                    parent,
                    f"{key}_portal_{side}",
                    (side * 1.4, -0.18, 0.05),
                    (side * 1.4, -0.18, 2.9),
                    0.035,
                    "cyan" if side == 1 else "purple",
                )
                self.box(
                    parent,
                    f"{key}_front_glass_{side}",
                    (side * (w / 4 + 0.7), -0.155, 1.5),
                    (w / 4 - 0.8, 0.02, 0.72),
                    "glass",
                    False,
                )
            self.box(parent, key + "_lintel", (0, 0, 3.05), (w / 2, 0.18, 0.3))
            self.box(
                parent,
                key + "_roof",
                (0, d / 2, 3.45),
                (w / 2 + 0.15, d / 2 + 0.2, 0.13),
                "panel",
                True,
                5,
            )
            for v in (-0.15, d + 0.15):
                beam(
                    parent,
                    f"{key}_roof_trim_{v}",
                    (-w / 2, v, 3.6),
                    (w / 2, v, 3.6),
                    0.025,
                    "purple",
                )
            for x in (-1.5, 1.5):
                self.box(
                    parent,
                    f"{key}_back_window_{x}",
                    (x, d + 0.15, 1.8),
                    (0.65, 0.025, 0.55),
                    "glass",
                    False,
                )
                beam(
                    parent,
                    f"{key}_back_window_light_{x}",
                    (x - 0.65, d + 0.18, 1.25),
                    (x + 0.65, d + 0.18, 1.25),
                    0.018,
                    "cyan",
                )
            for x in (-w / 2, w / 2):
                beam(
                    parent,
                    f"{key}_corner_{x}",
                    (x, d + 0.15, 0.15),
                    (x, d + 0.15, 3.5),
                    0.025,
                    "purple",
                )
            beam(
                parent,
                key + "_top_neon",
                (-w / 2, -0.2, 3.35),
                (w / 2, -0.2, 3.35),
                0.045,
                "purple",
            )
            self.sign(
                parent,
                key + "_sign",
                venue.get("sign", key),
                (0, -0.23, 2.93),
                min(5.3, w - 0.6),
                0.65,
            )
            for x in (-w / 2 + 0.5, w / 2 - 0.5):
                geom(
                    parent,
                    f"{key}_pillar_{x}",
                    "cylinder",
                    (x, d * 0.62, 1.3),
                    (0.16, 1.3),
                    "metal",
                )
                beam(
                    parent,
                    f"{key}_pillar_glow_{x}",
                    (x, d * 0.62 - 0.17, 0.2),
                    (x, d * 0.62 - 0.17, 2.45),
                    0.025,
                    "purple",
                )
            for side in (-1, 1):
                beam(
                    parent,
                    f"{key}_floor_guide_{side}",
                    (side * 1.15, 0.3, 0.022),
                    (side * 1.15, d - 0.6, 0.022),
                    0.012,
                    "cyan",
                )
        else:
            self.sign(parent, "park_sign", key, (0, -0.06, 2.7), 4.8, 0.7)
            for x in (-2.8, 2.8):
                self.box(parent, f"park_gate_{x}", (x, 0, 1.35), (0.10, 0.12, 1.35), "metal")
            self.box(parent, "park_back_hedge", (0, d, 0.45), (w / 2, 0.27, 0.45), "leaf")
            for side in (-1, 1):
                self.box(
                    parent,
                    f"park_side_hedge_{side}",
                    (side * w / 2, d / 2, 0.45),
                    (0.24, d / 2, 0.45),
                    "leaf",
                )
                for v in (1.4, 4.6):
                    u = side * 3.7
                    geom(
                        parent,
                        f"tree_{side}_{v}_trunk",
                        "cylinder",
                        (u, v, 1.05),
                        (0.1, 1.05),
                        "metal",
                    )
                    geom(
                        parent,
                        f"tree_{side}_{v}_crown",
                        "ellipsoid",
                        (u, v, 2.15),
                        (0.6, 0.62, 0.65),
                        "leaf",
                        False,
                    )
                    ring(parent, f"tree_{side}_{v}_halo", (u, v, 1.75), 0.55, "mint", 16, 0.016)
            ring(parent, "park_fountain_ring", (0, 2.7, 0.13), 0.8, "cyan", 32, 0.04)
            geom(parent, "park_fountain_basin", "cylinder", (0, 2.7, 0.12), (0.78, 0.12), "metal")
            geom(
                parent,
                "park_hologram",
                "ellipsoid",
                (0, 2.7, 0.85),
                (0.23, 0.23, 0.6),
                "cyan",
                False,
                rgba=".12 .8 1 .32",
            )
        # Accessible support surfaces for four real hide spots per venue.
        local_spots = [s for s in hiding_spots() if s["zone"] == key]
        for index, spot in enumerate(local_spots):
            world = np.array(spot["position"])
            front = world_position(venue, 0, 0)
            u = (world[0] - front[0]) * venue["side"]
            v = (world[1] - front[1]) * venue["side"]
            z = world[2] - 0.18
            self.shelf(parent, f"{key}_hiding_{index}", u, v, z, wide=0.38, depth=0.28)
            # Offset opaque screen: blocks the street view without sealing the aisle.
            self.box(
                parent,
                f"{key}_screen_{index}",
                (u, v - (0.35 if key == "chapel" and abs(u) < 1 else 0.60), 0.78),
                (0.42, 0.08, 0.78),
                "wall",
            )
        if key == "chapel":
            for v in (1.4, 3.7):
                for side in (-1, 1):
                    self.box(
                        parent, f"pew_{v}_{side}", (side * 0.9, v, 0.32), (0.35, 0.22, 0.32), "seat"
                    )
                    self.box(
                        parent,
                        f"pew_back_{v}_{side}",
                        (side * 0.9, v + 0.22, 0.66),
                        (0.35, 0.08, 0.35),
                        "metal",
                    )
            self.box(parent, "altar", (0, d - 0.7, 0.48), (0.7, 0.35, 0.48), "panel")
            beam(parent, "cross_vertical", (0, d - 0.18, 1.65), (0, d - 0.18, 2.9), 0.055, "purple")
            beam(
                parent,
                "cross_horizontal",
                (-0.5, d - 0.18, 2.48),
                (0.5, d - 0.18, 2.48),
                0.055,
                "cyan",
            )
            # Geometric pointed facade, with clerestory tubes and bell spire.
            for side in (-1, 1):
                beam(
                    parent,
                    f"chapel_gable_{side}",
                    (side * w / 2, -0.03, 3.55),
                    (0, -0.03, 5.8),
                    0.11,
                    "metal",
                )
                beam(
                    parent,
                    f"chapel_gable_light_{side}",
                    (side * w / 2, -0.15, 3.55),
                    (0, -0.15, 5.8),
                    0.034,
                    "purple",
                )
            geom(parent, "chapel_spire", "cylinder", (0, 0.8, 5.0), (0.15, 1.7), "metal", False)
        elif key == "charge":
            for x in (-2.0, 0.0, 2.0):
                self.box(parent, f"charge_pedestal_{x}", (x, 3.2, 0.7), (0.30, 0.23, 0.7), "panel")
                self.box(
                    parent, f"charge_screen_{x}", (x, 2.95, 1.1), (0.21, 0.025, 0.29), "mint", False
                )
                ring(parent, f"charge_pad_{x}", (x, 2.3, 0.025), 0.65, "mint", 24, 0.023)
        elif key in ("market", "lab"):
            self.box(parent, key + "_central_island", (-0.15, 2.5, 0.5), (0.45, 0.55, 0.5), "panel")
            beam(
                parent, key + "_central_light", (-0.6, 1.93, 0.95), (0.3, 1.93, 0.95), 0.025, "pink"
            )
            for index in range(4):
                self.box(
                    parent,
                    f"{key}_stack_{index}",
                    (-2.6, 3.5, 1.15 + index * 0.18),
                    (0.28, 0.25, 0.07),
                    "metal",
                )
        elif key == "cafe":
            for x in (-1.7, 1.65):
                geom(parent, f"cafe_table_{x}", "cylinder", (x, 3.5, 0.72), (0.42, 0.045), "metal")
                geom(
                    parent,
                    f"cafe_table_stem_{x}",
                    "cylinder",
                    (x, 3.5, 0.35),
                    (0.08, 0.35),
                    "panel",
                )
                self.box(parent, f"cafe_chair_{x}", (x, 2.9, 0.3), (0.23, 0.23, 0.3), "seat")
        return parent


def build_city(assets, world, visual, config):
    ensure_art()
    for key, rgba in PALETTE.items():
        luminous = key in ("cyan", "purple", "pink", "mint", "amber")
        ET.SubElement(
            assets,
            "material",
            name="city_" + key,
            rgba=numbers(rgba),
            emission=".85" if luminous else ".04",
            specular=".55",
            shininess=".7",
        )
    for key in SIGNS:
        ET.SubElement(
            assets, "texture", name="city_sign_" + key, type="2d", file=f"city_sign_{key}.png"
        )
        ET.SubElement(
            assets,
            "material",
            name="city_sign_" + key,
            texture="city_sign_" + key,
            emission=".7",
            specular=".1",
        )
    for index in range(3):
        ET.SubElement(
            assets,
            "texture",
            name=f"city_facade_{index}",
            type="2d",
            file=f"city_facade_{index}.png",
        )
        ET.SubElement(
            assets,
            "material",
            name=f"city_facade_{index}",
            texture=f"city_facade_{index}",
            emission=".3",
            specular=".6",
            shininess=".8",
        )
    ET.SubElement(assets, "texture", name="city_tiles", type="2d", file="city_paving.png")
    paving = next(m for m in assets.findall("material") if m.get("name") == "city_paving")
    paving.set("texture", "city_tiles")
    paving.set("texuniform", "true")
    paving.set("texrepeat", ".6 .6")
    ET.SubElement(
        assets,
        "texture",
        name="city_sky",
        type="skybox",
        builtin="gradient",
        rgb1=".012 .022 .07",
        rgb2=".15 .07 .24",
        mark="random",
        markrgb=".48 .65 .85",
        random=".0008",
        width="1024",
        height="6144",
    )
    visual.find("headlight").set("ambient", ".33 .38 .55")
    visual.find("headlight").set("diffuse", ".48 .51 .65")
    ET.SubElement(visual, "map", znear=".0007", zfar="10", fogstart=".8", fogend="3.2")
    ET.SubElement(visual, "rgba", fog=".045 .04 .12 1")
    ET.SubElement(visual, "quality", shadowsize="4096", offsamples="4")
    for light in world.findall("light"):
        world.remove(light)
    ET.SubElement(
        world,
        "light",
        name="city_moonlight",
        directional="true",
        pos="-10 -12 24",
        dir=".3 .4 -1",
        diffuse=".68 .72 .9",
        ambient=".05 .05 .10",
        castshadow="true",
    )
    ET.SubElement(
        world,
        "light",
        name="city_fill",
        directional="true",
        pos="8 10 16",
        dir="-.4 -.5 -1",
        diffuse=".34 .20 .52",
        castshadow="false",
    )
    for x, y, color in [(-10, 5, ".2 .3 .8"), (4, -6, ".4 .1 .6"), (11, 5, ".12 .45 .4")]:
        ET.SubElement(
            world,
            "light",
            name=f"city_glow_{x}",
            pos=numbers((x, y, 3.5)),
            dir="0 0 -1",
            diffuse=color,
            attenuation="1 .18 .10",
            castshadow="false",
        )
    floor = world.find("geom[@name='floor']")
    floor.set("material", "city_paving")
    floor.set("size", "70 70 .05")
    # Keep the original contact plane at z=0, but let the separate street and
    # pavement surfaces below it render instead of being covered by that plane.
    floor.set("rgba", "0 0 0 0")
    geom(world, "city_ground_underlay", "plane", (0, 0, -0.06), (100, 100, 0.05), "paving", False)
    builder = Builder(world)
    builder.box(world, "city_road", (0, 0, -0.019), (32, 2.7, 0.018), "road")
    for side in (-1, 1):
        builder.box(world, f"sidewalk_{side}", (0, side * 4.2, -0.012), (30, 1.5, 0.01), "paving")
        beam(
            world,
            f"sidewalk_light_{side}",
            (-30, side * 2.8, 0.025),
            (30, side * 2.8, 0.025),
            0.019,
            "cyan" if side > 0 else "purple",
        )
        builder.box(
            world, f"rear_promenade_{side}", (0, side * 14.1, -0.012), (30, 1.25, 0.01), "paving"
        )
        crossings = (-24, -16.7, -8, 0, 8.1, 15.6, 24)
        segments = []
        start = -30
        for crossing in crossings:
            segments.append((start, crossing - 1.1))
            start = crossing + 1.1
        segments.append((start, 30))
        for start, end in segments:
            builder.box(
                world,
                f"curb_{side}_{start}",
                ((start + end) / 2, side * 2.73, 0.055),
                ((end - start) / 2, 0.09, 0.055),
                "metal",
            )
    for x in CONNECTORS:
        builder.box(world, f"side_street_{x}", (x, 16.5, -0.019), (1.1, 32.5, 0.018), "road")
        for side in (-1, 1):
            beam(
                world,
                f"alley_guide_{x}_{side}",
                (x + side, 6.0, 0.018),
                (x + side, 24.0, 0.018),
                0.014,
                "amber",
            )
    for x in np.arange(-30, 31, 2.5):
        beam(world, f"lane_dash_{x}", (x, 0, 0.018), (x + 1.05, 0, 0.018), 0.025, "purple")
    for crossing in (-24, -16.7, -8, 0, 8.1, 15.6, 24):
        for y in np.arange(-2.5, 2.6, 0.55):
            builder.box(
                world,
                f"crosswalk_{crossing}_{y}",
                (crossing, y, 0.004),
                (0.85, 0.16, 0.004),
                "metal",
                False,
            )
        for side in (-1, 1):
            for offset in (-1.5, 1.5) if crossing == -24 else (-1.2, 1.2):
                geom(
                    world,
                    f"bollard_{crossing}_{side}_{offset}",
                    "cylinder",
                    (crossing + offset, side * 3.05, 0.37),
                    (0.09, 0.37),
                    "metal",
                )
                geom(
                    world,
                    f"bollard_light_{crossing}_{side}_{offset}",
                    "cylinder",
                    (crossing + offset, side * 3.05, 0.73),
                    (0.095, 0.035),
                    "cyan",
                    False,
                )
    for venue in VENUES:
        builder.venue(venue)
    # Street fixtures make navigation and occlusion physical, not painted.
    for x in (-17.5, -5.7, 5.4, 17):
        for side in (-1, 1):
            y = side * 5.02
            geom(world, f"lamp_{x}_{side}", "cylinder", (x, y, 2.05), (0.065, 2.05), "metal")
            beam(
                world,
                f"lamp_arm_{x}_{side}",
                (x, y, 4.1),
                (x, y - side * 0.9, 4.1),
                0.055,
                "metal",
                True,
            )
            builder.box(
                world,
                f"lamp_panel_{x}_{side}",
                (x, y - side * 0.9, 4.08),
                (0.33, 0.18, 0.035),
                "cyan",
                False,
            )
            beam(
                world,
                f"lamp_spine_{x}_{side}",
                (x, y - side * 0.07, 0.25),
                (x, y - side * 0.07, 3.85),
                0.018,
                "purple",
            )
    for index, (x, y) in enumerate([(-5.7, 4.0), (4.9, 4.0), (-4.6, -4.9), (16.7, -4.3)]):
        builder.planter(world, f"street_planter_{index}", x, y, 0.60, 0.28)
    builder.box(world, "transit_kiosk", (15.8, 4.5, 1.05), (0.6, 0.35, 1.05), "panel")
    builder.sign(world, "transit_kiosk_sign", "transit", (15.8, 4.12, 1.45), 1.08, 0.42)
    # Light gantries / street curtains above all walking clearances.
    for x in (-6.1, 15.5):
        for side in (-1, 1):
            builder.box(
                world, f"gantry_leg_{x}_{side}", (x, side * 5.35, 3.2), (0.13, 0.16, 3.2), "panel"
            )
        builder.box(world, f"gantry_beam_{x}", (x, 0, 6.35), (0.20, 5.45, 0.15), "metal", False)
        beam(
            world,
            f"gantry_neon_{x}",
            (x - 0.23, -5.2, 6.32),
            (x - 0.23, 5.2, 6.32),
            0.045,
            "purple",
        )
    # A suspended banner facing the main street; the underside stays 5m clear.
    banner = ET.SubElement(
        world, "body", name="district_banner", pos="-6.45 0 6.35", euler="0 0 -1.5707963"
    )
    builder.sign(banner, "district_banner", "district", (0, 0, 0.0), 7.8, 1.0)
    # Skyline, advertisements and natural trees are added in the expansion pass.
    geom(world, "sky_moon", "sphere", (-7, 67, 32), (3.3,), "purple", False, rgba=".34 .29 .61 1")
    ring(world, "sky_orbit", (-7, 67, 32), 4.5, "cyan", 64, 0.045, tilt=0.40)
    # Boundaries are physical and deliberately visible as low perimeter walls.
    for side in (-1, 1):
        builder.box(
            world, f"boundary_x_{side}", (side * 30.6, 16.5, 1.2), (0.12, 33.0, 1.2), "panel"
        )
        builder.box(
            world,
            f"boundary_y_{side}",
            (0, -16.5 if side < 0 else 49.5, 1.2),
            (30.6, 0.12, 1.2),
            "panel",
        )
    for camera in list(world.findall("camera")):
        if camera.get("name") == "overview":
            world.remove(camera)
    add_camera(world, "overview", (36, -25, 70), (0, 16, 0), 68)
    add_camera(world, "city_hero", (26, -18, 47), (0, 17, 3), 72)
    add_camera(world, "neon_street", (-26, -1, 4), (13, 0, 4.5), 82)
    add_camera(world, "skyline", (-29, -15, 22), (2, 2, 4.0), 74)
    add_camera(world, "street", (-16, -3.9, 1.65), (10, 1, 2.1), 70)
    add_camera(world, "traffic", (-12.5, -7, 3.5), (-16.5, -1.25, 0.8), 58)
    add_camera(world, "aerial", (-3, 7, 80), (0, 16.5, 0), 68)
    add_camera(world, "living_street", (-28, 28, 3.2), (22, 31.5, 3.2), 78)
    add_camera(world, "food_street", (-15.8, 29.0, 2.1), (-3, 23.8, 2.2), 76)
    add_camera(world, "hotel_front", (-27, 30.2, 2.4), (-22.5, 37.8, 5.2), 76)
    add_camera(world, "junction", (18.8, 14.0, 4.0), (14.9, 30.0, 3.0), 80)
    add_camera(world, "street_furniture", (-25.0, 29.3, 1.65), (-25.0, 25.55, 1.15), 80)
    add_camera(world, "directory", (13.1, 11.65, 1.57), (13.1, 13.5, 1.55), 54)
    add_camera(world, "leisure_square", (-2.0, 42.5, 1.9), (1.5, 45.5, 0.8), 76)
    add_camera(world, "night_market", (17.8, -2.2, 1.85), (24, -5.9, 3.1), 74)
    add_camera(world, "west_plaza", (-29, -3.7, 1.7), (-20, 3, 4), 76)
    add_camera(world, "drone_sky", (0, -1, 2.7), (12, 0, 10.5), 88)
    add_camera(world, "park_trees", (-12.2, -5.8, 1.6), (-13.7, -7.1, 2.0), 80)
    for venue in VENUES:
        p = world_position(venue, -0.8, 0.65, 1.4)
        target = world_position(venue, 0.3, 4.7, 1.1)
        fov = 76
        if venue.get("road_y") == 30.0:
            p = world_position(venue, 0.8, 0.8, 1.55)
            fov = 84
            kind = venue["shop"]
            if kind in ("hardware", "tanghulu", "skewers", "luckin", "mixue", "shaxian"):
                target = world_position(venue, -venue["width"] / 2 + 1.3, 3.1, 1.15)
            elif kind == "hotel":
                target = world_position(venue, -1.1, 3.0, 1.2)
            elif kind == "convenience":
                target = world_position(venue, -1.5, 3.0, 1.2)
            elif kind == "laundry":
                target = world_position(venue, 0, 3.3, 0.9)
            else:
                target = world_position(venue, 0, 3.0, 1.2)
        add_camera(world, "inside_" + venue["id"], p, target, fov)
    from .city_actors import add_actors

    add_actors(world, config.traffic_enabled)
    from .city_details import refine_city

    refine_city(assets, world, builder)
    from .city_life import enrich_city

    enrich_city(assets, world, builder)
    from .city_shops import add_living_district

    add_living_district(assets, world, builder)
    from .city_furnishings import add_street_furniture

    add_street_furniture(assets, world, builder)
    from .city_interiors import refine_interiors

    refine_interiors(assets, world)
    return builder
