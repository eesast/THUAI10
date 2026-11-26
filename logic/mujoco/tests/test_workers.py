import time

import numpy as np
from embodied_arena.workers import PolicyPool


def test_exception_does_not_stop_other_policy():
    pool = PolicyPool(
        ["tests.dummy_policies:Failing", "tests.dummy_policies:Echo"],
        {},
        [np.zeros(29), np.zeros(29)],
    )
    try:
        actions = pool.act([{"q": np.ones(29)}, {"q": np.ones(29)}])
        assert np.array_equal(actions[1]["joint_targets"], np.ones(29))
        assert any(e["type"] == "policy_error" and e["player"] == 0 for e in pool.events)
    finally:
        pool.close()


def test_timeout_drops_stale_fire_and_does_not_block_other_policy():
    pool = PolicyPool(
        ["tests.dummy_policies:Slow", "tests.dummy_policies:Echo"],
        {},
        [np.zeros(29), np.zeros(29)],
        timeout=0.05,
    )
    try:
        actions = pool.act([{"q": np.ones(29)}, {"q": np.ones(29)}])
        assert not actions[0]["fire"]
        assert np.array_equal(actions[1]["joint_targets"], np.ones(29))
        assert any(e["type"] == "policy_timeout" for e in pool.events)
        time.sleep(0.23)
        actions = pool.act([{"q": np.ones(29) * 2}, {"q": np.ones(29) * 2}])
        assert not actions[0]["fire"]
        assert np.array_equal(actions[1]["joint_targets"], np.ones(29) * 2)
    finally:
        pool.close()
