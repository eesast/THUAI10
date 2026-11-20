"""Adapter to Unitree's BSD-3-Clause G1 checkpoint (12 leg joints).

Observation scales, phase and PD settings follow the pinned upstream deployment.
See third_party/unitree_rl_gym/LICENSE and THIRD_PARTY.md.
"""

from __future__ import annotations

import io

import numpy as np

from .config import ROOT
from .scene import CALIBRATION, LEG_HOME


def projected_gravity(quaternion):
    w, x, y, z = quaternion
    return np.array([2 * (w * y - z * x), -2 * (z * y + w * x), 1 - 2 * (w * w + z * z)])


class UnitreeWalking:
    def __init__(self):
        import torch

        self.torch = torch
        torch.set_num_threads(1)
        path = ROOT / "third_party/unitree_rl_gym/motion.pt"
        self.policy = torch.jit.load(io.BytesIO(path.read_bytes()), map_location="cpu").eval()
        self.last = np.zeros(12, dtype=np.float32)

    def reset(self):
        self.last[:] = 0
        if hasattr(self.policy, "reset"):
            self.policy.reset()

    def act(self, q, dq, omega, quat, elapsed, command):
        phase = 2 * np.pi * ((elapsed % 0.8) / 0.8)
        observation = np.concatenate(
            [
                np.asarray(omega) * 0.25,
                projected_gravity(quat),
                np.asarray(command) * [2, 2, 0.25],
                np.asarray(q) - LEG_HOME,
                np.asarray(dq) * 0.05,
                self.last,
                [np.sin(phase), np.cos(phase)],
            ]
        ).astype(np.float32)
        with self.torch.inference_mode():
            self.last = (
                self.policy(self.torch.from_numpy(observation).unsqueeze(0))
                .numpy()
                .reshape(12)
                .copy()
            )
        return LEG_HOME + 0.25 * self.last


class HolosomaWalking:
    """100-observation, 29-action FastSAC policy; CPU-only ONNX inference.

    Observation terms are ALPHABETICALLY sorted by the upstream builder.
    The model metadata, not unrelated robot defaults, supplies actuator gains.
    """

    def __init__(self):
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(
            (ROOT / "third_party/holosoma/fastsac_g1_29dof.onnx").read_bytes(),
            options,
            providers=["CPUExecutionProvider"],
        )
        self.home = np.array(CALIBRATION["home"])
        self.reset()

    def reset(self):
        self.last = np.zeros(29, dtype=np.float32)
        self.phase = np.array([0.0, np.pi])
        self.standing = False

    def act(self, q, dq, omega, quat, elapsed, command):
        terms = {
            "actions": self.last,
            "base_ang_vel": np.asarray(omega) * 0.25,
            "command_ang_vel": [command[2]],
            "command_lin_vel": command[:2],
            "cos_phase": np.cos(self.phase),
            "dof_pos": np.asarray(q) - self.home,
            "dof_vel": np.asarray(dq) * 0.05,
            "projected_gravity": projected_gravity(quat),
            "sin_phase": np.sin(self.phase),
        }
        observation = np.concatenate([terms[name] for name in sorted(terms)]).astype(np.float32)[
            None
        ]
        self.last = self.session.run(None, {"actor_obs": observation})[0].reshape(29).copy()
        self.phase = (self.phase + 2 * np.pi * 0.02 + np.pi) % (2 * np.pi) - np.pi
        if np.linalg.norm(command[:2]) < 0.01 and abs(command[2]) < 0.01:
            self.phase[:] = np.pi
            self.standing = True
        elif self.standing:
            self.phase[:] = [0, np.pi]
            self.standing = False
        return self.home + 0.25 * self.last
