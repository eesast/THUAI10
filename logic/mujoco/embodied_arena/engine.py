from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import mujoco
import numpy as np
from PIL import Image, ImageDraw

from .config import ROOT, MatchConfig
from .rules import Hit, Referee, Target
from .scene import COLORS, get_targets, make_world


def reference_image(color: str, shape="cup"):
    if shape != "cup":
        from .objects import reference

        return reference(shape, tuple(int(channel * 255) for channel in COLORS[color][:3]))
    image = Image.new("RGB", (96, 96), (225, 225, 225))
    draw = ImageDraw.Draw(image)
    rgb = tuple(int(channel * 255) for channel in COLORS[color][:3])
    draw.ellipse((58, 34, 83, 65), outline=rgb, width=6)
    draw.rectangle((22, 26, 63, 73), fill=rgb)
    draw.ellipse((22, 20, 63, 35), fill=rgb, outline=(90, 90, 90), width=2)
    return np.asarray(image).copy()


class Arena:
    def __init__(self, config: MatchConfig, cameras: bool = True):
        self.config = config
        self.model, self.data, self.robots, self.xml = make_world(config)
        self.targets = get_targets(config)
        self.referee = Referee(
            config,
            [
                Target(
                    t["id"],
                    t["owner"],
                    config.public_points if t["owner"] is None else config.private_points,
                )
                for t in self.targets
            ],
        )
        self.motion = None
        if config.scene == "cyber_city":
            from .city_actors import CityMotion

            self.motion = CityMotion(self.model)
        self.robot_geom_players = {
            gid: r.pid
            for r in self.robots
            for gid in range(self.model.ngeom)
            if (self.model.geom(gid).name or "").startswith(r.prefix)
        }
        self.cameras = cameras
        self.renderer = self.overview_renderer = None
        self.render_options = mujoco.MjvOption()
        self.render_options.geomgroup[:] = [1, 0, 0, 1, 1, 1]
        self.render_options.sitegroup[:] = 0
        self.images: dict[int, tuple] = {}
        self.references = {
            t["id"]: reference_image(t["color"], t.get("shape", "cup")) for t in self.targets
        }
        self.frame = 0
        self.reset_counts = [0, 0]
        self.last_targets = [r.home.copy() for r in self.robots]
        self.traces = []
        self.shot_traces = []
        self.record()

    @property
    def time(self):
        return self.frame * self.config.control_dt

    def _camera_frame(self, pid):
        cached = self.images.get(pid)
        if cached is None or self.time - cached[0] + 1e-9 >= self.config.camera_dt:
            if self.renderer is None:
                self.renderer = mujoco.Renderer(self.model, self.config.height, self.config.width)
            self.renderer.disable_depth_rendering()
            self.renderer.update_scene(
                self.data, camera=self.robots[pid].camera, scene_option=self.render_options
            )
            self.renderer.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = self.config.render_shadows
            rgb = self.renderer.render().copy()
            self.renderer.enable_depth_rendering()
            depth = self.renderer.render().copy()
            self.renderer.disable_depth_rendering()
            cached = (self.time, rgb, depth)
            self.images[pid] = cached
        return {
            "time": cached[0],
            "rgb": cached[1].copy(),
            "depth": cached[2].copy(),
            "fovy_degrees": float(self.model.cam_fovy[self.robots[pid].camera]),
            "depth_unit": "m",
        }

    def observation(self, pid: int):
        robot, p = self.robots[pid], self.referee.players[pid]
        contacts = [0, 0]
        for contact in self.data.contact:
            for gid in (contact.geom1, contact.geom2):
                body_name = self.model.body(int(self.model.geom_bodyid[gid])).name or ""
                for side, index in (("left", 0), ("right", 1)):
                    if body_name.startswith(robot.prefix + side + "_ankle"):
                        contacts[index] += 1
        tasks = [
            {
                "id": t["id"],
                "kind": "public" if t["owner"] is None else "private",
                "text": t["text"],
                "reference_rgb": self.references[t["id"]].copy(),
            }
            for t in self.targets
            if t["owner"] in (None, pid) and self.referee.targets[t["id"]].active
        ]
        return {
            "schema_version": 1,
            "time": self.time,
            "player": pid,
            "reset_count": self.reset_counts[pid],
            "proprio": {
                "joint_names": robot.names.copy(),
                "q": self.data.qpos[robot.q].copy(),
                "dq": self.data.qvel[robot.v].copy(),
                "base_quat": self.data.qpos[robot.root_q + 3 : robot.root_q + 7].copy(),
                "gyro": self.data.qvel[robot.root_v + 3 : robot.root_v + 6].copy(),
                "foot_contacts": contacts,
            },
            "visual": self._camera_frame(pid) if self.cameras else None,
            "tasks": tasks,
            "game": {
                "health": p.health,
                "score": p.score,
                "alive": p.respawn_at is None,
                "stun_remaining": max(0.0, p.disabled_until - self.time),
                "cooldown_remaining": max(0.0, p.next_shot - self.time),
                "remaining": max(0.0, self.config.duration - self.time),
            },
        }

    def cast_shot(self, pid: int):
        robot = self.robots[pid]
        start = self.data.site_xpos[robot.muzzle].copy()
        axis = self.data.site_xmat[robot.muzzle].reshape(3, 3)[:, 0].copy()
        groups = np.array([1, 1, 1, 0, 0, 1], dtype=np.uint8)
        groups[pid + 1] = 0  # Exclude ALL shooter collision bodies, not only the pelvis.
        geom = np.array([-1], dtype=np.int32)
        distance = mujoco.mj_ray(self.model, self.data, start, axis, groups, 1, -1, geom)
        end = start + axis * (
            distance if 0 <= distance <= self.config.shot_range else self.config.shot_range
        )
        self.shot_traces.append(
            {"time": self.time, "player": pid, "start": start.tolist(), "end": end.tolist()}
        )
        if distance < 0 or distance > self.config.shot_range:
            return Hit("miss")
        name = self.model.geom(int(geom[0])).name or ""
        for other in self.robots:
            if name.startswith(other.prefix):
                return Hit("player", other.pid)
        for target in self.targets:
            if name.startswith(target["id"] + "/"):
                return Hit("target", target["id"])
        return Hit("miss")

    def step(self, actions: list[dict]):
        if len(actions) != len(self.robots):
            raise ValueError("Exactly one action per player is required")
        shots = {}
        for pid, action in enumerate(actions):
            robot = self.robots[pid]
            try:
                q = np.asarray(action["joint_targets"], dtype=float)
                fire = action.get("fire", False)
                if (
                    q.shape != robot.home.shape
                    or not np.isfinite(q).all()
                    or not isinstance(fire, (bool, np.bool_))
                ):
                    raise ValueError("Invalid action shape, numeric value or fire flag")
                self.last_targets[pid] = np.clip(q, robot.limits[:, 0], robot.limits[:, 1])
                if fire and self.referee.can_fire(pid, self.time):
                    shots[pid] = self.cast_shot(pid)
            except (KeyError, ValueError, TypeError) as error:
                self.referee.event(self.time, "invalid_action", player=pid, message=str(error))
            self.data.ctrl[robot.actuators] = self.last_targets[pid]
        self.referee.resolve_shots(self.time, shots)
        traffic_contacts = {}
        for _ in range(round(self.config.control_dt / self.config.physics_dt)):
            if self.motion:
                self.motion.update(self.data, self.data.time)
            mujoco.mj_step(self.model, self.data)
            if self.motion:
                contact_force = np.zeros(6)
                for ci, contact in enumerate(self.data.contact):
                    for vehicle_geom, robot_geom in (
                        (contact.geom1, contact.geom2),
                        (contact.geom2, contact.geom1),
                    ):
                        if (
                            vehicle_geom in self.motion.vehicle_geoms
                            and robot_geom in self.robot_geom_players
                            and contact.dist <= 0.002
                        ):
                            mujoco.mj_contactForce(self.model, self.data, ci, contact_force)
                            key = (
                                self.robot_geom_players[robot_geom],
                                self.motion.vehicle_geoms[vehicle_geom],
                            )
                            traffic_contacts[key] = max(
                                traffic_contacts.get(key, 0.0),
                                float(np.linalg.norm(contact_force[:3])),
                            )
        self.frame += 1
        for (pid, vehicle), force in traffic_contacts.items():
            self.referee.traffic_contact(
                pid, vehicle, self.time, force, self.motion.vehicle_speed(vehicle)
            )
        if not np.isfinite(self.data.qpos).all():
            raise RuntimeError("Non-finite physics state")
        postures = []
        for robot in self.robots:
            height = self.data.qpos[robot.root_q + 2]
            up = self.data.xmat[robot.body].reshape(3, 3)[2, 2]
            postures.append(
                "down"
                if height < 0.45 or up < 0.3
                else "upright"
                if height > 0.6 and up > 0.7
                else "unstable"
            )
        for pid in self.referee.tick(self.time, postures):
            robot = self.robots[pid]
            robot.reset(self.model, self.data)
            self.data.qacc_warmstart[robot.root_v : robot.root_v + 6] = 0
            self.data.qacc_warmstart[robot.v] = 0
            self.last_targets[pid] = robot.home.copy()
            self.reset_counts[pid] += 1
            self.images.pop(pid, None)
        if self.motion:
            self.motion.update(self.data, self.time)
        mujoco.mj_forward(self.model, self.data)
        self.record()
        return self.time + 1e-9 >= self.config.duration

    def record(self):
        self.traces.append(
            (
                self.time,
                self.data.qpos.copy(),
                self.data.qvel.copy(),
                self.data.ctrl.copy(),
                np.array([[p.health, p.score] for p in self.referee.players]),
                self.data.mocap_pos.copy(),
                self.data.mocap_quat.copy(),
            )
        )

    def overview(self, width=720, height=480, camera="overview"):
        if self.overview_renderer is not None and (
            self.overview_renderer.width != width or self.overview_renderer.height != height
        ):
            self.overview_renderer.close()
            self.overview_renderer = None
        if self.overview_renderer is None:
            self.overview_renderer = mujoco.Renderer(self.model, height, width)
        overview_options = mujoco.MjvOption()
        overview_options.geomgroup[:] = [
            1,
            0,
            0,
            1,
            1,
            0 if camera in ("overview", "aerial") else 1,
        ]
        overview_options.sitegroup[:] = 0
        self.overview_renderer.update_scene(self.data, camera=camera, scene_option=overview_options)
        return self.overview_renderer.render().copy()

    def save(self, path: str | Path):
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        time, qpos, qvel, ctrl, health_score, mocap_pos, mocap_quat = map(
            np.stack, zip(*self.traces, strict=True)
        )
        np.savez_compressed(
            path / "trajectory.npz",
            time=time,
            qpos=qpos,
            qvel=qvel,
            ctrl=ctrl,
            health_score=health_score,
            mocap_pos=mocap_pos,
            mocap_quat=mocap_quat,
        )
        (path / "scene.xml").write_text(self.xml, encoding="utf-8")
        (path / "config.json").write_text(
            json.dumps(asdict(self.config), indent=2), encoding="utf-8"
        )
        with (path / "events.jsonl").open("w", encoding="utf-8") as stream:
            for event in self.referee.events:
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        (path / "shots.json").write_text(json.dumps(self.shot_traces), encoding="utf-8")
        scores = [p.score for p in self.referee.players]
        winners = [i for i, score in enumerate(scores) if score == max(scores)]
        result = {
            "scene": self.config.scene,
            "seed": self.config.seed,
            "simulated_seconds": self.time,
            "scores": scores,
            "winners": winners,
            "tie": len(winners) > 1,
            "health": [p.health for p in self.referee.players],
            "events": dict(Counter(e["type"] for e in self.referee.events)),
            "trajectory_sha256": hashlib.sha256(
                qpos.tobytes() + mocap_pos.tobytes() + mocap_quat.tobytes()
            ).hexdigest(),
        }
        (path / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        versions = {"python": platform.python_version()}
        for name in ("mujoco", "numpy", "Pillow", "onnxruntime", "torch"):
            try:
                versions[name] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                pass
        manifest = ROOT / "third_party/manifest.json"
        source_hash = hashlib.sha256()
        for source in sorted((ROOT / "embodied_arena").glob("*.py")):
            source_hash.update(source.name.encode())
            source_hash.update(source.read_bytes())
        (path / "environment.json").write_text(
            json.dumps(
                {
                    "versions": versions,
                    "system": platform.platform(),
                    "source_sha256": source_hash.hexdigest(),
                    "actuators": json.loads(
                        (ROOT / "configs/g1_actuators.json").read_text(encoding="utf-8")
                    ),
                    "assets_manifest": json.loads(manifest.read_text(encoding="utf-8")),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return result

    def close(self):
        for renderer in (self.renderer, self.overview_renderer):
            if renderer is not None:
                renderer.close()
