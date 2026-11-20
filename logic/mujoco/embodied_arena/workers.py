"""Local trusted-code process runner. This is NOT a security sandbox."""

from __future__ import annotations

import importlib
import multiprocessing as mp
import time
import traceback


def load_policy(spec, pid, config):
    module, name = spec.split(":", 1)
    return getattr(importlib.import_module(module), name)(player_id=pid, config=config)


def _worker(connection, spec, pid, config):
    try:
        # Observations contain ndarray values. Import its serializer support
        # before announcing readiness so cold imports do not consume act time.
        importlib.import_module("numpy")
        policy = load_policy(spec, pid, config)
        connection.send(("ready", None))
        while True:
            request = connection.recv()
            if request is None:
                break
            request_id, observation = request
            try:
                connection.send((request_id, policy.act(observation)))
            except Exception:
                connection.send((request_id, {"error": traceback.format_exc(limit=6)}))
    except (EOFError, BrokenPipeError):
        pass
    except Exception:
        try:
            connection.send(("error", traceback.format_exc(limit=6)))
        except (OSError, EOFError):
            pass
    finally:
        connection.close()


class PolicyPool:
    def __init__(self, specs, config, homes, timeout=1.0):
        self.timeout = timeout
        self.connections, self.processes = [], []
        self.pending = [None] * len(specs)
        self.last = [{"joint_targets": q.copy(), "fire": False} for q in homes]
        self.events = []
        self.request_id = 0
        ctx = mp.get_context("spawn")
        try:
            for pid, spec in enumerate(specs):
                parent, child = ctx.Pipe()
                process = ctx.Process(target=_worker, args=(child, spec, pid, config), daemon=True)
                process.start()
                child.close()
                self.connections.append(parent)
                self.processes.append(process)
            deadline = time.monotonic() + 90
            for pid, connection in enumerate(self.connections):
                if not connection.poll(max(0.0, deadline - time.monotonic())):
                    raise TimeoutError(f"Player {pid} initialization timed out")
                status, result = connection.recv()
                if status != "ready":
                    raise RuntimeError(f"Player {pid} initialization failed: {result}")
        except BaseException:
            self.close()
            raise

    def act(self, observations):
        self.request_id += 1
        rid = self.request_id
        deadline = time.monotonic() + self.timeout
        result = [{"joint_targets": action["joint_targets"], "fire": False} for action in self.last]
        for pid, connection in enumerate(self.connections):
            if not self.processes[pid].is_alive():
                self.events.append({"type": "policy_exit", "player": pid})
                continue
            try:
                while connection.poll():
                    connection.recv()  # Discard late replies; never apply to a new tick.
                    self.pending[pid] = None
                if self.pending[pid] is None:
                    connection.send((rid, observations[pid]))
                    self.pending[pid] = rid
            except (BrokenPipeError, EOFError, OSError):
                self.events.append({"type": "policy_exit", "player": pid})
        for pid, connection in enumerate(self.connections):
            if self.pending[pid] != rid:
                continue
            try:
                if not connection.poll(max(0.0, deadline - time.monotonic())):
                    self.events.append({"type": "policy_timeout", "player": pid})
                    continue
                response_id, action = connection.recv()
                self.pending[pid] = None
                if response_id != rid:
                    continue
                if isinstance(action, dict) and "error" not in action and "joint_targets" in action:
                    result[pid] = action
                    self.last[pid] = action
                else:
                    self.events.append(
                        {"type": "policy_error", "player": pid, "message": str(action)[:1500]}
                    )
            except (EOFError, OSError):
                self.events.append({"type": "policy_exit", "player": pid})
        return result

    def close(self):
        for connection in self.connections:
            try:
                connection.send(None)
            except (OSError, EOFError):
                pass
        for process in self.processes:
            process.join(timeout=1)
            if process.is_alive():
                process.terminate()
                process.join(timeout=2)
        for connection in self.connections:
            connection.close()
