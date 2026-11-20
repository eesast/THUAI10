"""Executed ONLY inside the policy image. This file is never used as a host runner."""

from __future__ import annotations

import copy
import importlib
import os
import sys
import traceback

sys.path.insert(0, "/runtime")
from protocol import MAX_MESSAGE, dumps, loads


def main():
    protocol_output = sys.stdout.buffer
    sys.stdout = sys.stderr
    if os.environ.get("ARENA_GPU") == "1":
        import onnxruntime
        import torch

        if not torch.cuda.is_available():
            raise RuntimeError("GPU 环境没有可用 CUDA 设备")
        onnxruntime.preload_dlls()
    os.chdir("/submission")
    sys.path.insert(0, "/submission")
    policy = None
    cached_visual = None
    cached_tasks = None
    while raw := sys.stdin.buffer.readline(MAX_MESSAGE + 1):
        rid = None
        try:
            request = loads(raw)
            rid = request.get("id")
            if request.get("op") == "init":
                policy = importlib.import_module("policy").Policy(
                    player_id=request["player"], config=request["config"]
                )
                response = {"id": rid, "ok": True}
            elif request.get("op") == "act" and policy is not None:
                observation = request["observation"]
                if not request.get("reuse_visual"):
                    cached_visual = observation.get("visual")
                if not request.get("reuse_tasks"):
                    cached_tasks = observation.get("tasks", [])
                observation["visual"] = copy.deepcopy(cached_visual)
                observation["tasks"] = copy.deepcopy(cached_tasks)
                response = {"id": rid, "action": policy.act(request["observation"])}
            else:
                raise ValueError("Invalid command")
            encoded = dumps(response)
        except Exception:
            encoded = dumps({"id": rid, "error": traceback.format_exc(limit=6)[-4000:]})
        protocol_output.write(encoded)
        protocol_output.flush()


if __name__ == "__main__":
    main()
