"""Package a pinned, licensed walking checkpoint without importing participant code."""

import io
import json
import zipfile

from embodied_arena.config import CAPI_ROOT, ROOT

from .packages import template_zip


def walking_zip(environment):
    checkpoint = ROOT / "third_party/holosoma/fastsac_g1_29dof.onnx"
    if not checkpoint.exists():
        raise FileNotFoundError("请先一键部署，下载并校验公开的行走权重")
    buffer = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(template_zip(environment))) as original,
        zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as output,
    ):
        manifest = json.loads(original.read("submission.json"))
        manifest.update(
            name="G1 入门行走与深度避障",
            description="Holosoma 29DoF 行走示例；不含完整搜索、瞄准或自主起身",
        )
        for name in original.namelist():
            if name not in ("submission.json", "policy.py"):
                output.writestr(name, original.read(name))
        output.writestr("submission.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        output.writestr("policy.py", (CAPI_ROOT / "policy.py").read_text(encoding="utf-8"))
        output.writestr(
            "starter.json", json.dumps({"speed": 0.15, "avoid_obstacles": True}, indent=2)
        )
        output.writestr("models/walk.onnx", checkpoint.read_bytes())
        output.writestr(
            "LICENSES/Holosoma-Apache-2.0.txt", (ROOT / "third_party/holosoma/LICENSE").read_bytes()
        )
        output.writestr(
            "START_HERE.md",
            "# 入门行走包\n\n原样上传即可练习。前 2 秒站立，此后以 starter.json 的 speed 行走；设为 0 可测试站立。深度避障只是近距离转向示范，不保证避车或城市导航。未实现开火、物品识别和自主起身。修改策略与视觉模块后上传新版本。权重来自 assets.lock.json 固定的 Amazon FAR Holosoma，遵循随包 Apache-2.0 许可。\n",
        )
    return buffer.getvalue()
