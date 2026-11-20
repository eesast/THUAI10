"""Bounded JSON/typed-array protocol. No pickle, object dtype, eval or code loading."""

from __future__ import annotations

import base64
import json
import math

import numpy as np

MAX_MESSAGE = 8 * 1024**2
DTYPES = {"uint8", "int32", "int64", "float32", "float64", "bool"}


def encode(value, depth=0):
    if depth > 24:
        raise ValueError("Message nesting too deep")
    if isinstance(value, np.ndarray):
        array = np.ascontiguousarray(value)
        if array.dtype.name not in DTYPES or array.nbytes > MAX_MESSAGE // 2:
            raise ValueError("Unsupported array dtype or size")
        return {
            "__array__": 1,
            "dtype": array.dtype.name,
            "shape": list(array.shape),
            "data": base64.b64encode(array.tobytes()).decode("ascii"),
        }
    if isinstance(value, np.generic):
        return encode(value.item(), depth + 1)
    if isinstance(value, dict):
        if len(value) > 256 or any(not isinstance(k, str) or len(k) > 256 for k in value):
            raise ValueError("Invalid object keys")
        return {k: encode(v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        if len(value) > 4096:
            raise ValueError("List too long")
        return [encode(v, depth + 1) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, str) and len(value) > MAX_MESSAGE // 2:
            raise ValueError("String too long")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Nonfinite number")
        if isinstance(value, int) and value.bit_length() > 64:
            raise ValueError("Integer too large")
        return value
    raise ValueError("Unsupported value type")


def decode(value, depth=0):
    if depth > 24:
        raise ValueError("Message nesting too deep")
    if isinstance(value, dict) and "__array__" in value:
        if set(value) != {"__array__", "dtype", "shape", "data"} or value["dtype"] not in DTYPES:
            raise ValueError("Invalid array descriptor")
        shape = value["shape"]
        if (
            not isinstance(shape, list)
            or len(shape) > 4
            or any(type(x) is not int or x < 0 or x > MAX_MESSAGE for x in shape)
        ):
            raise ValueError("Invalid array shape")
        dtype = np.dtype(value["dtype"])
        size = math.prod(shape) * dtype.itemsize
        if size > MAX_MESSAGE // 2 or not isinstance(value["data"], str):
            raise ValueError("Array too large")
        raw = base64.b64decode(value["data"], validate=True)
        if len(raw) != size:
            raise ValueError("Array byte count mismatch")
        return np.frombuffer(raw, dtype=dtype).reshape(shape).copy()
    if isinstance(value, dict):
        if len(value) > 256 or any(len(k) > 256 for k in value):
            raise ValueError("Object too large")
        return {k: decode(v, depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        if len(value) > 4096:
            raise ValueError("List too long")
        return [decode(v, depth + 1) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Nonfinite number")
    return value


def dumps(value):
    raw = (
        json.dumps(
            encode(value), separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
        + b"\n"
    )
    if len(raw) > MAX_MESSAGE:
        raise ValueError("Message too large")
    return raw


def loads(raw):
    if len(raw) > MAX_MESSAGE:
        raise ValueError("Message too large")
    return decode(json.loads(raw))


def validate_action(action):
    if not isinstance(action, dict) or set(action) != {"joint_targets", "fire"}:
        raise ValueError("返回对象必须包含 joint_targets 和 fire，且不能包含其他字段")
    q = np.asarray(action["joint_targets"])
    if q.shape != (29,):
        raise ValueError(f"joint_targets 要求 29 个关节，实际形状为 {q.shape}")
    if q.dtype.kind not in "fiu" or not np.isfinite(q).all():
        raise ValueError("joint_targets 必须是 29 个有限实数，不接受 NaN 或无穷值")
    if type(action["fire"]) is not bool:
        raise ValueError("fire 必须是布尔值 True 或 False")
    return {"joint_targets": q.astype(np.float64), "fire": action["fire"]}
