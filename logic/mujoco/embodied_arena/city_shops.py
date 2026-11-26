"""Everyday businesses and the second, warmer commercial street."""

import xml.etree.ElementTree as ET

import numpy as np

from .city import VENUES, beam, geom
from .city_art import SHOP_SIGNS
from .city_life import advert, lantern, material, tower, tree


def panel(parent, name, texture, pos, width, height, group=3):
    x, y, z = pos
    geom(
        parent,
        name + "_frame",
        pos=pos,
        size=(width / 2 + 0.04, 0.035, height / 2 + 0.04),
        material="ink",
        solid=False,
        group=group,
    )
    geom(
        parent,
        name + "_image",
        pos=(x, y - 0.045, z),
        size=(width / 2, height / 2, 0.005),
        material=texture,
        solid=False,
        group=group,
        xyaxes=(1, 0, 0, 0, 0, 1),
    )


def cup(parent, name, u, v, z=1.07, iced=False):
    geom(parent, name, "cylinder", (u, v, z), (0.065, 0.085), "shop_white", False)
    geom(
        parent,
        name + "_lid",
        "cylinder",
        (u, v, z + 0.09),
        (0.071, 0.012),
        "shop_blue" if iced else "bronze",
        False,
    )
    if iced:
        beam(parent, name + "_straw", (u, v, z + 0.1), (u + 0.02, v, z + 0.26), 0.009, "red")


def table(parent, name, u, v):
    geom(parent, name + "_top", "cylinder", (u, v, 0.76), (0.35, 0.035), "shop_wood")
    geom(parent, name + "_leg", "cylinder", (u, v, 0.37), (0.06, 0.37), "bronze")
    for side in (-1, 1):
        geom(
            parent,
            name + f"_stool_{side}",
            "cylinder",
            (u + side * 0.63, v, 0.22),
            (0.18, 0.22),
            "shop_red",
        )


def sweets(parent, name, u, v, z=1.05):
    for j in range(3):
        x = u + (j - 1) * 0.16
        beam(parent, name + f"_stick_{j}", (x, v, z - 0.08), (x, v, z + 0.45), 0.01, "shop_wood")
        for k in range(3):
            geom(
                parent,
                name + f"_fruit_{j}_{k}",
                "sphere",
                (x, v, z + 0.10 + k * 0.11),
                (0.065,),
                "shop_red",
                False,
            )


def dress_shop(world, venue):
    key = venue["id"]
    kind = venue.get("shop")
    if kind is None:
        return
    parent = world.find(f"body[@name='venue_{key}']")
    w, d = venue["width"], venue["depth"]
    accent = {
        "luckin": "shop_blue",
        "mixue": "shop_red",
        "shaxian": "shop_red",
        "skewers": "bronze",
        "hardware": "olive",
        "hotel": "bronze",
        "netcafe": "shop_blue",
        "tanghulu": "shop_red",
        "convenience": "olive",
        "laundry": "shop_teal",
    }[kind]
    for g in parent.findall("geom"):
        n = g.get("name", "")
        if n in (key + "_back", key + "_lintel", key + "_side_-1", key + "_side_1"):
            g.set("material", "city_shop_cream")
        elif n.startswith(key + "_front_") and "glass" not in n:
            g.set("material", "city_" + accent)
        elif "portal" in n or n == key + "_top_neon":
            g.set(
                "material",
                "city_"
                + ("gold" if kind in ("hotel", "shaxian", "skewers", "hardware") else "white"),
            )
        elif n == key + "_awning":
            g.set("material", "city_shop_cream")
    panel(parent, key + "_daily_menu", "menu_" + kind, (w / 2 - 0.6, -0.23, 1.55), 0.85, 1.32)
    badge = parent.find(f"body[@name='tower_ad_{key}']")
    if badge is not None:
        badge.find(f"geom[@name='tower_ad_{key}_screen']").set("material", "city_menu_" + kind)
    # Existing south-street stores retain their established aisles and furniture.
    if key in ("market", "cafe", "tea"):
        if key == "market":
            for g in list(parent.findall("geom")):
                if g.get("name", "").startswith(("market_book_", "market_rear_book_shelf_")):
                    parent.remove(g)
            for j in range(3):
                geom(
                    parent,
                    f"market_dumpling_tray_{j}",
                    "ellipsoid",
                    (-0.35 + j * 0.25, 2.5, 1.055),
                    (0.11, 0.09, 0.03),
                    "shop_white",
                    False,
                )
        elif key == "cafe":
            cup(parent, "cafe_pickup_cup", -1.7, 3.5, 0.9, True)
        else:
            cup(parent, "tea_pickup_cup", 3.45, 3.4, 1.08, True)
        return
    # All larger furniture is physical; the small products are visual detail.
    left = -w / 2 + 0.75
    if kind in ("mixue", "luckin", "shaxian", "skewers", "tanghulu", "hardware", "convenience"):
        geom(
            parent,
            key + "_sales_counter",
            pos=(left, 2.8, 0.49),
            size=(0.39, 0.34, 0.49),
            material=accent,
        )
    if kind in ("mixue", "luckin"):
        geom(
            parent,
            key + "_dispenser",
            pos=(left, 2.95, 1.32),
            size=(0.28, 0.19, 0.28),
            material="shop_white",
            solid=False,
        )
        for j in range(3):
            cup(parent, key + f"_pickup_{j}", left - 0.2 + j * 0.2, 2.6, 1.08, True)
        table(parent, key + "_cafe_table", 0.4, 2.9)
        cup(parent, key + "_table_cup", 0.4, 2.9, 0.88, True)
        if kind == "mixue":
            geom(
                parent,
                key + "_cone",
                "cylinder",
                (left, 2.94, 1.82),
                (0.12, 0.14),
                "shop_wood",
                False,
            )
            geom(
                parent,
                key + "_icecream",
                "ellipsoid",
                (left, 2.94, 2.02),
                (0.17, 0.17, 0.19),
                "shop_white",
                False,
            )
    elif kind == "shaxian":
        table(parent, key + "_dining_table", 0.4, 2.8)
        for j in range(3):
            geom(
                parent,
                key + f"_dumplings_{j}",
                "ellipsoid",
                (0.2 + j * 0.17, 2.8, 0.83),
                (0.065, 0.045, 0.035),
                "shop_white",
                False,
            )
        for j in range(2):
            geom(
                parent,
                key + f"_steamer_{j}",
                "cylinder",
                (left, 2.8, 1.05 + j * 0.11),
                (0.25, 0.05),
                "shop_wood",
                False,
            )
    elif kind == "skewers":
        geom(
            parent,
            key + "_coals",
            pos=(left, 2.8, 1.005),
            size=(0.3, 0.25, 0.025),
            material="red",
            solid=False,
        )
        for j in range(4):
            x = left - 0.24 + j * 0.16
            beam(parent, key + f"_grill_bar_{j}", (x, 2.42, 1.04), (x, 3.16, 1.04), 0.014, "metal")
            for k in range(2):
                geom(
                    parent,
                    key + f"_meat_{j}_{k}",
                    pos=(x, 2.65 + k * 0.2, 1.085),
                    size=(0.055, 0.07, 0.035),
                    material="copper",
                    solid=False,
                )
        geom(
            parent,
            key + "_extractor",
            pos=(left, 2.8, 2.37),
            size=(0.55, 0.5, 0.12),
            material="bronze",
            solid=False,
        )
        table(parent, key + "_night_table", 0.5, 2.8)
    elif kind == "tanghulu":
        sweets(parent, key + "_display", left, 2.7)
        geom(
            parent,
            key + "_candy_canopy",
            pos=(left, 2.8, 2.22),
            size=(0.52, 0.48, 0.06),
            material="shop_red",
            solid=False,
        )
    elif kind == "hardware":
        geom(
            parent,
            key + "_pegboard",
            pos=(left, 3.2, 1.65),
            size=(0.55, 0.04, 0.48),
            material="shop_wood",
            solid=False,
        )
        for j in range(4):
            x = left - 0.36 + j * 0.24
            beam(parent, key + f"_tool_handle_{j}", (x, 3.14, 1.4), (x, 3.14, 1.83), 0.025, "metal")
            beam(
                parent,
                key + f"_tool_head_{j}",
                (x - 0.08, 3.14, 1.83),
                (x + 0.08, 3.14, 1.83),
                0.04,
                "metal",
            )
        for j in range(4):
            geom(
                parent,
                key + f"_pipe_{j}",
                "cylinder",
                (-3.5 + j * 0.16, d - 0.65, 0.65),
                (0.045, 0.6),
                "copper",
                False,
            )
        geom(
            parent,
            key + "_parts_crate",
            pos=(-2.8, d - 0.65, 0.3),
            size=(0.4, 0.35, 0.3),
            material="bronze",
        )
    elif kind == "hotel":
        geom(
            parent,
            key + "_reception_desk",
            pos=(-1.1, 3.0, 0.52),
            size=(1.1, 0.35, 0.52),
            material="shop_wood",
        )
        geom(parent, key + "_reception_bell", "sphere", (-0.7, 2.82, 1.1), (0.09,), "gold", False)
        panel(parent, key + "_welcome", "menu_hotel", (-1.4, d - 0.18, 1.85), 1.1, 1.55)
        for j in range(2):
            geom(
                parent,
                key + f"_luggage_{j}",
                pos=(-3.0 + j * 0.58, d - 0.7, 0.35),
                size=(0.23, 0.23, 0.35),
                material="shop_blue",
            )
        tower(parent, "near_tower_hotel", 0, d * 0.65, 5.04, 14.0, 3.35, 1.55, 3, 5)
        panel(parent, "hotel_vertical_sign", "menu_hotel", (-3.8, -0.22, 5.7), 1.1, 3.8, 5)
    elif kind == "netcafe":
        geom(parent, key + "_pc_desk", pos=(0, 2.9, 0.42), size=(1.78, 0.33, 0.42), material="ink")
        for j, u in enumerate((-1.2, 0, 1.2)):
            panel(parent, key + f"_monitor_{j}", "desktop", (u, 2.95, 1.25), 0.8, 0.5)
            geom(
                parent,
                key + f"_keyboard_{j}",
                pos=(u, 2.66, 0.87),
                size=(0.28, 0.09, 0.018),
                material="shop_blue",
                solid=False,
            )
        for j, u in enumerate((-0.6, 0.6)):
            geom(
                parent, key + f"_chair_{j}", "cylinder", (u, 1.95, 0.24), (0.18, 0.24), "shop_blue"
            )
            geom(
                parent,
                key + f"_chair_back_{j}",
                pos=(u, 1.78, 0.65),
                size=(0.19, 0.045, 0.3),
                material="shop_blue",
                solid=False,
            )
    elif kind == "convenience":
        for shelf in range(3):
            z = 1.05 + shelf * 0.28
            geom(
                parent,
                key + f"_shelf_{shelf}",
                pos=(left, 2.8, z),
                size=(0.36, 0.3, 0.025),
                material="shop_wood",
                solid=False,
            )
            for j in range(4):
                geom(
                    parent,
                    key + f"_bottle_{shelf}_{j}",
                    "cylinder",
                    (left - 0.23 + j * 0.15, 2.78, z + 0.12),
                    (0.045, 0.1),
                    "amber" if j % 2 else "mint",
                    False,
                )
        geom(
            parent,
            key + "_fridge",
            pos=(2.6, 2.8, 0.85),
            size=(0.38, 0.4, 0.85),
            material="shop_white",
        )
        panel(parent, key + "_fridge_glass", "ad_energy", (2.6, 2.36, 1.02), 0.63, 1.15)
    elif kind == "laundry":
        for j, u in enumerate((-1.4, 0, 1.4)):
            geom(
                parent,
                key + f"_washer_{j}",
                pos=(u, 3.3, 0.58),
                size=(0.5, 0.4, 0.58),
                material="shop_white",
            )
            geom(
                parent,
                key + f"_washer_door_{j}",
                "cylinder",
                (u, 2.88, 0.58),
                (0.29, 0.025),
                "shop_blue",
                False,
                euler=(np.pi / 2, 0, 0),
            )
            geom(
                parent,
                key + f"_washer_window_{j}",
                "cylinder",
                (u, 2.84, 0.58),
                (0.22, 0.015),
                "glass",
                False,
                euler=(np.pi / 2, 0, 0),
            )
            geom(
                parent,
                key + f"_washer_display_{j}",
                pos=(u + 0.22, 2.88, 0.99),
                size=(0.13, 0.015, 0.055),
                material="mint",
                solid=False,
            )
        geom(
            parent,
            key + "_laundry_basket",
            pos=(-3.4, d - 0.8, 0.3),
            size=(0.4, 0.3, 0.3),
            material="shop_wood",
        )


def add_living_district(assets, world, builder):
    colors = {
        "shop_cream": ((0.67, 0.55, 0.43, 1), 0.15),
        "shop_red": ((0.63, 0.06, 0.075, 1), 0.22),
        "shop_blue": ((0.05, 0.16, 0.43, 1), 0.12),
        "shop_wood": ((0.39, 0.23, 0.13, 1), 0.08),
        "shop_white": ((0.85, 0.83, 0.73, 1), 0.22),
        "shop_teal": ((0.08, 0.4, 0.43, 1), 0.15),
        "road_warm": ((0.08, 0.065, 0.065, 1), 0.05),
    }
    for key, (rgba, emission) in colors.items():
        material(assets, key, rgba, emission)
    for key in SHOP_SIGNS:
        ET.SubElement(
            assets, "texture", name="city_menu_" + key, type="2d", file=f"city_menu_{key}.png"
        )
        ET.SubElement(
            assets,
            "material",
            name="city_menu_" + key,
            texture="city_menu_" + key,
            emission=".6",
            specular=".1",
        )
    for key, file in (("warm_paving", "city_living_paving.png"), ("desktop", "city_desktop.png")):
        ET.SubElement(assets, "texture", name="city_" + key, type="2d", file=file)
        ET.SubElement(
            assets,
            "material",
            name="city_" + key,
            texture="city_" + key,
            texuniform="true" if key == "warm_paving" else "false",
            texrepeat=".7 .7" if key == "warm_paving" else "1 1",
            emission=".15" if key == "warm_paving" else ".65",
        )
    builder.box(world, "living_road", (0, 30, -0.019), (30.5, 3.1, 0.018), "road_warm")
    crossings = (-24, -16.7, -8, 0, 8.1, 15.6, 24)
    for side in (-1, 1):
        builder.box(
            world,
            f"living_sidewalk_{side}",
            (0, 30 + side * 4.65, -0.012),
            (30, 1.55, 0.01),
            "warm_paving",
        )
        beam(
            world,
            f"living_curb_light_{side}",
            (-30, 30 + side * 3.22, 0.025),
            (30, 30 + side * 3.22, 0.025),
            0.018,
            "gold",
        )
        start = -30
        for crossing in (*crossings, 31.1):
            end = min(30, crossing - 1.1)
            if end > start:
                builder.box(
                    world,
                    f"living_curb_{side}_{start}",
                    ((start + end) / 2, 30 + side * 3.13, 0.055),
                    ((end - start) / 2, 0.09, 0.055),
                    "bronze",
                )
            start = crossing + 1.1
    for x in np.arange(-29, 30, 3.0):
        beam(world, f"living_lane_dash_{x}", (x, 30, 0.016), (x + 1.25, 30, 0.016), 0.025, "amber")
    for x in crossings:
        for dy in np.arange(-2.8, 2.9, 0.6):
            geom(
                world,
                f"living_crosswalk_{x}_{dy}",
                pos=(x, 30 + dy, 0.006),
                size=(0.85, 0.18, 0.004),
                material="shop_white",
                solid=False,
            )
    for x in (-24, -8, 8, 24):
        for lane, direction in ((28.5, 1), (31.5, -1)):
            beam(
                world,
                f"living_arrow_{x}_{lane}",
                (x - 0.5 * direction, lane, 0.014),
                (x + 0.3 * direction, lane, 0.014),
                0.025,
                "shop_white",
            )
            for side in (-1, 1):
                beam(
                    world,
                    f"living_arrow_head_{x}_{lane}_{side}",
                    (x + 0.3 * direction, lane, 0.014),
                    (x, lane + side * 0.23, 0.014),
                    0.025,
                    "shop_white",
                )
    # Rear promenade and the open court keep the two shop rows from becoming a wall.
    builder.box(world, "north_prom_playground", (0, 45.5, -0.014), (30, 3.6, 0.012), "warm_paving")
    builder.box(world, "middle_service_walk", (0, 15.5, -0.014), (30, 1.5, 0.012), "paving")
    builder.box(world, "middle_pedestrian_link", (2.65, 15.0, -0.014), (0.7, 15.0, 0.012), "paving")
    for j, x in enumerate((-25.0, -11.0, 11.0, 25.0)):
        builder.planter(world, f"living_park_planter_{j}", x, 46.0, 0.65, 0.38)
        leaf = world.find(f"geom[@name='living_park_planter_{j}_leaves']")
        if leaf is not None:
            world.remove(leaf)
        tree(
            world,
            f"living_park_tree_{j}",
            x,
            46.0,
            base=0.52,
            height=2.9,
            seed=600 + j,
            autumn=j % 2 == 0,
        )
        geom(
            world,
            f"living_park_bench_{j}",
            pos=(x + 1.7, 46.0, 0.24),
            size=(0.65, 0.25, 0.24),
            material="shop_wood",
        )
    # Lamp strings and a recognisable neighbourhood entrance contrast with neon gantries.
    for x in (-6.8, 16.8):
        for side in (-1, 1):
            geom(
                world,
                f"living_string_post_{x}_{side}",
                "cylinder",
                (x, 30 + side * 5.7, 3.1),
                (0.065, 3.1),
                "bronze",
            )
        for j in range(8):
            y = 24.5 + j * 11 / 7
            z = 5.5 - 0.65 * np.sin(j * np.pi / 7)
            lantern(world, f"living_lantern_{x}_{j}", (x, y, z), j % 2 == 0)
    banner = ET.SubElement(
        world, "body", name="living_banner", pos="-7.1 30 6.2", euler="0 0 -1.5707963"
    )
    builder.sign(banner, "living_district_sign", "living", (0, 0, 0), 7.6, 0.9)
    beam(world, "living_banner_support", (-6.8, 24.3, 6.15), (-6.8, 35.7, 6.15), 0.065, "bronze")
    for side in (-1, 1):
        advert(
            world,
            f"living_end_ad_{side}",
            "delivery" if side < 0 else "tea",
            (side * 30.4, 30, 2.3),
            4.8,
            2.3,
            -side * np.pi / 2,
        )
    for venue in VENUES:
        dress_shop(world, venue)
    # Extra sweets on the original night market make daily shops present on both roads.
    market = world.find("body[@name='venue_noodle']")
    sweets(market, "old_market_tanghulu", -3.95, 3.3)
