"""Keep GLFW alive until MuJoCo's passive viewer has finished closing."""

import threading
from contextlib import contextmanager


@contextmanager
def passive_viewer(model, data, **kwargs):
    import mujoco.viewer

    existing = set(threading.enumerate())
    handle = mujoco.viewer.launch_passive(model, data, **kwargs)
    # MuJoCo 3.3.7 launches this daemon thread on Windows/Linux. Handle.close()
    # only requests exit: joining prevents GLFW's atexit callback racing the
    # still-running render loop after a short replay.
    render_threads = [
        t
        for t in threading.enumerate()
        if t not in existing and t.name.endswith("(_launch_internal)")
    ]
    try:
        yield handle
    finally:
        handle.close()
        for thread in render_threads:
            thread.join()
