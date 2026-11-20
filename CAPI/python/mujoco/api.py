"""Public API v1 types for the optional G1 MuJoCo competition backend."""

from typing import Literal, TypedDict

import numpy as np
from numpy.typing import NDArray


class Proprioception(TypedDict):
    joint_names: list[str]
    q: NDArray[np.float64]
    dq: NDArray[np.float64]
    base_quat: NDArray[np.float64]
    gyro: NDArray[np.float64]
    foot_contacts: list[int]


class VisualObservation(TypedDict):
    time: float
    rgb: NDArray[np.uint8]
    depth: NDArray[np.float32]
    fovy_degrees: float
    depth_unit: str


class TaskObservation(TypedDict):
    id: str
    kind: Literal["public", "private"]
    text: str
    reference_rgb: NDArray[np.uint8]


class GameState(TypedDict):
    health: float
    score: float
    alive: bool
    stun_remaining: float
    cooldown_remaining: float
    remaining: float


class Observation(TypedDict):
    schema_version: int
    time: float
    player: int
    reset_count: int
    proprio: Proprioception
    visual: VisualObservation | None
    tasks: list[TaskObservation]
    game: GameState


class Action(TypedDict):
    joint_targets: NDArray[np.float64] | list[float]
    fire: bool
