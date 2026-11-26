import threading

import mujoco.viewer
from embodied_arena.viewer import passive_viewer


def test_viewer_waits_for_render_cleanup_before_returning(monkeypatch):
    requested = threading.Event()
    allow_cleanup = threading.Event()
    cleanup_done = threading.Event()
    returned = threading.Event()

    def launch(*args, **kwargs):
        def render():
            requested.wait()
            allow_cleanup.wait()
            cleanup_done.set()

        threading.Thread(target=render, name="Test (_launch_internal)", daemon=True).start()

        class Handle:
            def close(self):
                requested.set()

        return Handle()

    monkeypatch.setattr(mujoco.viewer, "launch_passive", launch)

    def use_window():
        with passive_viewer(None, None):
            pass
        returned.set()

    client = threading.Thread(target=use_window)
    client.start()
    try:
        assert requested.wait(2)
        assert not returned.wait(0.03)
    finally:
        allow_cleanup.set()
        client.join(2)
    assert cleanup_done.is_set() and returned.is_set() and not client.is_alive()
