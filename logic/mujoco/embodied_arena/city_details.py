"""Architectural detailing, prop bevels and readable street-level material layers."""

import itertools
import xml.etree.ElementTree as ET

import numpy as np

from .city import VENUES, beam, geom, hiding_spots, numbers, ring, world_position


class Details:
    def __init__(self, assets):
        self.assets = assets
        self.meshes = {}

    def bevel(self, parent, name, pos, size, material="metal", bevel=0.035, group=3):
        key = tuple(round(float(v), 5) for v in (*size, bevel))
        if key not in self.meshes:
            mesh_name = "city_bevel_" + str(len(self.meshes))
            # Truncated cube, with a small outward allowance over the collision proxy.
            half = np.asarray(size) + 0.016
            cut = min(bevel, float(min(half)) * 0.55)
            vertices = []
            for signs in itertools.product((-1, 1), repeat=3):
                for axis in range(3):
                    vertex = half.copy()
                    vertex[axis] -= cut
                    vertices.extend(vertex * np.array(signs))
            ET.SubElement(
                self.assets, "mesh", name=mesh_name, vertex=numbers(vertices), smoothnormal="false"
            )
            self.meshes[key] = mesh_name
        return geom(
            parent,
            name,
            "mesh",
            pos=pos,
            size=(1, 1, 1),
            material=material,
            solid=False,
            group=group,
            mesh=self.meshes[key],
        )


def refine_city(assets, world, builder):
    materials = {
        "ceramic": ((0.43, 0.47, 0.59, 1), 0.05, 0.45),
        "titanium": ((0.29, 0.33, 0.44, 1), 0.05, 0.7),
        "warm": ((1, 0.77, 0.47, 1), 0.55, 0.3),
        "white": ((0.58, 0.82, 1, 1), 0.65, 0.25),
        "copper": ((0.53, 0.30, 0.24, 1), 0.05, 0.6),
        "ink": ((0.015, 0.025, 0.05, 1), 0.05, 0.2),
    }
    for key, (rgba, emission, specular) in materials.items():
        ET.SubElement(
            assets,
            "material",
            name="city_" + key,
            rgba=numbers(rgba),
            emission=str(emission),
            specular=str(specular),
            shininess=".65",
        )
    paving = assets.find("material[@name='city_paving']")
    paving.set("rgba", ".68 .74 .87 1")
    wall = assets.find("material[@name='city_wall']")
    wall.set("rgba", ".23 .26 .37 1")
    wall.set("specular", ".15")
    wall.set("shininess", ".2")
    details = Details(assets)
    for venue in VENUES:
        key = venue["id"]
        w = venue["width"]
        d = venue["depth"]
        parent = world.find(f"body[@name='venue_{key}']")
        if key != "park":
            # Broad awning over open frontage, with a white underside light.
            details.bevel(
                parent,
                key + "_awning",
                (0, -0.53, 2.60),
                (w / 2 + 0.15, 0.6, 0.075),
                "titanium",
                0.03,
                5,
            )
            beam(
                parent,
                key + "_awning_light",
                (-w / 2 + 0.15, -1.1, 2.59),
                (w / 2 - 0.15, -1.1, 2.59),
                0.024,
                "purple" if key in ("cafe", "chapel") else "cyan",
            )
            for x in np.linspace(-w / 2 + 0.3, w / 2 - 0.3, 7):
                beam(
                    parent,
                    f"{key}_awning_rib_{x}",
                    (x, -0.98, 2.52),
                    (x, -0.05, 2.52),
                    0.018,
                    "metal",
                )
            for side in (-1, 1):
                center = side * (w / 4 + 0.7)
                width = w / 4 - 0.8
                for offset in (-0.50, 0, 0.50):
                    u = center + offset * width
                    beam(
                        parent,
                        f"{key}_mullion_{side}_{offset}",
                        (u, -0.19, 0.79),
                        (u, -0.19, 2.22),
                        0.017,
                        "titanium",
                    )
                beam(
                    parent,
                    f"{key}_sill_{side}",
                    (center - width, -0.20, 0.78),
                    (center + width, -0.20, 0.78),
                    0.035,
                    "metal",
                )
                details.bevel(
                    parent,
                    f"{key}_corner_panel_{side}",
                    (side * (w / 2 - 0.13), -0.17, 1.45),
                    (0.12, 0.05, 1.38),
                    "titanium",
                    0.03,
                )
                for z in (0.25, 1.05, 2.15):
                    geom(
                        parent,
                        f"{key}_bolt_{side}_{z}",
                        "sphere",
                        (side * 1.4, -0.23, z),
                        (0.028,),
                        "ceramic",
                        False,
                    )
            # Wall seams and interior luminaires provide depth without narrowing aisles.
            for z in (0.32, 1.35, 2.45):
                beam(
                    parent,
                    f"{key}_back_seam_{z}",
                    (-w / 2 + 0.18, d - 0.15, z),
                    (w / 2 - 0.18, d - 0.15, z),
                    0.008,
                    "titanium",
                )
            for u in (-w / 2 + 0.45, w / 2 - 0.45):
                beam(
                    parent,
                    f"{key}_interior_light_{u}",
                    (u, 0.35, 2.92),
                    (u, d - 0.35, 2.92),
                    0.026,
                    "white",
                )
            for u in np.arange(-w / 2 + 0.8, w / 2, 0.95):
                beam(
                    parent,
                    f"{key}_back_joint_{u}",
                    (u, d - 0.151, 0.2),
                    (u, d - 0.151, 2.65),
                    0.006,
                    "panel",
                )
            if key != "chapel":
                # Recessed upper floor: a second facade layer behind the ground-floor roof.
                geom(
                    parent,
                    key + "_upper_floor",
                    pos=(0, d * 0.66, 4.23),
                    size=(w / 2 - 0.28, d * 0.33, 0.65),
                    material="panel",
                    solid=True,
                    group=5,
                )
                for side in (-1, 1):
                    details.bevel(
                        parent,
                        f"{key}_upper_edge_{side}",
                        (side * (w / 2 - 0.28), d * 0.66, 4.22),
                        (0.09, d * 0.33, 0.69),
                        "titanium",
                        0.035,
                        5,
                    )
                for u in np.linspace(-w / 2 + 0.7, w / 2 - 0.7, 5):
                    geom(
                        parent,
                        f"{key}_upper_window_{u}",
                        pos=(u, d * 0.33 - 0.02, 4.25),
                        size=(0.34, 0.015, 0.34),
                        material="glass",
                        solid=False,
                        group=5,
                    )
                    beam(
                        parent,
                        f"{key}_upper_window_neon_{u}",
                        (u - 0.32, d * 0.33 - 0.04, 3.94),
                        (u + 0.32, d * 0.33 - 0.04, 3.94),
                        0.018,
                        "cyan",
                    ).set("group", "5")
                details.bevel(
                    parent,
                    key + "_upper_roof",
                    (0, d * 0.66, 4.95),
                    (w / 2 - 0.1, d * 0.33 + 0.15, 0.08),
                    "titanium",
                    0.03,
                    5,
                )
                for u in (-1.4, 1.4):
                    details.bevel(
                        parent,
                        f"{key}_vent_{u}",
                        (u, d * 0.7, 5.16),
                        (0.4, 0.3, 0.16),
                        "metal",
                        0.045,
                        5,
                    )
                    for j in range(5):
                        beam(
                            parent,
                            f"{key}_vent_louver_{u}_{j}",
                            (u - 0.3, d * 0.7 - 0.22 + j * 0.1, 5.33),
                            (u + 0.3, d * 0.7 - 0.22 + j * 0.1, 5.33),
                            0.012,
                            "panel",
                        )
            # Entry sill is a texture-like thin plate; no raised doorstep.
            geom(
                parent,
                key + "_threshold",
                pos=(0, -0.15, 0.006),
                size=(1.3, 0.23, 0.004),
                material="titanium",
                solid=False,
            )
            for u in (-1.0, -0.5, 0, 0.5, 1.0):
                beam(
                    parent,
                    f"{key}_threshold_tick_{u}",
                    (u, -0.3, 0.012),
                    (u, -0.02, 0.012),
                    0.013,
                    "cyan",
                )
        # Give storage modules bevelled skins, inset panels and packages.
        for index, spot in enumerate(s for s in hiding_spots() if s["zone"] == key):
            p = np.array(spot["position"])
            origin = world_position(venue, 0, 0)
            u = (p[0] - origin[0]) * venue["side"]
            v = (p[1] - origin[1]) * venue["side"]
            z = p[2] - 0.18
            details.bevel(
                parent,
                f"{key}_storage_skin_{index}",
                (u, v, z / 2),
                (0.38, 0.28, z / 2),
                "titanium",
                0.035,
            )
            geom(
                parent,
                f"{key}_storage_inset_{index}",
                pos=(u, v - 0.296, z * 0.52),
                size=(0.27, 0.01, z * 0.27),
                material="panel",
                solid=False,
            )
            beam(
                parent,
                f"{key}_storage_handle_{index}",
                (u - 0.12, v - 0.315, z * 0.8),
                (u + 0.12, v - 0.315, z * 0.8),
                0.013,
                "ceramic",
            )
            search_u = (spot["search_position"][0] - origin[0]) * venue["side"]
            outward = -1 if search_u > u else 1
            for package in range(2):
                details.bevel(
                    parent,
                    f"{key}_package_{index}_{package}",
                    (u + outward * 0.25, v + 0.08, z + 0.13 + package * 0.14),
                    (0.075, 0.12, 0.065),
                    "copper" if package else "panel",
                    0.018,
                )
                beam(
                    parent,
                    f"{key}_package_band_{index}_{package}",
                    (u + outward * 0.25 - 0.06, v - 0.045, z + 0.15 + package * 0.14),
                    (u + outward * 0.25 + 0.06, v - 0.045, z + 0.15 + package * 0.14),
                    0.012,
                    "amber",
                )
        if key == "chapel":
            # Actual pitched roof, vaulted ribs and rose-window detail.
            old = parent.find("geom[@name='chapel_roof']")
            if old is not None:
                parent.remove(old)
            angle = np.arctan2(2.2, w / 2)
            length = np.hypot(w / 2, 2.2)
            for side in (-1, 1):
                geom(
                    parent,
                    f"chapel_sloped_roof_{side}",
                    pos=(side * w / 4, d / 2, 4.7),
                    size=(length / 2, d / 2 + 0.2, 0.10),
                    material="panel",
                    solid=True,
                    group=5,
                    euler=(0, side * angle, 0),
                )
            vertices = []
            for y in (d - 0.10, d + 0.10):
                vertices.extend((-w / 2, y, 3.28))
                vertices.extend((w / 2, y, 3.28))
                vertices.extend((0, y, 5.8))
            ET.SubElement(
                assets,
                "mesh",
                name="city_chapel_gable",
                vertex=numbers(vertices),
                smoothnormal="false",
            )
            geom(
                parent,
                "chapel_back_gable",
                "mesh",
                pos=(0, 0, 0),
                size=(1, 1, 1),
                material="wall",
                solid=True,
                group=5,
                mesh="city_chapel_gable",
            )
            for v in (0.25, 2.2, 4.4, d - 0.12):
                beam(
                    parent,
                    f"chapel_vault_left_{v}",
                    (-w / 2 + 0.25, v, 3.25),
                    (0, v, 5.55),
                    0.07,
                    "titanium",
                )
                beam(
                    parent,
                    f"chapel_vault_right_{v}",
                    (w / 2 - 0.25, v, 3.25),
                    (0, v, 5.55),
                    0.07,
                    "titanium",
                )
            ring(
                parent,
                "chapel_rose",
                (0, d - 0.17, 3.75),
                0.78,
                "purple",
                40,
                0.035,
                tilt=np.pi / 2,
            )
            for angle in np.arange(0, 2 * np.pi, np.pi / 4):
                beam(
                    parent,
                    f"chapel_rose_spoke_{angle}",
                    (0, d - 0.17, 3.75),
                    (0.74 * np.cos(angle), d - 0.17, 3.75 + 0.74 * np.sin(angle)),
                    0.025,
                    "cyan",
                )
            for v in (1.4, 3.7):
                for side in (-1, 1):
                    details.bevel(
                        parent,
                        f"chapel_seat_cushion_{v}_{side}",
                        (side * 0.9, v, 0.65),
                        (0.34, 0.21, 0.055),
                        "seat",
                        0.025,
                    )
                    for offset in (-0.27, 0.27):
                        beam(
                            parent,
                            f"chapel_seat_arm_{v}_{side}_{offset}",
                            (side * 0.9 + offset, v - 0.12, 0.85),
                            (side * 0.9 + offset, v + 0.18, 0.85),
                            0.023,
                            "titanium",
                        )
        elif key == "cafe":
            for x in (-1.7, 1.65):
                ring(parent, f"cafe_table_rim_{x}", (x, 3.5, 0.77), 0.42, "pink", 24, 0.013)
                details.bevel(
                    parent,
                    f"cafe_chair_back_{x}",
                    (x, 2.68, 0.67),
                    (0.23, 0.04, 0.32),
                    "seat",
                    0.04,
                )
                geom(
                    parent,
                    f"cafe_coffee_plate_{x}",
                    "cylinder",
                    (x, 3.5, 0.79),
                    (0.12, 0.015),
                    "ceramic",
                    False,
                )
                geom(
                    parent,
                    f"cafe_coffee_cup_{x}",
                    "cylinder",
                    (x, 3.5, 0.86),
                    (0.065, 0.06),
                    "copper",
                    False,
                )
        elif key == "charge":
            for x in (-2.0, 0.0, 2.0):
                details.bevel(
                    parent, f"charge_shell_{x}", (x, 3.2, 0.7), (0.30, 0.23, 0.7), "titanium", 0.04
                )
                for row in range(4):
                    geom(
                        parent,
                        f"charge_status_{x}_{row}",
                        pos=(x - 0.12 + row * 0.08, 2.935, 1.22),
                        size=(0.023, 0.018, 0.04 + row * 0.02),
                        material="mint",
                        solid=False,
                    )
                for segment in range(10):
                    a, b = np.pi * segment / 10, np.pi * (segment + 1) / 10
                    beam(
                        parent,
                        f"charge_cable_{x}_{segment}",
                        (x + 0.35 + 0.23 * np.sin(a), 3.2, 0.85 - 0.65 * np.cos(a / 2)),
                        (x + 0.35 + 0.23 * np.sin(b), 3.2, 0.85 - 0.65 * np.cos(b / 2)),
                        0.023,
                        "ink",
                    )
        elif key == "park":
            for side in (-1, 1):
                for v in (1.4, 4.6):
                    u = side * 3.7
                    for j in range(5):
                        a = j * 2 * np.pi / 5
                        geom(
                            parent,
                            f"park_leaf_{side}_{v}_{j}",
                            "ellipsoid",
                            (
                                u + 0.36 * np.cos(a),
                                v + 0.36 * np.sin(a),
                                2.25 + 0.16 * np.cos(a * 2),
                            ),
                            (0.39, 0.24, 0.32),
                            "leaf",
                            False,
                            euler=(0, 0.22, a),
                        )
                    beam(
                        parent,
                        f"park_tree_circuit_{side}_{v}",
                        (u - 0.08, v, 0.65),
                        (u - 0.08, v, 1.65),
                        0.018,
                        "mint",
                    )
        elif key in ("market", "lab"):
            for shelf in range(3):
                z = 1.2 + shelf * 0.38
                geom(
                    parent,
                    f"{key}_rear_book_shelf_{shelf}",
                    pos=(-1.6, d - 0.23, z),
                    size=(0.65, 0.12, 0.025),
                    material="titanium",
                    solid=False,
                )
                for book in range(6):
                    details.bevel(
                        parent,
                        f"{key}_book_{shelf}_{book}",
                        (-2.15 + book * 0.19, d - 0.24, z + 0.13),
                        (0.055, 0.08, 0.105),
                        "copper" if book % 3 == 0 else "panel",
                        0.012,
                    )
                    beam(
                        parent,
                        f"{key}_book_led_{shelf}_{book}",
                        (-2.15 + book * 0.19, d - 0.33, z + 0.04),
                        (-2.15 + book * 0.19, d - 0.33, z + 0.21),
                        0.008,
                        "cyan",
                    )
    # Drainage covers and lane-direction arrows give the pavement a human scale.
    for x in np.arange(-18, 19, 3.8):
        for side in (-1, 1):
            for j in range(6):
                geom(
                    world,
                    f"drain_{x}_{side}_{j}",
                    pos=(x - 0.25 + j * 0.1, side * 2.54, 0.007),
                    size=(0.018, 0.12, 0.005),
                    material="ink",
                    solid=False,
                )
    for x in (-13, -5, 3, 11):
        for lane, direction in ((-1.25, 1), (1.25, -1)):
            beam(
                world,
                f"road_arrow_stem_{x}_{lane}",
                (x - direction * 0.55, lane, 0.012),
                (x + direction * 0.25, lane, 0.012),
                0.025,
                "white",
            )
            for side in (-1, 1):
                beam(
                    world,
                    f"road_arrow_head_{x}_{lane}_{side}",
                    (x + direction * 0.25, lane, 0.012),
                    (x - direction * 0.04, lane + side * 0.22, 0.012),
                    0.025,
                    "white",
                )
    for x in (-17.5, -5.7, 5.4, 17):
        for side in (-1, 1):
            for j in range(8):
                a, b = j / 8, (j + 1) / 8
                p = (x - 1.4 + 2.8 * a, side * 5.02, 4.12 - 0.30 * np.sin(a * np.pi))
                q = (x - 1.4 + 2.8 * b, side * 5.02, 4.12 - 0.30 * np.sin(b * np.pi))
                beam(world, f"lamp_cable_{x}_{side}_{j}", p, q, 0.012, "ink")
    # Hovercraft: bevelled body shell, turbine rings, radiator slats and antenna.
    for body in world.findall("body"):
        name = body.get("name", "")
        if name.startswith("traffic/"):
            details.bevel(body, name + "/bodywork", (0, 0, 0), (1.25, 0.58, 0.18), "titanium", 0.07)
            for side in (-1, 1):
                for j in range(6):
                    beam(
                        body,
                        name + f"/radiator_{side}_{j}",
                        (-0.9 + j * 0.14, side * 0.605, -0.06),
                        (-0.9 + j * 0.14, side * 0.605, 0.09),
                        0.018,
                        "ink",
                    )
                for x in (-0.85, 0.85):
                    ring(
                        body,
                        name + f"/turbine_ring_{side}_{x}",
                        (x, side * 0.42, -0.34),
                        0.16,
                        "cyan",
                        20,
                        0.014,
                    )
            beam(body, name + "/antenna", (-0.65, 0, 0.55), (-0.8, 0, 0.86), 0.013, "metal")
            geom(body, name + "/antenna_tip", "sphere", (-0.8, 0, 0.86), (0.026,), "pink", False)
        elif name.startswith("citizen/") and name.count("/") == 1:
            details.bevel(
                body, name + "/chest_shell", (0, 0, 0.25), (0.2, 0.145, 0.24), "titanium", 0.055
            )
            for side in (-1, 1):
                geom(
                    body,
                    name + f"/shoulder_led_{side}",
                    "sphere",
                    (0, side * 0.17, 0.42),
                    (0.055,),
                    "cyan",
                    False,
                )
