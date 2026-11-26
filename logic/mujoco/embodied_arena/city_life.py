"""Layered urban expansion, branched foliage, warm advertisements and street life."""

import xml.etree.ElementTree as ET

import numpy as np

from .city import VENUES, beam, geom, numbers
from .city_art import ADVERTS


def material(assets, name, rgba, emission=0.05, specular=0.2):
    return ET.SubElement(
        assets,
        "material",
        name="city_" + name,
        rgba=numbers(rgba),
        emission=str(emission),
        specular=str(specular),
        shininess=".35",
    )


def advert(parent, name, key, pos, width=1.2, height=1.6, yaw=0, group=3):
    body = ET.SubElement(
        parent,
        "body",
        name=name,
        pos=numbers(pos),
        quat=numbers((np.cos(yaw / 2), 0, 0, np.sin(yaw / 2))),
    )
    geom(
        body,
        name + "_case",
        size=(width / 2 + 0.065, 0.045, height / 2 + 0.065),
        material="dark",
        solid=False,
        group=group,
    )
    geom(
        body,
        name + "_screen",
        pos=(0, -0.054, 0),
        size=(width / 2, height / 2, 0.006),
        material="ad_" + key,
        solid=False,
        group=group,
        xyaxes=(1, 0, 0, 0, 0, 1),
    )
    accent = (
        "gold"
        if key in ("ramen", "tea", "repair")
        else "red"
        if key in ("music", "night")
        else "cyan"
    )
    for side in (-1, 1):
        beam(
            body,
            name + f"_edge_{side}",
            (side * (width / 2 + 0.045), -0.06, -height / 2),
            (side * (width / 2 + 0.045), -0.06, height / 2),
            0.018,
            accent,
        ).set("group", str(group))
    return body


def facade(parent, name, pos, width, depth, height, index, group=3):
    x, y, z = pos
    for face, center, half_width, yaw in [
        ("front", (x, y - depth - 0.015, z), width, 0),
        ("back", (x, y + depth + 0.015, z), width, np.pi),
        ("right", (x + width + 0.015, y, z), depth, np.pi / 2),
        ("left", (x - width - 0.015, y, z), depth, -np.pi / 2),
    ]:
        geom(
            parent,
            name + "_" + face,
            pos=center,
            size=(half_width, height / 2, 0.006),
            material=f"facade_{index}",
            solid=False,
            group=group,
            xyaxes=(np.cos(yaw), np.sin(yaw), 0, 0, 0, 1),
        )


def tower(parent, name, x, y, base, height, width, depth, index, group=3):
    style = ("steelblue", "maroon", "stone", "olive", "bronze", "steelblue")[index % 6]
    split = 0.68 * height
    geom(
        parent,
        name + "_podium",
        pos=(x, y, base + split / 2),
        size=(width, depth, split / 2),
        material=style,
        solid=group == 5,
        group=group,
    )
    facade(
        parent, name + "_podium_face", (x, y, base + split / 2), width, depth, split, index, group
    )
    upper_width = width * (0.72 + 0.08 * (index % 2))
    upper_depth = depth * 0.77
    geom(
        parent,
        name + "_crown",
        pos=(x, y, base + split + (height - split) / 2),
        size=(upper_width, upper_depth, (height - split) / 2),
        material=style,
        solid=group == 5,
        group=group,
    )
    facade(
        parent,
        name + "_crown_face",
        (x, y, base + split + (height - split) / 2),
        upper_width,
        upper_depth,
        height - split,
        index,
        group,
    )
    for level, w, d in ((base + split, width, depth), (base + height, upper_width, upper_depth)):
        geom(
            parent,
            name + f"_ledge_{level}",
            pos=(x, y, level + 0.08),
            size=(w + 0.12, d + 0.10, 0.09),
            material="metal",
            solid=False,
            group=group,
        )
    accent = ("cyan", "purple", "gold", "red", "gold", "mint")[index]
    for side in (-1, 1):
        beam(
            parent,
            name + f"_fin_{side}",
            (x + side * width, y - depth - 0.04, base + 0.3),
            (x + side * width, y - depth - 0.04, base + split),
            0.026,
            accent,
        ).set("group", str(group))
    if index % 2 == 0:
        geom(
            parent,
            name + "_mast",
            "cylinder",
            (x, y, base + height + 1.0),
            (0.055, 1.0),
            "metal",
            False,
            group,
        )
        geom(
            parent,
            name + "_beacon",
            "sphere",
            (x, y, base + height + 2.05),
            (0.09,),
            "red",
            False,
            group,
        )


def leaf_mesh(assets):
    from .city_meshes import prepare_trees

    prepare_trees(assets)


def tree(parent, name, u, v, base=0, height=2.8, seed=0, autumn=False):
    from .city_meshes import draw_tree

    draw_tree(parent, name, u, v, base, height, seed, autumn)


def lantern(parent, name, pos, red=True):
    x, y, z = pos
    accent = "red" if red else "gold"
    beam(parent, name + "_hanger", (x, y, z + 0.3), (x, y, z + 0.52), 0.009, "ink")
    geom(parent, name + "_shade", "ellipsoid", (x, y, z), (0.13, 0.13, 0.21), accent, False)
    for zoff in (-0.2, 0.2):
        geom(
            parent,
            name + f"_cap_{zoff}",
            "cylinder",
            (x, y, z + zoff),
            (0.075, 0.022),
            "bronze",
            False,
        )
    for a in np.linspace(0, 2 * np.pi, 6, endpoint=False):
        beam(
            parent,
            name + f"_rib_{a}",
            (x + 0.075 * np.cos(a), y + 0.075 * np.sin(a), z - 0.18),
            (x + 0.075 * np.cos(a), y + 0.075 * np.sin(a), z + 0.18),
            0.006,
            "bronze",
        )
    beam(parent, name + "_tassel", (x, y, z - 0.2), (x, y, z - 0.38), 0.012, "gold")


def enrich_city(assets, world, builder):
    colors = {
        "gold": ((1, 0.61, 0.16, 1), 0.85),
        "red": ((1, 0.105, 0.075, 1), 0.8),
        "bronze": ((0.32, 0.23, 0.16, 1), 0.05),
        "maroon": ((0.20, 0.10, 0.14, 1), 0.05),
        "stone": ((0.34, 0.32, 0.35, 1), 0.04),
        "steelblue": ((0.12, 0.18, 0.28, 1), 0.05),
        "olive": ((0.18, 0.21, 0.20, 1), 0.04),
        "bark": ((0.18, 0.14, 0.14, 1), 0.03),
        "leaf_dark": ((0.035, 0.16, 0.10, 1), 0.04),
        "leaf_mid": ((0.10, 0.32, 0.15, 1), 0.04),
        "leaf_light": ((0.22, 0.42, 0.18, 1), 0.04),
        "leaf_gold": ((0.61, 0.40, 0.12, 1), 0.06),
    }
    for name, (rgba, emission) in colors.items():
        material(assets, name, rgba, emission)
    for index in range(3, 6):
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
            emission=".28",
            specular=".3",
        )
    for key in ADVERTS:
        ET.SubElement(
            assets, "texture", name="city_ad_" + key, type="2d", file=f"city_ad_{key}.png"
        )
        ET.SubElement(
            assets,
            "material",
            name="city_ad_" + key,
            texture="city_ad_" + key,
            emission=".75",
            specular=".1",
        )
    # Near buildings rise directly above recessed retail podiums.
    heights = {
        "market": 18.0,
        "charge": 12.0,
        "cafe": 13.0,
        "lab": 23.0,
        "station": 17.0,
        "tea": 12.0,
        "noodle": 9.0,
        "arcade": 21.0,
    }
    styles = {
        "market": 0,
        "charge": 2,
        "cafe": 3,
        "lab": 1,
        "station": 5,
        "tea": 3,
        "noodle": 4,
        "arcade": 4,
    }
    ads = {
        "market": "fashion",
        "charge": "energy",
        "cafe": "music",
        "lab": "repair",
        "station": "delivery",
        "tea": "tea",
        "noodle": "ramen",
        "arcade": "night",
    }
    for venue in VENUES:
        key = venue["id"]
        parent = world.find(f"body[@name='venue_{key}']")
        w = venue["width"]
        d = venue["depth"]
        if key in heights:
            tower(
                parent,
                "near_tower_" + key,
                0,
                d * 0.66,
                5.04,
                heights[key],
                min(w / 2 - 0.5, 2.65),
                d * 0.28,
                styles[key],
                5,
            )
            advert(
                parent,
                "tower_ad_" + key,
                ads[key],
                (-min(w / 2 - 0.55, 2.65) + 0.78, d * 0.38 - 0.06, 7.3),
                1.25,
                2.5,
                group=5,
            )
        if key in ("cafe", "tea", "noodle", "arcade", "market"):
            accent = "gold" if key in ("tea", "cafe", "market") else "red"
            for g in parent.findall("geom"):
                if "portal" in g.get("name", "") or "top_neon" in g.get("name", ""):
                    g.set("material", "city_" + accent)
            for j, u in enumerate(np.linspace(-w / 2 + 0.65, w / 2 - 0.65, 5 if w > 8 else 4)):
                lantern(parent, f"{key}_lantern_{j}", (u, -0.68, 2.15), j % 2 == 0)
            advert(
                parent,
                key + "_pavement_menu",
                ads.get(key, "ramen"),
                (w / 2 - 0.45, -0.55, 1.35),
                0.65,
                1.05,
            )
        if key in ("tea", "noodle"):
            for side in (-1, 1):
                u = side * (w / 2 - 1.05)
                geom(
                    parent,
                    f"{key}_food_counter_{side}",
                    pos=(u, 3.4, 0.48),
                    size=(0.52, 0.35, 0.48),
                    material="bronze",
                    solid=True,
                )
                geom(
                    parent,
                    f"{key}_canopy_{side}",
                    pos=(u, 3.4, 2.35),
                    size=(0.68, 0.5, 0.07),
                    material="maroon",
                    solid=False,
                )
                for leg in (-1, 1):
                    beam(
                        parent,
                        f"{key}_stall_pole_{side}_{leg}",
                        (u + leg * 0.6, 3.5, 0.95),
                        (u + leg * 0.6, 3.5, 2.35),
                        0.025,
                        "bronze",
                    )
                for j in range(3):
                    geom(
                        parent,
                        f"{key}_bowl_{side}_{j}",
                        "ellipsoid",
                        (u - 0.3 + j * 0.3, 3.25, 1.03),
                        (0.10, 0.10, 0.055),
                        "ceramic",
                        False,
                    )
                advert(parent, f"{key}_stall_menu_{side}", ads[key], (u, 3.42, 1.72), 0.72, 1.0)
                # A small serving automaton behind the counter adds everyday scale.
                geom(
                    parent,
                    f"{key}_vendor_body_{side}",
                    pos=(u, 3.95, 1.0),
                    size=(0.16, 0.12, 0.27),
                    material="titanium",
                    solid=False,
                )
                geom(
                    parent,
                    f"{key}_vendor_head_{side}",
                    "sphere",
                    (u, 3.95, 1.48),
                    (0.14,),
                    "ceramic",
                    False,
                )
                beam(
                    parent,
                    f"{key}_vendor_visor_{side}",
                    (u - 0.1, 3.80, 1.48),
                    (u + 0.1, 3.80, 1.48),
                    0.025,
                    "cyan",
                )
        elif key == "station":
            for side in (-1, 1):
                geom(
                    parent,
                    f"station_bench_{side}",
                    pos=(side * 1.2, 2.4, 0.3),
                    size=(0.45, 0.22, 0.3),
                    material="seat",
                    solid=True,
                )
            geom(
                parent,
                "station_ticket_machine",
                pos=(0, 4.7, 0.75),
                size=(0.35, 0.3, 0.75),
                material="panel",
                solid=True,
            )
            advert(parent, "station_ticket_screen", "delivery", (0, 4.38, 1.05), 0.55, 0.73)
        elif key == "arcade":
            for j, u in enumerate((-1.4, 0, 1.4)):
                geom(
                    parent,
                    f"arcade_machine_{j}",
                    pos=(u, 3.0, 0.75),
                    size=(0.3, 0.3, 0.75),
                    material="maroon",
                    solid=True,
                )
                advert(
                    parent,
                    f"arcade_game_screen_{j}",
                    ("music", "night", "fashion")[j],
                    (u, 2.67, 1.13),
                    0.51,
                    0.68,
                )
    # Three skyline layers: readable near podiums, staggered mid towers, far silhouettes.
    rng = np.random.default_rng(903)
    for layer, ybase, xrange, spacing, hmin, hmax in [
        (0, 23.5, (-41, 43), 6.5, 15, 29),
        (1, 44.0, (-57, 60), 7.5, 24, 47),
    ]:
        for side in (-1, 1):
            for i, x in enumerate(np.arange(*xrange, spacing)):
                y = side * (
                    (60.0 if layer == 0 else 80.0) if side > 0 else ybase
                ) + side * rng.uniform(-1.2, 2.0)
                tower(
                    world,
                    f"skyline_l{layer}_{side}_{i}",
                    float(x) + rng.uniform(-1.0, 1.0),
                    y,
                    0,
                    rng.uniform(hmin, hmax),
                    rng.uniform(1.6, 2.65),
                    rng.uniform(1.3, 2.3),
                    int(rng.integers(6)),
                )
    for side in (-1, 1):
        for i, y in enumerate(np.linspace(-26, 67, 8)):
            tower(
                world,
                f"skyline_edge_{side}_{i}",
                side * (40 + rng.uniform(0, 5)),
                float(y),
                0,
                rng.uniform(18, 38),
                2.2,
                2.0,
                int(rng.integers(6)),
            )
    # Elevated rail and a second distant bridge enrich the background silhouettes.
    for side in (-1, 1):
        beam(
            world,
            f"skyrail_track_{side}",
            (-45, 53 + side * 0.75, 10),
            (45, 53 + side * 0.75, 10),
            0.09,
            "metal",
        )
        beam(
            world,
            f"skyrail_light_{side}",
            (-45, 53 + side * 0.80, 10.05),
            (45, 53 + side * 0.80, 10.05),
            0.032,
            "gold",
        )
    for x in np.arange(-42, 45, 12):
        geom(
            world,
            f"skyrail_pier_{x}",
            pos=(x, 53, 4.8),
            size=(0.32, 0.42, 4.8),
            material="steelblue",
            solid=False,
        )
    for side in (-1, 1):
        beam(
            world,
            f"distant_bridge_{side}",
            (-30, -30 + side * 0.5, 16),
            (32, -30 + side * 0.5, 16),
            0.11,
            "panel",
        )
        beam(
            world,
            f"distant_bridge_neon_{side}",
            (-30, -30 + side * 0.5, 16.12),
            (32, -30 + side * 0.5, 16.12),
            0.026,
            "red",
        )
    # True leaf geometry replaces all bubble-shaped park crowns.
    leaf_mesh(assets)
    for parent in world.iter("body"):
        for g in list(parent.findall("geom")):
            n = g.get("name", "")
            if n.startswith(("tree_", "park_leaf_", "park_tree_circuit_")) or (
                n.startswith("street_planter_") and n.endswith("_leaves")
            ):
                parent.remove(g)
    park = world.find("body[@name='venue_park']")
    for side in (-1, 1):
        for i, v in enumerate((1.4, 4.6)):
            tree(
                park,
                f"park_botanical_{side}_{i}",
                side * 3.7,
                v,
                height=2.9,
                seed=i + side * 17 + 40,
                autumn=i == 1,
            )
    # Ground-level ads are attached to buildings rather than closing the sidewalk.
    for i, (x, y, yaw, key) in enumerate(
        [
            (-17, 5.4, 0, "delivery"),
            (15.5, -5.4, np.pi, "night"),
            (-6.7, -5.4, np.pi, "tea"),
            (5.0, 5.4, 0, "energy"),
        ]
    ):
        advert(world, f"street_ad_{i}", key, (x, y, 2.6), 1.1, 1.7, yaw)
    for side in (-1, 1):
        advert(
            world,
            f"district_end_ad_{side}",
            "delivery" if side < 0 else "night",
            (side * 30.4, 0, 2.3),
            4.8,
            2.3,
            -side * np.pi / 2,
        )
        for y in (-2.5, 2.5):
            beam(
                world,
                f"district_end_ad_post_{side}_{y}",
                (side * 30.43, y, 0.15),
                (side * 30.43, y, 3.6),
                0.045,
                "bronze",
            )
    # Warm spill lights supplement the existing blue/purple district lighting.
    existing = world.find("light[@name='city_glow_4']")
    if existing is not None:
        existing.set("diffuse", ".50 .23 .14")
    for name, x in (("market_warm", 22), ("tea_warm", -23)):
        ET.SubElement(
            world,
            "light",
            name=name,
            pos=numbers((x, -6.4, 3.5)),
            dir="0 0 -1",
            diffuse=".55 .28 .11",
            attenuation="1 .25 .12",
            castshadow="false",
        )
