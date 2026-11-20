"""Downloadable beginner baseline; uses only the public observation and local weights."""

import json
from pathlib import Path

import numpy as np
import onnxruntime as ort
from api import Action, Observation

ROOT = Path(__file__).resolve().parent


def gravity(quat):
    w, x, y, z = quat
    return [2 * (w * y - z * x), -2 * (z * y + w * x), 1 - 2 * (w * w + z * z)]


class Policy:
    def __init__(self, player_id=0, config=None):
        robot = json.loads((ROOT / "robot.json").read_text(encoding="utf-8"))
        self.home = np.asarray(robot["home"])
        self.names = robot["joint_names"]
        self.options = json.loads((ROOT / "starter.json").read_text(encoding="utf-8"))
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 1
        opts.inter_op_num_threads = 1
        self.session = ort.InferenceSession(
            str(ROOT / "models/walk.onnx"), opts, providers=["CPUExecutionProvider"]
        )
        self.reset = -1

    def act(self, observation: Observation) -> Action:
        if self.reset != observation["reset_count"]:
            self.reset = observation["reset_count"]
            self.last = np.zeros(29, dtype=np.float32)
            self.phase = np.array([0.0, np.pi])
            self.started = observation["time"]
            self.standing = False
        p = observation["proprio"]
        elapsed = observation["time"] - self.started
        command = np.array([0.0, 0.0, 0.0])
        if elapsed > 2 and observation["game"]["alive"]:
            command[0] = min(0.25, max(0.0, float(self.options.get("speed", 0.15))))
            visual = observation["visual"]
            if self.options.get("avoid_obstacles", True) and visual:
                d = visual["depth"]
                h, w = d.shape
                center = d[h // 3 : 2 * h // 3, w // 3 : 2 * w // 3]
                valid = center[np.isfinite(center) & (center > 0.05)]
                if len(valid) and np.percentile(valid, 20) < 1.4:
                    command[:] = [0.0, 0.0, 0.25]
        order = [p["joint_names"].index(n) for n in self.names]
        terms = {
            "actions": self.last,
            "base_ang_vel": np.asarray(p["gyro"]) * 0.25,
            "command_ang_vel": [command[2]],
            "command_lin_vel": command[:2],
            "cos_phase": np.cos(self.phase),
            "dof_pos": np.asarray(p["q"])[order] - self.home,
            "dof_vel": np.asarray(p["dq"])[order] * 0.05,
            "projected_gravity": gravity(p["base_quat"]),
            "sin_phase": np.sin(self.phase),
        }
        inputs = np.concatenate([terms[n] for n in sorted(terms)]).astype(np.float32)[None]
        self.last = self.session.run(None, {"actor_obs": inputs})[0].reshape(29).copy()
        self.phase = (self.phase + 2 * np.pi * 0.02 + np.pi) % (2 * np.pi) - np.pi
        if np.linalg.norm(command) < 0.01:
            self.phase[:] = np.pi
            self.standing = True
        elif self.standing:
            self.phase[:] = [0, np.pi]
            self.standing = False
        target = self.home + 0.25 * self.last
        return {
            "joint_targets": np.asarray([target[self.names.index(n)] for n in p["joint_names"]]),
            "fire": False,
        }
