from dataclasses import replace

import mujoco
import numpy as np
import pytest
from embodied_arena.city import VENUES, city_targets, hiding_spots
from embodied_arena.city_actors import DRONES, PEDESTRIANS, drone_pose
from embodied_arena.city_validation import validate_layout
from embodied_arena.config import MatchConfig
from embodied_arena.engine import Arena
from embodied_arena.rules import Referee
from embodied_arena.scene import load_model


@pytest.fixture(scope="module")
def city():
    a = Arena(MatchConfig(), cameras=False)
    yield a
    a.close()


def test_all_venues_and_search_positions_are_reachable_and_visible(city):
    report = validate_layout(city.model, city.data)
    assert all(report["venues"].values()) and report["second_spawn_connected"]
    assert all(report["streets"].values()) and all(report["connectors"].values())
    assert all(report["spawn_clear"])
    assert all(report["entrance_approaches"].values()), report["entrance_approaches"]
    assert report["size_m"] == pytest.approx([61.2, 66.0])
    assert city.model.ngeom < 10000
    assert report["reachable_spots"] == len(hiding_spots()) and report["visible_spots"] == len(
        hiding_spots()
    )


def test_patrol_routes_do_not_pass_through_static_street_furniture(city):
    from embodied_arena.city_validation import pedestrian_routes

    report = pedestrian_routes(city.model, city.data)
    assert all(r["clear"] for r in report.values()), report


def test_city_target_placement_is_seeded_without_privileged_observations(city):
    assert city_targets(7) == city_targets(7)
    assert city_targets(7) != city_targets(8)
    assert {t["zone"] for t in city_targets(7)} == {v["id"] for v in VENUES}
    observation = city.observation(0)
    assert len(observation["tasks"]) == sum(t["owner"] in (None, 0) for t in city_targets(7))
    assert all(
        "position" not in task and "search_position" not in task for task in observation["tasks"]
    )
    assert len(hiding_spots()) == 80 and len(VENUES) == 20
    targets = city_targets(7)
    assert sum(t["owner"] == 0 for t in targets) == sum(t["owner"] == 1 for t in targets) == 6


def test_crossing_drone_routes_remain_separated_and_span_altitude_bands():
    assert len(DRONES) == 7
    assert sum(p["kind"] == "dog" for p in PEDESTRIANS) == 8
    for time in np.linspace(0, 120, 121):
        positions = np.stack([drone_pose(d, time)[0] for d in DRONES])
        distances = np.linalg.norm(positions[:, None] - positions[None, :], axis=2)
        np.fill_diagonal(distances, np.inf)
        assert distances.min() > 1.5
        assert np.ptp(positions[:, 2]) > 10


def test_actors_move_deterministically_and_new_mocap_trajectory_replays(city, tmp_path):
    motion = city.motion
    model = city.model
    initial = city.data.mocap_pos.copy()
    motion.update(city.data, 2.0)
    second = city.data.mocap_pos.copy()
    assert not np.array_equal(initial, second)
    motion.update(city.data, 0.0)
    motion.update(city.data, 2.0)
    assert np.array_equal(second, city.data.mocap_pos)
    city.record()
    city.save(tmp_path)
    model2 = load_model((tmp_path / "scene.xml").read_text(encoding="utf-8"))
    data2 = mujoco.MjData(model2)
    with np.load(tmp_path / "trajectory.npz") as saved:
        data2.qpos[:] = saved["qpos"][-1]
        data2.qvel[:] = saved["qvel"][-1]
        data2.mocap_pos[:] = saved["mocap_pos"][-1]
        data2.mocap_quat[:] = saved["mocap_quat"][-1]
    mujoco.mj_forward(model2, data2)
    mujoco.mj_forward(model, city.data)
    assert np.allclose(data2.xpos, city.data.xpos)
    assert np.allclose(data2.xquat, city.data.xquat)
    motion.update(city.data, 0.0)
    mujoco.mj_forward(model, city.data)


def test_collision_cooldown_and_death_do_not_change_task_score():
    cfg = MatchConfig()
    ref = Referee(cfg, [])
    assert ref.traffic_contact(0, "car", 0, 100, 1.6)
    assert not ref.traffic_contact(0, "car", 1, 100, 1.6)
    assert ref.players[0].health == 85 and ref.players[0].score == 0
    assert ref.traffic_contact(0, "car", 2, 100, 1.6)
    ref.players[0].health = 10
    ref.traffic_contact(0, "car", 4, 100, 1.6)
    assert ref.players[0].health == 0 and ref.players[0].respawn_at == 6
    assert not ref.traffic_contact(0, "car", 5, 100, 1.6)


def test_low_force_and_near_miss_are_not_penalized():
    ref = Referee(MatchConfig(), [])
    assert not ref.traffic_contact(0, "car", 0, 1, 1.6)
    assert ref.players[0].health == 100


@pytest.mark.parametrize(
    "position,vehicle",
    [([-16.4, -1.25, 0.79], "traffic/azure"), ([-13.4, 28.5, 0.79], "traffic/living_taxi")],
)
def test_moving_car_physically_contacts_robot_and_only_penalizes_once(position, vehicle):
    a = Arena(MatchConfig(), cameras=False)
    try:
        r = a.robots[0]
        a.data.qpos[r.root_q : r.root_q + 3] = position
        mujoco.mj_forward(a.model, a.data)
        for _ in range(25):
            a.step([{"joint_targets": r.home, "fire": False} for r in a.robots])
        hits = [e for e in a.referee.events if e["type"] == "traffic_collision"]
        assert len(hits) == 1
        assert hits[0]["vehicle"] == vehicle
        assert hits[0]["player"] == 0 and hits[0]["force"] >= a.config.traffic_min_force
        assert a.referee.players[0].health == 85 and a.referee.players[1].health == 100
        assert np.isfinite(a.data.qpos).all()
    finally:
        a.close()


def test_city_scene_can_disable_traffic():
    a = Arena(replace(MatchConfig(), traffic_enabled=False), cameras=False)
    try:
        assert not a.motion.vehicle_geoms
        assert "drone/01" in a.motion.ids
    finally:
        a.close()
