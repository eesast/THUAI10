"""Deterministic prescribed motion. Contestant robots remain fully dynamic."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import mujoco
import numpy as np

from .city import beam, geom, numbers, ring

VEHICLES = [
    {"name": "traffic/azure", "lane": -1.25, "direction": 1, "speed": 1.6, "offset": 18.0},
    {"name": "traffic/violet", "lane": 1.25, "direction": -1, "speed": 1.3, "offset": 34.0},
    {"name": "traffic/courier", "lane": -1.25, "direction": 1, "speed": 1.6, "offset": 43.0},
    {
        "name": "traffic/living_taxi",
        "lane": 28.5,
        "direction": 1,
        "speed": 1.2,
        "offset": 21.0,
        "accent": "amber",
    },
    {
        "name": "traffic/living_delivery",
        "lane": 31.5,
        "direction": -1,
        "speed": 1.1,
        "offset": 42.0,
        "accent": "mint",
    },
    {
        "name": "traffic/living_cab",
        "lane": 28.5,
        "direction": 1,
        "speed": 1.2,
        "offset": 51.0,
        "accent": "amber",
    },
]
PEDESTRIANS = [
    {
        "name": "citizen/01",
        "kind": "robot",
        "center": (-9.5, 4.65),
        "radius": 4.6,
        "speed": 0.50,
        "phase": 0.0,
    },
    {
        "name": "citizen/02",
        "kind": "robot",
        "center": (10.0, -4.7),
        "radius": 4.4,
        "speed": 0.45,
        "phase": 2.0,
    },
    {
        "name": "dog/01",
        "kind": "dog",
        "center": (8.0, 3.55),
        "radius": 5.3,
        "speed": 0.68,
        "phase": 1.0,
    },
    {
        "name": "dog/02",
        "kind": "dog",
        "center": (-10.0, -3.55),
        "radius": 4.8,
        "speed": 0.60,
        "phase": 3.2,
    },
    {
        "name": "dog/03",
        "kind": "dog",
        "center": (22.0, 3.55),
        "radius": 4.5,
        "speed": 0.65,
        "phase": 0.5,
    },
    {
        "name": "dog/04",
        "kind": "dog",
        "center": (22.0, -3.55),
        "radius": 4.0,
        "speed": 0.63,
        "phase": 2.4,
    },
    {
        "name": "dog/05",
        "kind": "dog",
        "center": (-23.0, 3.55),
        "radius": 4.4,
        "speed": 0.60,
        "phase": 1.8,
    },
    {
        "name": "dog/06",
        "kind": "dog",
        "center": (-23.0, -3.55),
        "radius": 4.4,
        "speed": 0.66,
        "phase": 4.1,
    },
    {
        "name": "citizen/03",
        "kind": "robot",
        "center": (8.0, 24.6),
        "radius": 4.4,
        "speed": 0.45,
        "phase": 1.0,
    },
    {
        "name": "dog/07",
        "kind": "dog",
        "center": (-10.0, 26.2),
        "radius": 5.0,
        "speed": 0.60,
        "phase": 1.8,
    },
    {
        "name": "dog/08",
        "kind": "dog",
        "center": (22.0, 33.7),
        "radius": 4.0,
        "speed": 0.60,
        "phase": 2.7,
    },
]
DRONES = []
for band, (count, height, rx, ry, omega) in enumerate(
    ((3, 4.2, 20.0, 1.0, 0.055), (2, 8.8, 26.0, 1.8, 0.040), (2, 15.5, 29.0, 2.8, 0.028))
):
    for j in range(count):
        DRONES.append(
            {
                "name": f"drone/{len(DRONES) + 1:02d}",
                "band": band,
                "height": height + j * 0.12,
                "rx": rx,
                "ry": ry,
                "cy": 30.0 if j == 1 else 0.0,
                "omega": omega,
                "phase": j * 2 * np.pi / count + band * 0.6,
                "scale": 1 + band * 0.15,
            }
        )


def yaw_quat(angle):
    return np.array([np.cos(angle / 2), 0.0, 0.0, np.sin(angle / 2)])


def multiply(a, b):
    out = np.empty(4)
    mujoco.mju_mulQuat(out, a, b)
    return out


def pedestrian_pose(spec, t):
    phase = t * spec["speed"] / spec["radius"] + spec["phase"]
    x = spec["center"][0] + spec["radius"] * np.sin(phase)
    direction = 1 if np.cos(phase) >= 0 else -1
    height = 0.82 if spec["kind"] == "robot" else 0.62
    return np.array([x, spec["center"][1], height + 0.018 * np.sin(t * 7)]), yaw_quat(
        0 if direction == 1 else np.pi
    )


def vehicle_pose(spec, t):
    x = -36.0 + (spec["offset"] + t * spec["speed"]) % 72.0
    return np.array(
        [x * spec["direction"], spec["lane"], 0.65 + 0.035 * np.sin(t * 2.2 + spec["offset"])]
    ), yaw_quat(0 if spec["direction"] == 1 else np.pi)


def drone_pose(spec, t):
    angle = t * spec["omega"] + spec["phase"]
    pos = np.array(
        [
            spec["rx"] * np.cos(angle),
            spec.get("cy", 0.0) + spec["ry"] * np.sin(angle),
            spec["height"] + 0.18 * np.sin(t * 0.7 + spec["phase"]),
        ]
    )
    yaw = np.arctan2(spec["ry"] * np.cos(angle), -spec["rx"] * np.sin(angle))
    return pos, yaw_quat(yaw)


def mocap(world, name, pos, quat=(1, 0, 0, 0)):
    return ET.SubElement(
        world, "body", name=name, mocap="true", pos=numbers(pos), quat=numbers(quat)
    )


def add_actors(world, traffic_enabled=True):
    if traffic_enabled:
        for i, spec in enumerate(VEHICLES):
            name = spec["name"]
            position, quat = vehicle_pose(spec, 0)
            body = mocap(world, name, position, quat)
            accent = spec.get("accent", "cyan" if i % 2 == 0 else "purple")
            geom(body, name + "/hull", "box", (0, 0, 0), (1.25, 0.58, 0.18), "metal", mass="180")
            geom(
                body,
                name + "/nose",
                "ellipsoid",
                (0.55, 0, 0.08),
                (0.9, 0.60, 0.27),
                "panel",
                False,
            )
            geom(
                body,
                name + "/cockpit",
                "ellipsoid",
                (-0.12, 0, 0.31),
                (0.76, 0.47, 0.30),
                "glass",
                False,
            )
            for side in (-1, 1):
                beam(
                    body,
                    name + f"/rail_{side}",
                    (-1.15, side * 0.60, 0.02),
                    (1.1, side * 0.60, 0.02),
                    0.025,
                    accent,
                )
                beam(
                    body,
                    name + f"/headlight_{side}",
                    (1.27, side * 0.48, 0.10),
                    (1.34, side * 0.25, 0.10),
                    0.045,
                    "cyan",
                )
                beam(
                    body,
                    name + f"/tail_{side}",
                    (-1.27, side * 0.48, 0.08),
                    (-1.27, side * 0.22, 0.08),
                    0.04,
                    "pink",
                )
                for x in (-0.85, 0.85):
                    geom(
                        body,
                        name + f"/thruster_{side}_{x}",
                        "cylinder",
                        (x, side * 0.42, -0.23),
                        (0.18, 0.10),
                        "dark",
                        False,
                    )
                    geom(
                        body,
                        name + f"/exhaust_{side}_{x}",
                        "ellipsoid",
                        (x, side * 0.42, -0.36),
                        (0.13, 0.13, 0.17),
                        accent,
                        False,
                    )
            if "living_" in name:
                geom(
                    body,
                    name + "/cab_sign",
                    pos=(0, 0, 0.72),
                    size=(0.23, 0.13, 0.07),
                    material=accent,
                    solid=False,
                )
    for spec in PEDESTRIANS:
        name = spec["name"]
        position, quat = pedestrian_pose(spec, 0)
        body = mocap(world, name, position, quat)
        if spec["kind"] == "robot":
            geom(
                body,
                name + "/collision",
                "capsule",
                size=(0.20,),
                fromto=(0, 0, -0.55, 0, 0, 0.45),
                material="metal",
            )
            geom(body, name + "/shell", "box", (0, 0, 0.25), (0.20, 0.145, 0.24), "panel", False)
            geom(
                body, name + "/head", "ellipsoid", (0, 0, 0.65), (0.16, 0.13, 0.14), "metal", False
            )
            geom(
                body, name + "/visor", "box", (0.145, 0, 0.65), (0.018, 0.105, 0.045), "cyan", False
            )
            beam(body, name + "/chest", (0.205, -0.11, 0.35), (0.205, 0.11, 0.35), 0.022, "purple")
            for side in (-1, 1):
                limb = mocap(world, name + f"/leg_{side}", position, quat)
                beam(limb, name + f"/shin_{side}", (0, 0, 0), (0.04, 0, -0.46), 0.055, "metal")
                geom(
                    limb,
                    name + f"/foot_{side}",
                    "box",
                    (0.10, 0, -0.47),
                    (0.14, 0.075, 0.04),
                    "panel",
                    False,
                )
                limb = mocap(world, name + f"/arm_{side}", position, quat)
                beam(limb, name + f"/upper_arm_{side}", (0, 0, 0), (0.03, 0, -0.38), 0.052, "metal")
        else:
            geom(body, name + "/collision", "box", (0, 0, 0), (0.38, 0.18, 0.16), "metal")
            geom(body, name + "/head", "box", (0.44, 0, 0.08), (0.18, 0.14, 0.13), "panel", False)
            geom(
                body, name + "/visor", "box", (0.626, 0, 0.10), (0.012, 0.10, 0.035), "cyan", False
            )
            beam(body, name + "/backlight", (-0.3, 0, 0.17), (0.25, 0, 0.17), 0.023, "purple")
            for x in (-0.22, 0, 0.22):
                geom(
                    body,
                    name + f"/spine_plate_{x}",
                    "box",
                    (x, 0, 0.18),
                    (0.085, 0.16, 0.025),
                    "panel",
                    False,
                )
            for side in (-1, 1):
                beam(
                    body,
                    name + f"/ear_{side}",
                    (0.43, side * 0.11, 0.20),
                    (0.40, side * 0.14, 0.35),
                    0.025,
                    "metal",
                )
                geom(
                    body,
                    name + f"/sensor_{side}",
                    "sphere",
                    (0.636, side * 0.07, 0.13),
                    (0.026,),
                    "amber",
                    False,
                )
            for front in (-1, 1):
                for side in (-1, 1):
                    limb = mocap(world, name + f"/leg_{front}_{side}", position, quat)
                    beam(
                        limb,
                        name + f"/thigh_{front}_{side}",
                        (0, 0, 0),
                        (-0.07, 0, -0.22),
                        0.035,
                        "metal",
                    )
                    beam(
                        limb,
                        name + f"/calf_{front}_{side}",
                        (-0.07, 0, -0.22),
                        (0.07, 0, -0.43),
                        0.029,
                        "panel",
                    )
                    geom(
                        limb,
                        name + f"/knee_{front}_{side}",
                        "cylinder",
                        (-0.07, 0, -0.22),
                        (0.052, 0.035),
                        "metal",
                        False,
                        euler=(np.pi / 2, 0, 0),
                    )
    for spec in DRONES:
        name = spec["name"]
        s = spec["scale"]
        pos, quat = drone_pose(spec, 0)
        body = mocap(world, name, pos, quat)
        accent = ("cyan", "amber", "pink")[spec["band"]]
        geom(
            body,
            name + "/body",
            "ellipsoid",
            size=(0.32 * s, 0.26 * s, 0.13 * s),
            material="metal",
            solid=False,
        )
        geom(body, name + "/eye", "sphere", (0.25 * s, 0, -0.05 * s), (0.065 * s,), accent, False)
        geom(
            body,
            name + "/cargo",
            "box",
            (-0.04 * s, 0, -0.18 * s),
            (0.18 * s, 0.15 * s, 0.07 * s),
            "panel",
            False,
        )
        for sx in (-1, 1):
            for sy in (-1, 1):
                beam(
                    body,
                    name + f"/arm_{sx}_{sy}",
                    (0, 0, 0),
                    (sx * 0.52 * s, sy * 0.52 * s, 0),
                    0.04 * s,
                    "metal",
                )
                ring(
                    body,
                    name + f"/rotor_{sx}_{sy}",
                    (sx * 0.52 * s, sy * 0.52 * s, 0.02 * s),
                    0.23 * s,
                    accent,
                    12,
                    0.016 * s,
                )
                rotor = mocap(world, name + f"/blade_{sx}_{sy}", pos, quat)
                beam(
                    rotor,
                    name + f"/blade_geom_{sx}_{sy}",
                    (-0.19 * s, 0, 0),
                    (0.19 * s, 0, 0),
                    0.018 * s,
                    "metal",
                )
    train = mocap(world, "transit/skytrain", (-26, 53, 10.8))
    for i in (-1, 0, 1):
        geom(
            train,
            f"skytrain_body_{i}",
            pos=(i * 3, 0, 0),
            size=(1.4, 0.64, 0.52),
            material="metal",
            solid=False,
        )
        for side in (-1, 1):
            beam(
                train,
                f"skytrain_line_{i}_{side}",
                (i * 3 - 1.3, side * 0.66, -0.32),
                (i * 3 + 1.3, side * 0.66, -0.32),
                0.025,
                "amber",
            )
            for j in range(4):
                geom(
                    train,
                    f"skytrain_window_{i}_{side}_{j}",
                    pos=(i * 3 - 0.9 + j * 0.6, side * 0.65, 0.12),
                    size=(0.22, 0.015, 0.23),
                    material="cyan",
                    solid=False,
                )


class CityMotion:
    def __init__(self, model):
        self.model = model
        self._background_frame = None
        self.ids = {
            model.body(i).name: int(mid) for i, mid in enumerate(model.body_mocapid) if mid >= 0
        }
        self.vehicle_geoms = {}
        for gid in range(model.ngeom):
            name = model.geom(gid).name or ""
            if name.startswith("traffic/"):
                self.vehicle_geoms[gid] = "/".join(name.split("/")[:2])

    def set_pose(self, data, name, pos, quat):
        mid = self.ids.get(name)
        if mid is not None:
            data.mocap_pos[mid] = pos
            data.mocap_quat[mid] = quat

    def update(self, data, t):
        for spec in VEHICLES:
            pos, quat = vehicle_pose(spec, t)
            self.set_pose(data, spec["name"], pos, quat)
        # Exact vehicle motion stays at physics rate; decorative animation is
        # evaluated on deterministic 50 Hz frames rather than repeating work.
        frame = int(np.floor((t + 1e-9) / 0.02))
        if frame == self._background_frame:
            return
        self._background_frame = frame
        t = frame * 0.02
        for spec in PEDESTRIANS:
            pos, quat = pedestrian_pose(spec, t)
            name = spec["name"]
            self.set_pose(data, name, pos, quat)
            rotation = np.zeros(9)
            mujoco.mju_quat2Mat(rotation, quat)
            rotation = rotation.reshape(3, 3)
            gait = t * 6.0 + spec["phase"]
            if spec["kind"] == "robot":
                for side in (-1, 1):
                    angle = 0.34 * np.sin(gait + (0 if side == 1 else np.pi))
                    pitch = np.array([np.cos(angle / 2), 0, np.sin(angle / 2), 0])
                    self.set_pose(
                        data,
                        name + f"/leg_{side}",
                        pos + rotation @ np.array([0, side * 0.11, -0.23]),
                        multiply(quat, pitch),
                    )
                    self.set_pose(
                        data,
                        name + f"/arm_{side}",
                        pos + rotation @ np.array([0, side * 0.25, 0.39]),
                        multiply(quat, pitch * np.array([1, 1, -1, 1])),
                    )
            else:
                for front in (-1, 1):
                    for side in (-1, 1):
                        angle = 0.38 * np.sin(gait + (0 if side * front == 1 else np.pi))
                        pitch = np.array([np.cos(angle / 2), 0, np.sin(angle / 2), 0])
                        self.set_pose(
                            data,
                            name + f"/leg_{front}_{side}",
                            pos + rotation @ np.array([front * 0.26, side * 0.17, -0.05]),
                            multiply(quat, pitch),
                        )
        for spec in DRONES:
            pos, quat = drone_pose(spec, t)
            s = spec["scale"]
            name = spec["name"]
            self.set_pose(data, name, pos, quat)
            rotation = np.zeros(9)
            mujoco.mju_quat2Mat(rotation, quat)
            rotation = rotation.reshape(3, 3)
            for sx in (-1, 1):
                for sy in (-1, 1):
                    self.set_pose(
                        data,
                        name + f"/blade_{sx}_{sy}",
                        pos + rotation @ np.array([sx * 0.52 * s, sy * 0.52 * s, 0.025 * s]),
                        multiply(quat, yaw_quat(t * 30)),
                    )
        self.set_pose(
            data,
            "transit/skytrain",
            np.array([-36 + (10 + t * 2.4) % 72, 53, 10.8]),
            np.array([1.0, 0, 0, 0]),
        )

    @staticmethod
    def vehicle_speed(name):
        return next(v["speed"] for v in VEHICLES if v["name"] == name)
