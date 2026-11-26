import math
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ROOT.parents[1]
SCRIPTS_ROOT = REPOSITORY_ROOT / "dependency/shell/mujoco"
DOCKER_ROOT = REPOSITORY_ROOT / "dependency/docker/mujoco"
FRONTEND_ROOT = REPOSITORY_ROOT / "interface/mujoco"
CAPI_ROOT = REPOSITORY_ROOT / "CAPI/python/mujoco"
DOCS_ROOT = REPOSITORY_ROOT / "docs/mujoco"


@dataclass(frozen=True)
class MatchConfig:
    scene: str = "cyber_city"
    task_set: str = "legacy"
    spawn_swap: bool = False
    render_shadows: bool = True
    duration: float = 60.0
    seed: int = 7
    physics_dt: float = 0.002
    control_dt: float = 0.02
    camera_dt: float = 0.10
    width: int = 160
    height: int = 120
    health: float = 100.0
    hit_damage: float = 20.0
    miss_damage: float = 5.0
    stun_seconds: float = 1.0
    shot_cooldown: float = 0.5
    shot_range: float = 10.0
    respawn_delay: float = 2.0
    fall_timeout: float = 10.0
    upright_hold: float = 0.3
    public_points: float = 10.0
    private_points: float = 10.0
    traffic_enabled: bool = True
    traffic_damage: float = 15.0
    traffic_contact_cooldown: float = 2.0
    traffic_min_force: float = 5.0

    def __post_init__(self):
        if self.scene not in ("room", "cyber_city"):
            raise ValueError("scene must be room or cyber_city")
        if (
            self.task_set not in ("legacy", "mixed-v1")
            or type(self.spawn_swap) is not bool
            or type(self.render_shadows) is not bool
        ):
            raise ValueError("Invalid task set or spawn configuration")
        if not isinstance(self.traffic_enabled, bool):
            raise ValueError("traffic_enabled must be a bool")
        if not isinstance(self.seed, int) or self.seed < 0:
            raise ValueError("seed must be a nonnegative integer")
        for name, value in asdict(self).items():
            if name in ("scene", "traffic_enabled", "task_set", "spawn_swap", "render_shadows"):
                continue
            if not math.isfinite(value) or (name != "seed" and value <= 0):
                raise ValueError(f"Invalid config value {name}={value}")
        if not isinstance(self.width, int) or not isinstance(self.height, int):
            raise ValueError("Camera dimensions must be integers")
        for name in ("control_dt", "camera_dt"):
            ratio = getattr(self, name) / self.physics_dt
            if abs(round(ratio) - ratio) > 1e-7:
                raise ValueError(f"{name} must be an integer multiple of physics_dt")
        if self.camera_dt < self.control_dt:
            raise ValueError("camera_dt must be >= control_dt")

    @classmethod
    def load(cls, path: str | Path | None = None):
        with open(path or ROOT / "configs/default.toml", "rb") as stream:
            return cls(**tomllib.load(stream))
