from dataclasses import replace

import pytest
from embodied_arena.config import MatchConfig
from embodied_arena.rules import Hit, Referee, Target


def game(**kwargs):
    cfg = replace(MatchConfig(), **kwargs)
    return Referee(cfg, [Target("shared", None, 10), Target("private", 0, 10)])


def test_wrong_private_wall_and_repeated_target_cost_health():
    r = game()
    r.resolve_shots(0, {1: Hit("target", "private")})
    r.resolve_shots(1, {1: Hit("miss")})
    assert r.players[1].health == 90
    r.resolve_shots(2, {0: Hit("target", "shared")})
    r.resolve_shots(3, {0: Hit("target", "shared")})
    assert r.players[0].health == 95
    assert r.players[0].score == 10


def test_mutual_shots_are_simultaneous_even_if_lethal():
    r = game(hit_damage=100)
    r.resolve_shots(0, {0: Hit("player", 1), 1: Hit("player", 0)})
    assert [p.health for p in r.players] == [0, 0]
    assert [p.score for p in r.players] == [0, 0]
    assert r.tick(1, ["down", "down"]) == []
    assert r.tick(2, ["down", "down"]) == [0, 1]
    assert [p.health for p in r.players] == [100, 100]


def test_shared_target_simultaneous_hits_split_score():
    r = game()
    r.resolve_shots(0, {0: Hit("target", "shared"), 1: Hit("target", "shared")})
    assert [p.score for p in r.players] == [5, 5]


def test_stun_blocks_shooting_but_does_not_create_miss_penalty():
    r = game()
    r.resolve_shots(0, {0: Hit("player", 1)})
    r.resolve_shots(0.5, {1: Hit("miss")})
    assert r.players[1].health == 80
    r.resolve_shots(1, {1: Hit("miss")})
    assert r.players[1].health == 75


def test_cooldown_rejected_requests_are_not_shots():
    r = game()
    r.resolve_shots(0, {0: Hit("miss")})
    r.resolve_shots(0.1, {0: Hit("miss")})
    assert r.players[0].health == 95


def test_fall_reset_preserves_health_score_and_tasks():
    r = game()
    r.players[0].health = 35
    r.players[0].score = 20
    assert r.tick(0, ["down", "upright"]) == []
    assert r.tick(9.99, ["down", "upright"]) == []
    assert r.tick(10, ["down", "upright"]) == [0]
    assert r.players[0].health == 35 and r.players[0].score == 20
    assert r.targets["shared"].active


def test_brief_upright_pose_does_not_clear_fall_timer():
    r = game()
    r.tick(0, ["down", "upright"])
    r.tick(9.8, ["upright", "upright"])
    assert r.tick(10, ["down", "upright"]) == [0]


def test_sustained_self_recovery_clears_timer():
    r = game()
    r.tick(0, ["down", "upright"])
    r.tick(5, ["upright", "upright"])
    r.tick(5.3, ["upright", "upright"])
    assert r.tick(10, ["upright", "upright"]) == []
    assert any(e["type"] == "self_recovery" for e in r.events)


def test_death_has_priority_over_fall_reset():
    r = game(miss_damage=100, respawn_delay=12)
    r.tick(0, ["down", "upright"])
    r.resolve_shots(5, {0: Hit("miss")})
    assert r.tick(10, ["down", "upright"]) == []
    assert r.tick(17, ["down", "upright"]) == [0]


@pytest.mark.parametrize(
    "kwargs", [{"physics_dt": 0}, {"control_dt": 0.021}, {"health": float("nan")}, {"width": 160.5}]
)
def test_invalid_config_rejected(kwargs):
    with pytest.raises(ValueError):
        replace(MatchConfig(), **kwargs)
