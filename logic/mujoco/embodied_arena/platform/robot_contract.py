"""Public G1 contract and explicit joint-order mapping, with no world truth."""

from __future__ import annotations

import json

import numpy as np

from embodied_arena.config import ROOT

ROBOT_ID = "unitree_g1_29dof"


def descriptor():
    calibration = json.loads((ROOT / "configs/g1_actuators.json").read_text(encoding="utf-8"))
    return {
        "id": ROBOT_ID,
        "api_version": 1,
        "dof": 29,
        "control_mode": "joint_position",
        "joint_unit": "rad",
        "joint_names": calibration["dof_names"],
        "home": calibration["home"],
        "kp": calibration["kp"],
        "kd": calibration["kd"],
        "control_hz": 50,
        "camera_hz": 10,
        "base_quaternion_order": "wxyz",
        "note": "默认动作按观测 joint_names 排列；action_joint_names 可显式声明另一套完整的 29 关节输出顺序",
    }


def validate_manifest(manifest):
    robot = descriptor()
    if manifest.get("robot_id", ROBOT_ID) != ROBOT_ID:
        raise ValueError(f"机器人不匹配：当前仅支持 {ROBOT_ID}，不能上传其他本体的控制代码直接参赛")
    if manifest.get("control_mode", "joint_position") != "joint_position":
        raise ValueError("动作模式必须为 joint_position；平台不接受直接力矩或速度命令")
    if manifest.get("joint_unit", "rad") != "rad":
        raise ValueError("关节输出单位必须为 rad（弧度），不能直接返回角度制")
    names = manifest.get("action_joint_names")
    if names is not None and (
        not isinstance(names, list)
        or len(names) != 29
        or any(not isinstance(n, str) for n in names)
        or len(set(names)) != 29
        or set(names) != set(robot["joint_names"])
    ):
        raise ValueError(
            "action_joint_names 必须包含 G1 全部 29 个关节且不能重复；12/23 关节策略需要选手补齐控制后再提交"
        )
    return names


def reorder(targets, declared_names, observed_names):
    if declared_names is None:
        return targets
    if len(declared_names) != len(observed_names) or set(declared_names) != set(observed_names):
        raise ValueError("声明的输出关节与实际机器人不匹配")
    indices = {name: index for index, name in enumerate(declared_names)}
    return np.asarray(targets)[[indices[name] for name in observed_names]].copy()
