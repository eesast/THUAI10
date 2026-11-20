"""Internal validation policies, not a competition benchmark or official solution."""

from __future__ import annotations

import mujoco
import numpy as np

from .config import MatchConfig
from .locomotion import HolosomaWalking
from .scene import make_world


class HoldPose:
    """Minimal SDK example: read joint angles and send position targets."""

    def __init__(self, player_id=0, config=None):
        self.q = None
        self.reset_count = -1

    def act(self, observation):
        if observation["reset_count"] != self.reset_count:
            self.q = observation["proprio"]["q"].copy()
            self.reset_count = observation["reset_count"]
        return {"joint_targets": self.q.copy(), "fire": False}


class WalkInPlace:
    def __init__(self, player_id=0, config=None):
        self.walk = HolosomaWalking()
        self.reset_count = -1

    def act(self, observation):
        if observation["reset_count"] != self.reset_count:
            self.walk.reset()
            self.reset_count = observation["reset_count"]
        p = observation["proprio"]
        return {
            "joint_targets": self.walk.act(
                p["q"], p["dq"], p["gyro"], p["base_quat"], observation["time"], [0, 0, 0]
            ),
            "fire": False,
        }


class DiagnosticVision:
    """RGB reference color retrieval + depth + own-robot IK + pretrained gait.

    Only public robot geometry and the supplied observation are used. No actual
    arena MjData, target coordinates or opponent state are accessible here.
    It is deliberately limited to the prototype's colored-cup scenes.
    """

    def __init__(self, player_id=0, config=None):
        self.player_id = player_id
        self.config = MatchConfig(**(config or {}))
        self.model, self.data, robots, _ = make_world(self.config, count=1, room=False)
        self.robot = robots[0]
        self.walk = HolosomaWalking()
        self.arm = np.array(
            [
                self.robot.names.index(name)
                for name in ("right_wrist_pitch_joint", "right_wrist_yaw_joint")
            ]
        )
        self.reset_count = -1
        self.target = self.robot.home.copy()
        self.target_command = self.target[self.arm].copy()
        self.last_visual_time = -1
        self.alignment = 1.0
        self.aim_point = None
        self.started = 0.0
        self.command = [0.0, 0.0, 0.0]

    @staticmethod
    def find_target(visual, tasks):
        rgb = visual["rgb"].astype(float) / 255
        chroma = rgb / np.maximum(rgb.sum(axis=2, keepdims=True), 0.01)
        saturation = rgb.max(axis=2) - rgb.min(axis=2)
        for task in tasks:
            reference = task["reference_rgb"].astype(float) / 255
            saturated = reference.max(axis=2) - reference.min(axis=2) > 0.25
            color = np.median(reference[saturated], axis=0)
            color /= color.sum()
            mask = (np.linalg.norm(chroma - color, axis=2) < 0.15) & (saturation > 0.20)
            yy, xx = np.where(mask)
            if len(xx) < 4:
                continue
            x, y = float(np.median(xx)), float(np.median(yy))
            depth = float(np.median(visual["depth"][mask]))
            if not 0.1 < depth < 10:
                continue
            focal = rgb.shape[0] / (2 * np.tan(np.deg2rad(visual["fovy_degrees"]) / 2))
            camera_point = np.array(
                [
                    (x - (rgb.shape[1] - 1) / 2) * depth / focal,
                    -(y - (rgb.shape[0] - 1) / 2) * depth / focal,
                    -depth,
                ]
            )
            return camera_point
        return None

    def aim(self, observation, camera_point):
        r, m, d = self.robot, self.model, self.data
        # The shadow robot's base has no global arena position.
        d.qpos[r.root_q : r.root_q + 3] = 0
        d.qpos[r.root_q + 3 : r.root_q + 7] = observation["proprio"]["base_quat"]
        d.qpos[r.q] = observation["proprio"]["q"]
        mujoco.mj_forward(m, d)
        point = d.cam_xpos[r.camera] + d.cam_xmat[r.camera].reshape(3, 3) @ camera_point
        self.aim_point = point
        jac_position = np.zeros((3, m.nv))
        jac_rotation = np.zeros((3, m.nv))
        for _ in range(20):
            position = d.site_xpos[r.muzzle]
            direction = point - position
            distance = np.linalg.norm(direction)
            direction /= max(distance, 0.001)
            axis = d.site_xmat[r.muzzle].reshape(3, 3)[:, 0]
            error = direction - axis
            if np.linalg.norm(error) < 0.002:
                break
            mujoco.mj_jacSite(m, d, jac_position, jac_rotation, r.muzzle)
            x, y, z = axis
            skew = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
            jacobian = (
                -skew @ jac_rotation
                + (np.eye(3) - np.outer(direction, direction)) @ jac_position / max(distance, 0.001)
            )[:, r.v[self.arm]]
            delta = jacobian.T @ np.linalg.solve(jacobian @ jacobian.T + 0.003 * np.eye(3), error)
            delta *= min(1.0, 0.15 / max(float(np.max(np.abs(delta))), 0.001))
            d.qpos[r.q[self.arm]] += delta
            d.qpos[r.q[self.arm]] = np.clip(
                d.qpos[r.q[self.arm]], r.limits[self.arm, 0], r.limits[self.arm, 1]
            )
            mujoco.mj_forward(m, d)
        self.target[self.arm] = d.qpos[r.q[self.arm]]

    def act(self, observation):
        if observation["reset_count"] != self.reset_count:
            self.walk.reset()
            self.reset_count = observation["reset_count"]
            self.started = observation["time"]
            self.target = self.robot.home.copy()
            self.target_command = self.target[self.arm].copy()
            self.last_visual_time = -1
            self.aim_point = None
            self.command = [0.0, 0.0, 0.0]
        p = observation["proprio"]
        elapsed = observation["time"] - self.started
        visual = observation["visual"]
        target = self.walk.act(p["q"], p["dq"], p["gyro"], p["base_quat"], elapsed, self.command)
        tasks = sorted(
            observation["tasks"],
            key=lambda task: task["kind"] != ("public" if self.player_id == 0 else "private"),
        )
        fire = False
        if elapsed > 1.5 and visual is not None and visual["time"] != self.last_visual_time:
            self.last_visual_time = visual["time"]
            point = self.find_target(visual, tasks)
            if point is not None:
                bearing = -np.arctan2(point[0], -point[2])
                self.command = [
                    0.18 if -point[2] > 2.4 and abs(bearing) < 0.5 else 0.0,
                    0.0,
                    float(np.clip(bearing, -0.3, 0.3)),
                ]
                self.aim(observation, point)
                # Check measured arm pose, not the requested IK pose.
                r = self.robot
                self.data.qpos[r.q] = p["q"]
                mujoco.mj_forward(self.model, self.data)
                direction = self.aim_point - self.data.site_xpos[r.muzzle]
                direction /= np.linalg.norm(direction)
                axis = self.data.site_xmat[r.muzzle].reshape(3, 3)[:, 0]
                self.alignment = float(np.dot(axis, direction))
                fire = self.alignment > 0.9997 and elapsed > 2.5 and observation["game"]["alive"]
            else:
                self.command = [0.0, 0.0, 0.15 if tasks else 0.0]
        if not tasks or not observation["game"]["alive"]:
            self.command = [0.0, 0.0, 0.0]
        if self.aim_point is not None and tasks:
            target[self.arm] = np.clip(
                self.target[self.arm], self.target_command - 0.008, self.target_command + 0.008
            )
            self.target_command = target[self.arm].copy()
        return {
            "joint_targets": np.clip(target, self.robot.limits[:, 0], self.robot.limits[:, 1]),
            "fire": bool(fire),
        }
