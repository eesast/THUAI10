"""Room finishes, joinery, lighting and store-specific small furnishings."""

import numpy as np

from .city import VENUES, beam, geom, hiding_spots, numbers, world_position
from .city_meshes import Mesh
from .city_shops import panel

THEMES = {
    "mixue": ("terrazzo", "ivory", "shop_red"),
    "luckin": ("timber", "ivory", "shop_blue"),
    "shaxian": ("terrazzo", "linen", "shop_red"),
    "skewers": ("concrete", "linen", "bronze"),
    "hardware": ("concrete", "ivory", "olive"),
    "hotel": ("marble", "ivory", "brass"),
    "netcafe": ("carpet", "upholstery", "shop_blue"),
    "tanghulu": ("terrazzo", "ivory", "shop_red"),
    "convenience": ("terrazzo", "ivory", "olive"),
    "laundry": ("ceramic", "ivory", "teal_paint"),
}


def prepare_details(assets):
    plant = Mesh()
    rng = np.random.default_rng(941)
    for i in range(48):
        angle = i * 2.4
        center = np.array([0.11 * np.cos(angle), 0.11 * np.sin(angle), 0.13 + 0.006 * i])
        plant.leaf(center, angle, 0.23 + rng.uniform(0, 0.13), 0.034, rng.uniform(0.2, 1.5))
    plant.asset(assets, "city_indoor_fern")
    for radius in (0.08, 0.12, 0.25, 0.30):
        m = Mesh()
        n = 32
        k = 6
        points = []
        faces = []
        for i in range(n):
            a = i * 2 * np.pi / n
            for j in range(k):
                b = j * 2 * np.pi / k
                points.append(
                    (
                        (radius + 0.012 * np.cos(b)) * np.cos(a),
                        (radius + 0.012 * np.cos(b)) * np.sin(a),
                        0.012 * np.sin(b),
                    )
                )
        for i in range(n):
            for j in range(k):
                a = i * k + j
                b = ((i + 1) % n) * k + j
                c = ((i + 1) % n) * k + (j + 1) % k
                d = i * k + (j + 1) % k
                faces.extend(((a, b, c), (a, c, d)))
        m.add(points, faces)
        m.asset(assets, f"city_detail_ring_{round(radius * 100)}")


def ring_detail(parent, name, pos, radius, mat="brass", euler=(0, 0, 0)):
    geom(
        parent,
        name,
        "mesh",
        pos=pos,
        material=mat,
        solid=False,
        mesh=f"city_detail_ring_{round(radius * 100)}",
        euler=euler,
    )


def plant(parent, name, u, v):
    geom(parent, name + "_pot", "cylinder", (u, v, 0.16), (0.17, 0.16), "ivory")
    geom(parent, name + "_soil", "cylinder", (u, v, 0.325), (0.145, 0.012), "soil", False)
    geom(
        parent,
        name + "_fern",
        "mesh",
        (u, v, 0.33),
        (1, 1, 1),
        "leaf_light",
        False,
        mesh="city_indoor_fern",
    )


def pendant(parent, name, u, v):
    beam(parent, name + "_wire", (u, v, 2.64), (u, v, 3.28), 0.009, "steel").set("group", "5")
    geom(parent, name + "_shade", "cylinder", (u, v, 2.58), (0.18, 0.07), "walnut", False, 5)
    geom(parent, name + "_diffuser", "cylinder", (u, v, 2.502), (0.15, 0.012), "warm", False, 5)


def common_room(assets, world, venue, kind):
    key = venue["id"]
    w, d = venue["width"], venue["depth"]
    parent = world.find(f"body[@name='venue_{key}']")
    floor, wall, accent = THEMES[kind]
    parent.find(f"geom[@name='{key}_floor']").set("material", "city_finish_" + floor)
    for g in parent.findall("geom"):
        name = g.get("name", "")
        if name in (key + "_back", key + "_side_-1", key + "_side_1"):
            g.set("material", "city_" + wall)
        elif "_back_joint_" in name or "_back_seam_" in name:
            g.set("material", "city_steel")
        elif "_storage_skin_" in name:
            g.set(
                "material",
                "city_" + ("walnut" if kind in ("hotel", "luckin", "skewers") else accent),
            )
        elif "_storage_handle_" in name:
            g.set("material", "city_brass")
        elif name.startswith(key + "_screen_"):
            g.set(
                "material",
                "city_"
                + (
                    "upholstery"
                    if kind == "netcafe"
                    else "walnut"
                    if kind in ("hotel", "luckin")
                    else "linen"
                ),
            )
    # Wall joinery uses the existing shell, leaving the floor plan intact.
    geom(
        parent,
        key + "_back_wainscot",
        pos=(0, d - 0.156, 0.53),
        size=(w / 2 - 0.19, 0.012, 0.48),
        material="walnut",
        solid=False,
    )
    for side in (-1, 1):
        geom(
            parent,
            key + f"_side_wainscot_{side}",
            pos=(side * (w / 2 - 0.156), d / 2, 0.53),
            size=(0.012, d / 2 - 0.18, 0.48),
            material="walnut",
            solid=False,
        )
        beam(
            parent,
            key + f"_dado_rail_{side}",
            (side * (w / 2 - 0.18), 0.2, 1.04),
            (side * (w / 2 - 0.18), d - 0.18, 1.04),
            0.014,
            "brass",
        )
    beam(
        parent,
        key + "_back_dado",
        (-w / 2 + 0.2, d - 0.18, 1.04),
        (w / 2 - 0.2, d - 0.18, 1.04),
        0.014,
        "brass",
    )
    panel(
        parent,
        key + "_feature_wall",
        "sign_" + venue.get("sign", key),
        (1.0 if key == "hotel" else 0, d - 0.18, 2.27),
        2.5,
        0.65,
    )
    geom(
        parent,
        key + "_ceiling_light",
        pos=(0, d * 0.46, 3.29),
        size=(0.55, 0.19, 0.018),
        material="warm" if kind not in ("netcafe", "laundry") else "white",
        solid=False,
        group=5,
    )
    # Trim makes the hiding screens read as shop dividers instead of bare slabs.
    frame = Mesh()
    for i, spot in enumerate(s for s in hiding_spots() if s["zone"] == key):
        origin = world_position(venue, 0, 0)
        p = np.asarray(spot["position"])
        u = (p[0] - origin[0]) * venue["side"]
        v = (p[1] - origin[1]) * venue["side"] - 0.6
        for side in (-1, 1):
            frame.box((u + side * 0.405, v - 0.09, 0.78), (0.018, 0.018, 0.78))
        for z in (0.08, 0.77, 1.49):
            frame.box((u, v - 0.092, z), (0.40, 0.018, 0.014))
    frame.asset(assets, "city_divider_trim_" + key)
    geom(
        parent,
        key + "_divider_trim",
        "mesh",
        material="brass" if kind in ("hotel", "hardware") else "oak",
        solid=False,
        mesh="city_divider_trim_" + key,
    )
    plant(parent, key + "_indoor_plant", w / 2 - 0.65, 2.8)
    return parent


def refine_seating(parent, key):
    for g in list(parent.findall("geom")):
        name = g.get("name", "")
        if "_stool_" not in name or g.get("type") != "cylinder":
            continue
        x, y, _ = map(float, g.get("pos").split())
        g.set("pos", numbers((x, y, 0.435)))
        g.set("size", ".19 .035")
        for sx in (-1, 1):
            for sy in (-1, 1):
                beam(
                    parent,
                    name + f"_leg_{sx}_{sy}",
                    (x + sx * 0.12, y + sy * 0.12, 0.02),
                    (x + sx * 0.12, y + sy * 0.12, 0.40),
                    0.017,
                    "steel",
                    True,
                )
    if key == "cafe":
        for x in (-1.7, 1.65):
            g = parent.find(f"geom[@name='cafe_chair_{x}']")
            g.set("pos", numbers((x, 2.9, 0.44)))
            g.set("size", ".23 .23 .04")
            g.set("material", "city_upholstery")
            for sx in (-1, 1):
                for sy in (-1, 1):
                    beam(
                        parent,
                        f"cafe_chair_legs_{x}_{sx}_{sy}",
                        (x + sx * 0.16, 2.9 + sy * 0.16, 0.02),
                        (x + sx * 0.16, 2.9 + sy * 0.16, 0.40),
                        0.018,
                        "steel",
                        True,
                    )


def counter_detail(parent, key, u, v, accent):
    geom(
        parent,
        key + "_counter_cap",
        pos=(u, v, 1.005),
        size=(0.41, 0.36, 0.025),
        material="walnut",
        solid=False,
    )
    for i, z in enumerate((0.27, 0.57, 0.84)):
        geom(
            parent,
            key + f"_drawer_{i}",
            pos=(u, v - 0.347, z),
            size=(0.34, 0.008, 0.11),
            material=accent,
            solid=False,
        )
        beam(
            parent,
            key + f"_pull_{i}",
            (u - 0.11, v - 0.365, z + 0.035),
            (u + 0.11, v - 0.365, z + 0.035),
            0.012,
            "brass",
        )


def dining_details(parent, key, u, v, z=0.81):
    ring_detail(parent, key + "_plate_rim", (u - 0.12, v, z), 0.12, "ivory")
    geom(
        parent,
        key + "_plate",
        "ellipsoid",
        (u - 0.12, v, z - 0.008),
        (0.12, 0.12, 0.015),
        "ivory",
        False,
    )
    geom(
        parent,
        key + "_napkin_box",
        pos=(u + 0.13, v + 0.12, z + 0.08),
        size=(0.085, 0.045, 0.075),
        material="oak",
        solid=False,
    )
    geom(
        parent,
        key + "_napkin",
        pos=(u + 0.13, v + 0.12, z + 0.165),
        size=(0.065, 0.005, 0.035),
        material="shop_white",
        solid=False,
    )
    for i in range(2):
        geom(
            parent,
            key + f"_condiment_{i}",
            "cylinder",
            (u + 0.13 + i * 0.11, v - 0.13, z + 0.055),
            (0.028, 0.055),
            "shop_red" if i else "steel",
            False,
        )


def refine_store(assets, world, venue):
    key = venue["id"]
    kind = venue.get("shop", {"noodle": "skewers", "arcade": "netcafe"}.get(key))
    if kind is None:
        return
    p = common_room(assets, world, venue, kind)
    w, d = venue["width"], venue["depth"]
    left = -w / 2 + 0.75
    refine_seating(p, key)
    if p.find(f"geom[@name='{key}_sales_counter']") is not None:
        counter_detail(p, key, left, 2.8, THEMES[kind][2])
        pendant(p, key + "_counter_pendant", left, 2.8)
    if kind in ("mixue", "luckin"):
        if key == "cafe":
            left = -2.65
            geom(
                p,
                "cafe_barista_counter",
                pos=(left, 0.95, 0.5),
                size=(0.42, 0.34, 0.5),
                material="walnut",
            )
            geom(
                p,
                "cafe_barista_machine",
                pos=(left, 1.04, 1.30),
                size=(0.29, 0.18, 0.28),
                material="steel",
                solid=False,
            )
            cy = 0.95
        elif key == "tea":
            left = -3.45
            cy = 3.4
            geom(
                p,
                "tea_tea_dispenser",
                pos=(left, cy + 0.1, 1.3),
                size=(0.3, 0.19, 0.28),
                material="shop_white",
                solid=False,
            )
        else:
            cy = 2.8
        for j in range(3):
            x = left - 0.18 + j * 0.18
            beam(p, key + f"_tap_{j}", (x, cy - 0.1, 1.36), (x, cy - 0.29, 1.36), 0.017, "steel")
            geom(
                p,
                key + f"_tap_lever_{j}",
                pos=(x, cy - 0.16, 1.47),
                size=(0.019, 0.025, 0.065),
                material="shop_blue" if kind == "luckin" else "shop_red",
                solid=False,
            )
        geom(
            p,
            key + "_machine_display",
            pos=(left, cy - 0.097, 1.55),
            size=(0.115, 0.012, 0.06),
            material="mint",
            solid=False,
        )
        if kind == "luckin":
            geom(
                p,
                key + "_bean_hopper",
                "ellipsoid",
                (left, cy + 0.1, 1.72),
                (0.15, 0.13, 0.16),
                "glass",
                False,
                rgba=".32 .24 .16 .6",
            )
        if key not in ("cafe", "tea"):
            dining_details(p, key + "_cafe_place", 0.4, 2.9)
        if key == "cafe":
            dining_details(p, "cafe_table_place", -1.7, 3.5, 0.78)
    elif kind == "shaxian":
        if key == "shaxian":
            for j, z in enumerate((1.01, 1.11, 1.21)):
                ring_detail(p, key + f"_bamboo_rim_{j}", (left, 2.8, z), 0.25, "oak")
            dining_details(p, key + "_meal", 0.4, 2.8)
        else:
            dining_details(p, key + "_meal", -0.15, 2.5, 1.04)
        geom(
            p,
            key + "_service_shelf",
            pos=(-w / 2 + 0.55, d - 0.4, 1.6),
            size=(0.4, 0.17, 0.035),
            material="oak",
            solid=False,
        )
        for j in range(3):
            geom(
                p,
                key + f"_bowl_stack_{j}",
                "cylinder",
                (-w / 2 + 0.55, d - 0.4, 1.67 + j * 0.055),
                (0.11, 0.022),
                "shop_white",
                False,
            )
    elif kind == "skewers" and key == "skewers":
        geom(
            p,
            key + "_exhaust_duct",
            pos=(left, 2.8, 2.93),
            size=(0.18, 0.20, 0.39),
            material="steel",
            solid=False,
            group=5,
        )
        for i in range(5):
            beam(
                p,
                key + f"_hood_slit_{i}",
                (left - 0.35 + i * 0.17, 2.35, 2.34),
                (left - 0.35 + i * 0.17, 2.35, 2.43),
                0.012,
                "ink",
            )
        dining_details(p, key + "_night_place", 0.5, 2.8)
    elif kind == "tanghulu":
        for side in (-1, 1):
            for depth in (-1, 1):
                beam(
                    p,
                    key + f"_stall_post_{side}_{depth}",
                    (left + side * 0.46, 2.8 + depth * 0.40, 1.0),
                    (left + side * 0.46, 2.8 + depth * 0.40, 2.22),
                    0.018,
                    "brass",
                )
        panel(p, key + "_stall_sign", "sign_tanghulu", (left, 2.3, 2.23), 1.02, 0.23)
        for j in range(3):
            geom(
                p,
                key + f"_wrapping_{j}",
                pos=(left - 0.24 + j * 0.22, 3.05, 1.06),
                size=(0.08, 0.12, 0.025),
                material="ivory",
                solid=False,
            )
    elif kind == "hardware":
        bins = Mesh()
        for j in range(5):
            u = left - 0.30 + j * 0.15
            bins.box((u, 2.61, 1.04), (0.068, 0.12, 0.025))
            for k in range(3):
                bins.cylinder(
                    (u - 0.04 + k * 0.035, 2.61, 1.065),
                    (u - 0.04 + k * 0.035, 2.61, 1.11),
                    0.012,
                    sides=6,
                )
        bins.asset(assets, "city_hardware_small_parts")
        geom(
            p,
            "hardware_parts_bins",
            "mesh",
            material="steel",
            solid=False,
            mesh="city_hardware_small_parts",
        )
        for j in range(4):
            geom(
                p,
                key + f"_safety_band_{j}",
                pos=(left - 0.29 + j * 0.19, 2.438, 0.88),
                size=(0.055, 0.005, 0.04),
                material="gold" if j % 2 else "ink",
                solid=False,
            )
    elif kind == "hotel":
        bell = p.find("geom[@name='hotel_reception_bell']")
        bell.set("type", "ellipsoid")
        bell.set("size", ".10 .10 .045")
        bell.set("material", "city_brass")
        geom(p, key + "_bell_base", "cylinder", (-0.7, 2.82, 1.06), (0.11, 0.012), "brass", False)
        geom(
            p, key + "_bell_button", "cylinder", (-0.7, 2.82, 1.157), (0.018, 0.02), "steel", False
        )
        geom(
            p,
            key + "_desk_slab",
            pos=(-1.1, 3.0, 1.065),
            size=(1.14, 0.39, 0.025),
            material="walnut",
            solid=False,
        )
        for u in (-1.8, -1.1, -0.4):
            geom(
                p,
                key + f"_desk_inlay_{u}",
                pos=(u, 2.64, 0.57),
                size=(0.006, 0.008, 0.36),
                material="brass",
                solid=False,
            )
        panel(p, key + "_desk_terminal", "desktop", (-1.65, 3.1, 1.34), 0.45, 0.27)
        for j in range(3):
            geom(
                p,
                key + f"_key_card_{j}",
                pos=(-0.15 + j * 0.1, 2.89, 1.10),
                size=(0.035, 0.055, 0.005),
                material="ivory",
                solid=False,
            )
    elif kind == "netcafe" and key == "netcafe":
        desk = p.find("geom[@name='netcafe_pc_desk']")
        desk.set("pos", "0 2.9 .84")
        desk.set("size", "1.78 .33 .045")
        for x in (-1.62, 1.62):
            for y in (2.66, 3.14):
                beam(
                    p, key + f"_desk_leg_{x}_{y}", (x, y, 0.02), (x, y, 0.80), 0.032, "steel", True
                )
        for j, u in enumerate((-1.2, 0, 1.2)):
            geom(
                p,
                key + f"_monitor_base_{j}",
                pos=(u, 2.95, 0.90),
                size=(0.16, 0.10, 0.012),
                material="steel",
                solid=False,
            )
            beam(p, key + f"_monitor_stand_{j}", (u, 2.95, 0.9), (u, 2.95, 1.02), 0.018, "steel")
            geom(
                p,
                key + f"_mouse_{j}",
                "ellipsoid",
                (u + 0.35, 2.67, 0.90),
                (0.045, 0.065, 0.025),
                "steel",
                False,
            )
        geom(p, key + "_tower", pos=(-1.35, 2.9, 0.35), size=(0.20, 0.28, 0.35), material="ink")
        for z in (0.24, 0.49):
            ring_detail(
                p, key + f"_tower_fan_{z}", (-1.35, 2.607, z), 0.08, "mint", (np.pi / 2, 0, 0)
            )
        beam(p, key + "_desk_rgb", (-1.7, 2.555, 0.80), (1.7, 2.555, 0.80), 0.012, "purple")
        for j, u in enumerate((-0.6, 0.6)):
            geom(
                p,
                key + f"_chair_headrest_{j}",
                pos=(u, 1.78, 1.02),
                size=(0.13, 0.055, 0.075),
                material="upholstery",
                solid=False,
            )
            for side in (-1, 1):
                beam(
                    p,
                    key + f"_armrest_{j}_{side}",
                    (u + side * 0.22, 1.80, 0.69),
                    (u + side * 0.22, 2.10, 0.69),
                    0.022,
                    "steel",
                )
    elif kind == "convenience":
        geom(
            p,
            key + "_fridge_handle",
            pos=(2.86, 2.335, 1.03),
            size=(0.012, 0.018, 0.32),
            material="steel",
            solid=False,
        )
        for j in range(3):
            geom(
                p,
                key + f"_fridge_grille_{j}",
                pos=(2.6, 2.332, 0.16 + j * 0.045),
                size=(0.26, 0.008, 0.008),
                material="steel",
                solid=False,
            )
    elif kind == "laundry":
        for j, u in enumerate((-1.4, 0, 1.4)):
            ring_detail(
                p, key + f"_door_bezel_{j}", (u, 2.805, 0.58), 0.30, "steel", (np.pi / 2, 0, 0)
            )
            geom(
                p,
                key + f"_dial_{j}",
                "cylinder",
                (u - 0.25, 2.87, 1.0),
                (0.065, 0.025),
                "steel",
                False,
                euler=(np.pi / 2, 0, 0),
            )
            for k in range(3):
                geom(
                    p,
                    key + f"_folded_towel_{j}_{k}",
                    pos=(u, 3.3, 1.19 + k * 0.045),
                    size=(0.25, 0.17, 0.02),
                    material="ivory" if k % 2 else "teal_paint",
                    solid=False,
                )


def refine_interiors(assets, world):
    prepare_details(assets)
    for venue in VENUES:
        refine_store(assets, world, venue)
