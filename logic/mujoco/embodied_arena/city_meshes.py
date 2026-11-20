"""Shared decorative meshes keep detailed scenery within the viewer budget."""

import xml.etree.ElementTree as ET

import numpy as np

from .city import beam, geom, numbers


class Mesh:
    def __init__(self):
        self.vertices = []
        self.faces = []

    def add(self, points, faces):
        offset = len(self.vertices)
        self.vertices.extend(np.asarray(points, dtype=float).tolist())
        self.faces.extend(tuple(offset + i for i in face) for face in faces)

    def box(self, center, half):
        x, y, z = half
        points = (
            np.array(
                [
                    (-x, -y, -z),
                    (x, -y, -z),
                    (x, y, -z),
                    (-x, y, -z),
                    (-x, -y, z),
                    (x, -y, z),
                    (x, y, z),
                    (-x, y, z),
                ]
            )
            + center
        )
        self.add(
            points,
            [
                (0, 3, 2),
                (0, 2, 1),
                (4, 5, 6),
                (4, 6, 7),
                (0, 1, 5),
                (0, 5, 4),
                (3, 7, 6),
                (3, 6, 2),
                (1, 2, 6),
                (1, 6, 5),
                (0, 4, 7),
                (0, 7, 3),
            ],
        )

    def cylinder(self, start, end, radius, tip_radius=None, sides=10):
        a = np.asarray(start, float)
        b = np.asarray(end, float)
        w = b - a
        w /= np.linalg.norm(w)
        u = np.cross(w, [0, 0, 1] if abs(w[2]) < 0.9 else [1, 0, 0])
        u /= np.linalg.norm(u)
        v = np.cross(w, u)
        tip_radius = radius if tip_radius is None else tip_radius
        points = []
        for c, r in ((a, radius), (b, tip_radius)):
            for angle in np.arange(sides) * 2 * np.pi / sides:
                points.append(c + r * (np.cos(angle) * u + np.sin(angle) * v))
        points.extend((a, b))
        faces = []
        for i in range(sides):
            j = (i + 1) % sides
            faces.extend(
                (
                    (i, j, sides + j),
                    (i, sides + j, sides + i),
                    (2 * sides, j, i),
                    (2 * sides + 1, sides + i, sides + j),
                )
            )
        self.add(points, faces)

    def leaf(self, center, angle, length, width, tilt):
        along = np.array([np.cos(angle), np.sin(angle), tilt])
        along /= np.linalg.norm(along)
        across = np.array([-np.sin(angle), np.cos(angle), 0.08])
        p = np.asarray(center)
        self.add(
            [
                p,
                p + along * length,
                p + along * length * 0.45 - across * width + [0, 0, 0.018],
                p + along * length * 0.45 + across * width + [0, 0, 0.018],
            ],
            [(0, 2, 1), (0, 1, 3), (1, 2, 0), (3, 1, 0)],
        )

    def asset(self, assets, name, scale=1):
        return ET.SubElement(
            assets,
            "mesh",
            name=name,
            vertex=numbers(np.asarray(self.vertices).ravel()),
            face=" ".join(str(i) for face in self.faces for i in face),
            smoothnormal="false",
            scale=numbers((scale, scale, scale)),
        )


TREE_HEIGHTS = (2.9, 3.15, 3.35)


def prepare_trees(assets):
    for variant in range(2):
        rng = np.random.default_rng(710 + variant)
        bark = Mesh()
        leaves = [Mesh(), Mesh(), Mesh()]
        stem = np.array([0.025, 0, 2.04])
        bark.cylinder((0, 0, 0), stem, 0.10, 0.046)
        for j in range(8):
            angle = j * np.pi / 4 + rng.uniform(-0.15, 0.15)
            end = stem + np.array(
                [
                    (0.65 + 0.15 * (j % 3)) * np.cos(angle),
                    (0.65 + 0.15 * (j % 3)) * np.sin(angle),
                    0.35 + 0.19 * (j % 3),
                ]
            )
            bark.cylinder(stem - [0, 0, 0.03 * (j % 3)], end, 0.035, 0.012)
            for k in range(3):
                tip = end + np.array(
                    [
                        0.23 * np.cos(angle + (k - 1) * 0.65),
                        0.23 * np.sin(angle + (k - 1) * 0.65),
                        0.12 * (k - 1),
                    ]
                )
                bark.cylinder(end, tip, 0.012, 0.004, 8)
                for i in range(32):
                    p = tip + rng.normal(0, (0.19, 0.19, 0.16))
                    leaves[(j + k + i) % 3].leaf(
                        p,
                        rng.uniform(0, 2 * np.pi),
                        rng.uniform(0.13, 0.23),
                        rng.uniform(0.025, 0.048),
                        rng.uniform(-0.65, 0.75),
                    )
        for j in range(5):
            tip = stem + np.array(
                [0.28 * np.cos(j * 1.3), 0.28 * np.sin(j * 1.3), 0.78 + 0.12 * (j % 2)]
            )
            bark.cylinder(stem, tip, 0.018, 0.005, 8)
            for i in range(32):
                leaves[(i + j) % 3].leaf(
                    tip + rng.normal(0, (0.22, 0.22, 0.16)),
                    rng.uniform(0, 2 * np.pi),
                    0.18,
                    0.036,
                    rng.uniform(-0.8, 0.8),
                )
        for height in TREE_HEIGHTS:
            prefix = f"city_botany_{round(height * 100)}_{variant}"
            bark.asset(assets, prefix + "_wood", height / 3)
            for i, mesh in enumerate(leaves):
                mesh.asset(assets, prefix + f"_leaf_{i}", height / 3)


def draw_tree(parent, name, u, v, base=0, height=2.9, seed=0, autumn=False):
    height = min(TREE_HEIGHTS, key=lambda h: abs(h - height))
    prefix = f"city_botany_{round(height * 100)}_{seed % 2}"
    yaw = seed * 0.733
    beam(
        parent,
        name + "_trunk",
        (u, v, base),
        (u + 0.025 * np.cos(yaw), v + 0.025 * np.sin(yaw), base + height * 0.68),
        0.09,
        "bark",
        True,
    ).set("rgba", "0 0 0 0")
    geom(
        parent,
        name + "_wood",
        "mesh",
        (u, v, base),
        (1, 1, 1),
        "bark",
        False,
        mesh=prefix + "_wood",
        euler=(0, 0, yaw),
    )
    for i, color in enumerate(
        ("leaf_dark", "leaf_mid", "leaf_light")
        if not autumn
        else ("leaf_dark", "leaf_gold", "leaf_gold")
    ):
        geom(
            parent,
            name + f"_canopy_{i}",
            "mesh",
            (u, v, base),
            (1, 1, 1),
            color,
            False,
            mesh=prefix + f"_leaf_{i}",
            euler=(0, 0, yaw),
        )
    geom(
        parent,
        name + "_uplight",
        "cylinder",
        (u, v, base + 0.012),
        (0.14, 0.012),
        "gold" if autumn else "mint",
        False,
    )
