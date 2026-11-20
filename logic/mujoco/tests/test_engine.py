from dataclasses import replace

import mujoco
import numpy as np
import pytest
from embodied_arena.config import MatchConfig
from embodied_arena.engine import Arena


@pytest.fixture(scope="module")
def arena():
    a = Arena(MatchConfig(scene="room"), cameras=False)
    yield a
    a.close()


def test_g1_joint_contract_and_no_privileged_observations(arena):
    observation = arena.observation(0)
    assert len(observation["proprio"]["q"]) == 29
    assert len(observation["proprio"]["joint_names"]) == 29
    assert "position" not in observation["proprio"]
    assert "model" not in observation and "qpos" not in observation
    assert {t["id"] for t in observation["tasks"]} == {"red_cup", "blue_cup"}


def test_ray_hits_target_and_occluder_first(arena):
    a = arena
    robot = a.robots[0]
    start = a.data.site_xpos[robot.muzzle].copy()
    axis = a.data.site_xmat[robot.muzzle].reshape(3, 3)[:, 0].copy()
    body = a.model.body("red_cup").id
    original = a.model.body_pos[body].copy()
    cabinet = a.model.geom("cabinet").id
    original_cabinet = a.model.geom_pos[cabinet].copy()
    original_size = a.model.geom_size[cabinet].copy()
    try:
        a.model.body_pos[body] = start + axis * 0.38
        mujoco.mj_forward(a.model, a.data)
        hit = a.cast_shot(0)
        assert hit.kind == "target" and hit.id == "red_cup"
        a.model.geom_pos[cabinet] = start + axis * 0.12
        a.model.geom_size[cabinet] = [0.035, 0.035, 0.035]
        mujoco.mj_forward(a.model, a.data)
        assert a.cast_shot(0).kind == "miss"
    finally:
        a.model.body_pos[body] = original
        a.model.geom_pos[cabinet] = original_cabinet
        a.model.geom_size[cabinet] = original_size
        mujoco.mj_forward(a.model, a.data)


def test_stun_keeps_joint_commands_enabled(arena):
    a = arena
    a.referee.players[0].disabled_until = a.time + 5
    target = a.robots[0].home.copy()
    target[-1] = 0.15
    a.step(
        [
            {"joint_targets": target, "fire": True},
            {"joint_targets": a.robots[1].home, "fire": False},
        ]
    )
    assert a.data.ctrl[a.robots[0].actuators[-1]] == pytest.approx(0.15)
    assert a.referee.players[0].health == 100


def test_ray_can_hit_opponent_and_apply_damage():
    a = Arena(MatchConfig(scene="room"), cameras=False)
    try:
        shooter, other = a.robots
        wrist = shooter.names.index("right_wrist_pitch_joint")
        a.data.qpos[shooter.q[wrist]] = -0.8
        mujoco.mj_forward(a.model, a.data)
        start = a.data.site_xpos[shooter.muzzle]
        axis = a.data.site_xmat[shooter.muzzle].reshape(3, 3)[:, 0]
        point = start + axis * 1.8
        a.data.qpos[other.root_q : other.root_q + 3] = point + [0, 0, 0.076]
        mujoco.mj_forward(a.model, a.data)
        hit = a.cast_shot(0)
        assert hit.kind == "player" and hit.id == 1
        a.referee.resolve_shots(0, {0: hit})
        assert a.referee.players[1].health == 80
        assert a.referee.players[1].disabled_until == 1
        assert a.referee.players[0].score == 0
    finally:
        a.close()


def test_invalid_action_is_rejected_and_state_stays_finite(arena):
    bad = arena.robots[0].home.copy()
    bad[0] = np.nan
    arena.step(
        [
            {"joint_targets": bad, "fire": False},
            {"joint_targets": arena.robots[1].home, "fire": False},
        ]
    )
    assert np.isfinite(arena.data.qpos).all()
    assert any(e["type"] == "invalid_action" for e in arena.referee.events)


def test_fall_reset_physically_preserves_other_player_and_health():
    config = replace(MatchConfig(scene="room"), fall_timeout=0.04)
    a = Arena(config, cameras=False)
    try:
        r = a.robots[0]
        a.data.qpos[r.root_q + 2] = 0.3
        a.referee.players[0].health = 35
        mujoco.mj_forward(a.model, a.data)
        for _ in range(3):
            a.step([{"joint_targets": x.home, "fire": False} for x in a.robots])
        assert a.reset_counts == [1, 0]
        assert a.referee.players[0].health == 35
        assert a.data.qpos[r.root_q + 2] > 0.7
        assert a.referee.targets["red_cup"].active
    finally:
        a.close()


def test_rgb_depth_units_and_camera_cadence():
    a = Arena(MatchConfig(scene="room"), cameras=True)
    try:
        visual = a.observation(0)["visual"]
        assert visual["rgb"].shape == (120, 160, 3)
        assert visual["depth"].shape == (120, 160)
        assert np.isfinite(visual["depth"]).all() and visual["depth"].min() > 0
        a.step([{"joint_targets": r.home, "fire": False} for r in a.robots])
        assert a.observation(0)["visual"]["time"] == visual["time"]
    finally:
        a.close()
