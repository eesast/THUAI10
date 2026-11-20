from __future__ import annotations

import copy
import json
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

from .config import ROOT, MatchConfig

CALIBRATION = json.loads((ROOT / "configs/g1_actuators.json").read_text(encoding="utf-8"))

LEG_NAMES = [
    f"{side}_{name}_joint"
    for side in ("left", "right")
    for name in ("hip_pitch", "hip_roll", "hip_yaw", "knee", "ankle_pitch", "ankle_roll")
]
LEG_HOME = np.array([-0.1, 0, 0, 0.3, -0.2, 0] * 2)
COLORS = {
    "red": (0.88, 0.08, 0.07, 1),
    "blue": (0.06, 0.25, 0.95, 1),
    "green": (0.07, 0.8, 0.24, 1),
    "yellow": (0.95, 0.75, 0.05, 1),
}
TARGETS = [
    {"id": "red_cup", "color": "red", "owner": None, "text": "找到并命中红色杯子。"},
    {"id": "blue_cup", "color": "blue", "owner": 0, "text": "找到并命中蓝色杯子。"},
    {"id": "green_cup", "color": "green", "owner": 1, "text": "找到并命中绿色杯子。"},
]


def get_targets(config):
    if config.scene == "cyber_city":
        from .city import city_targets

        targets = city_targets(config.seed, config.task_set)
    else:
        targets = [dict(t) for t in TARGETS]
    if config.spawn_swap:
        targets = [{**t, "owner": None if t["owner"] is None else 1 - t["owner"]} for t in targets]
    return targets


def _numbers(values):
    return " ".join(f"{v:.9g}" for v in values)


def build_xml(config: MatchConfig, count: int = 2, room: bool = True) -> str:
    is_city = room and config.scene == "cyber_city"
    source = ROOT / "third_party/g1/g1.xml"
    if not source.exists():
        raise FileNotFoundError(
            "Missing G1 assets. From repository root run: "
            "python dependency/shell/mujoco/fetch_assets.py"
        )
    original = ET.parse(source).getroot()
    root = ET.Element("mujoco", model="EmbodiedArena_G1")
    ET.SubElement(root, "compiler", angle="radian", meshdir="assets")
    ET.SubElement(root, "option", timestep=str(config.physics_dt), integrator="implicitfast")
    ET.SubElement(root, "size", njmax="4000", nconmax="800")
    if is_city:
        ET.SubElement(root, "statistic", center="0 16.5 4", extent="70")
    visual = ET.SubElement(root, "visual")
    ET.SubElement(
        visual,
        "global",
        offwidth=str(max(1600 if is_city else 960, config.width)),
        offheight=str(max(1000 if is_city else 720, config.height)),
    )
    ET.SubElement(visual, "headlight", ambient="0.4 0.4 0.4", diffuse="0.8 0.8 0.8")
    defaults = copy.deepcopy(original.find("default"))
    for position in defaults.iter("position"):
        position.attrib.pop("dampratio", None)
    for joint in defaults.iter("joint"):
        joint.set("frictionloss", "0.1")
        joint.set("damping", "0.001")
    root.append(defaults)
    assets = copy.deepcopy(original.find("asset"))
    ET.SubElement(
        assets,
        "texture",
        name="floor_tex",
        type="2d",
        builtin="checker",
        rgb1=".24 .28 .32",
        rgb2=".30 .34 .38",
        width="512",
        height="512",
    )
    ET.SubElement(
        assets,
        "material",
        name="floor_mat",
        texture="floor_tex",
        texrepeat="8 6",
        texuniform="true",
    )
    root.append(assets)
    world = ET.SubElement(root, "worldbody")
    ET.SubElement(world, "light", pos="0 0 4", dir="0 0 -1", directional="true")
    ET.SubElement(
        world,
        "geom",
        name="floor",
        type="plane",
        size="5 4 .05",
        material="floor_mat",
        friction=".9 .005 .0001",
    )
    pos = np.array([6.0, -7.0, 4.8])
    forward = np.array([0.0, 0.0, 0.7]) - pos
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, [0, 0, 1])
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    ET.SubElement(
        world,
        "camera",
        name="overview",
        pos=_numbers(pos),
        xyaxes=_numbers([*right, *up]),
        fovy="48",
    )
    actuator = ET.SubElement(root, "actuator")
    for pid in range(count):
        prefix = f"p{pid}/"
        robot = copy.deepcopy(original.find("worldbody/body"))
        for element_index, element in enumerate(robot.iter()):
            for field in ("name", "joint", "site", "body", "target", "objname"):
                if field in element.attrib:
                    element.set(field, prefix + element.get(field))
            if element.tag == "geom":
                if "name" not in element.attrib:
                    element.set("name", f"{prefix}geom_{element_index}")
                element.set("group", "4" if element.get("class") == "visual" else str(pid + 1))
        if is_city:
            from .city import SPAWNS

            spawn = SPAWNS[1 - pid if config.spawn_swap else pid]
        else:
            spawn = (
                [-1.5, -1.1 if (1 - pid if config.spawn_swap else pid) == 0 else 1.1, 0.79]
                if room
                else [0, 0, 0.79]
            )
        robot.set("pos", _numbers(spawn))
        torso = next(b for b in robot.iter("body") if b.get("name") == prefix + "torso_link")
        ET.SubElement(
            torso, "camera", name=prefix + "eye", pos=".12 0 .30", xyaxes="0 -1 0 0 0 1", fovy="70"
        )
        wrist = next(
            b for b in robot.iter("body") if b.get("name") == prefix + "right_wrist_yaw_link"
        )
        for group, collide in ((str(pid + 1), True), ("4", False)):
            ET.SubElement(
                wrist,
                "geom",
                name=prefix + ("gun_collision" if collide else "gun_visual"),
                type="capsule",
                fromto=".06 0 0 .24 0 0",
                size=".016",
                rgba=".95 .6 .12 1",
                group=group,
                mass=".06" if collide else "0",
                contype="1" if collide else "0",
                conaffinity="1" if collide else "0",
            )
        ET.SubElement(
            wrist, "site", name=prefix + "muzzle", pos=".26 0 0", size=".009", rgba="1 0 0 1"
        )
        world.append(robot)
        for index, source_motor in enumerate(original.find("actuator")):
            motor = copy.deepcopy(source_motor)
            for field in ("name", "joint"):
                motor.set(field, prefix + motor.get(field))
            joint_name = source_motor.get("joint")
            calibration_index = CALIBRATION["dof_names"].index(joint_name)
            kp, kd = CALIBRATION["kp"][calibration_index], CALIBRATION["kd"][calibration_index]
            motor.set("kp", str(kp))
            motor.set("kv", str(kd))
            actuator.append(motor)
    if is_city:
        from .city import build_city

        build_city(assets, world, visual, config)
    if room and not is_city:
        for name, pos, size in [
            ("back_wall", [4, 0, 1.5], [0.08, 3, 1.5]),
            ("left_wall", [0, 3, 1.5], [4, 0.08, 1.5]),
            ("right_wall", [0, -3, 1.5], [4, 0.08, 1.5]),
            ("front_wall", [-4, 0, 1.5], [0.08, 3, 1.5]),
            ("table", [2, 0, 0.75], [0.45, 2.35, 0.05]),
            ("table_leg_a", [2, -1.9, 0.35], [0.12, 0.12, 0.35]),
            ("table_leg_b", [2, 1.9, 0.35], [0.12, 0.12, 0.35]),
            ("cabinet", [-0.3, 2.55, 0.55], [0.5, 0.3, 0.55]),
        ]:
            ET.SubElement(
                world,
                "geom",
                name=name,
                type="box",
                pos=_numbers(pos),
                size=_numbers(size),
                rgba=".65 .62 .55 1",
                group="5" if "wall" in name else "0",
            )
    if room:
        rng = np.random.default_rng(config.seed)
        if is_city:
            placements = [(target, target["position"]) for target in get_targets(config)]
        else:
            placements = [
                (target, [2, y + rng.uniform(-0.08, 0.08), 0.93])
                for target, y in zip(
                    TARGETS + [{"id": "yellow_cup", "color": "yellow"}], [0, -1.65, 1.65, 0.75]
                )
            ]
        for target, position in placements:
            body = ET.SubElement(world, "body", name=target["id"], pos=_numbers(position))
            rgba = _numbers(COLORS[target["color"]])
            from .objects import add_shape

            add_shape(body, target["id"], target.get("shape", "cup"), rgba)
    if is_city and config.task_set == "mixed-v1":
        from .objects import distractors

        distractors(world, config)
    return ET.tostring(root, encoding="unicode")


class RobotBinding:
    def __init__(self, model: mujoco.MjModel, pid: int):
        self.pid = pid
        self.prefix = f"p{pid}/"
        self.body = model.body(self.prefix + "pelvis").id
        root_joint = int(model.body_jntadr[self.body])
        self.root_q = int(model.jnt_qposadr[root_joint])
        self.root_v = int(model.jnt_dofadr[root_joint])
        self.actuators = np.array(
            [i for i in range(model.nu) if model.actuator(i).name.startswith(self.prefix)]
        )
        self.joints = model.actuator_trnid[self.actuators, 0]
        self.names = [model.joint(int(j)).name[len(self.prefix) :] for j in self.joints]
        self.q = model.jnt_qposadr[self.joints]
        self.v = model.jnt_dofadr[self.joints]
        self.limits = model.jnt_range[self.joints].copy()
        self.legs = np.array([self.names.index(name) for name in LEG_NAMES])
        self.home = np.array(
            [CALIBRATION["home"][CALIBRATION["dof_names"].index(name)] for name in self.names]
        )
        self.muzzle = model.site(self.prefix + "muzzle").id
        self.camera = model.camera(self.prefix + "eye").id
        self.spawn = model.qpos0[self.root_q : self.root_q + 7].copy()

    def reset(self, model, data):
        data.qpos[self.root_q : self.root_q + 7] = self.spawn
        data.qpos[self.q] = self.home
        data.qvel[self.root_v : self.root_v + 6] = 0
        data.qvel[self.v] = 0
        data.ctrl[self.actuators] = self.home


def load_model(xml: str):
    # Supply bytes through MuJoCo's VFS: native mesh file loading can fail on
    # non-ASCII Windows workspace paths. Python's Path handles these paths.
    assets = {
        path.name: path.read_bytes() for path in (ROOT / "third_party/g1/assets").glob("*.STL")
    }
    if "city_sky" in xml:
        from .city_art import ART, ensure_art

        ensure_art()
        assets.update({path.name: path.read_bytes() for path in ART.glob("*.png")})
    return mujoco.MjModel.from_xml_string(xml, assets=assets)


def make_world(config: MatchConfig, count: int = 2, room: bool = True):
    xml = build_xml(config, count, room)
    model = load_model(xml)
    data = mujoco.MjData(model)
    robots = [RobotBinding(model, pid) for pid in range(count)]
    for robot in robots:
        robot.reset(model, data)
    if room and config.scene == "cyber_city":
        from .city_actors import CityMotion

        CityMotion(model).update(data, 0.0)
    mujoco.mj_forward(model, data)
    return model, data, robots, xml
