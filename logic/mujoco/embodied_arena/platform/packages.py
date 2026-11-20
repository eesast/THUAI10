from __future__ import annotations

import ast
import hashlib
import io
import json
import re
import shutil
import stat
import zipfile
from pathlib import PurePosixPath

from embodied_arena.config import CAPI_ROOT, DOCS_ROOT

from .robot_contract import descriptor, validate_manifest


class PackageError(ValueError):
    pass


def discard_staging(directory, parent):
    resolved = directory.resolve()
    if resolved.parent != parent.resolve() or not re.fullmatch(r"[0-9a-f]{32}", resolved.name):
        raise ValueError("Refusing to remove a non-staging directory")
    if resolved.is_dir():
        shutil.rmtree(resolved)


def inspect_package(archive, destination, settings):
    """Bounded static inspection. Never import, eval, compile or execute a submission."""
    reports = []
    try:
        with zipfile.ZipFile(archive) as z:
            entries = z.infolist()
            if len(entries) > settings.max_files:
                raise PackageError(f"文件数量超过 {settings.max_files} 个。")
            paths, names, total = [], set(), 0
            for item in entries:
                raw = item.filename
                pieces = raw.rstrip("/").split("/")
                if (
                    not raw
                    or item.orig_filename != raw
                    or "\\" in raw
                    or raw.startswith("/")
                    or any(p in ("", ".", "..") for p in pieces)
                    or any(
                        ":" in p
                        or p.endswith((" ", "."))
                        or re.match(r"(?i)^(con|prn|aux|nul|com[0-9]|lpt[0-9])(?:\.|$)", p)
                        for p in pieces
                    )
                    or any(ord(c) < 32 for c in raw)
                    or len(raw) > 240
                ):
                    raise PackageError("压缩包包含不允许的路径，请只使用普通相对文件路径。")
                mode = item.external_attr >> 16
                if stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR) or item.flag_bits & 1:
                    raise PackageError("不接受链接、特殊文件或加密 ZIP。")
                folded = raw.rstrip("/").casefold()
                if folded in names:
                    raise PackageError("压缩包有重复或大小写冲突的路径。")
                names.add(folded)
                total += item.file_size
                if (
                    total > settings.expanded_bytes
                    or item.file_size / max(1, item.compress_size) > 250
                ):
                    raise PackageError(
                        "解压大小或压缩率超过上限，请移除缓存、虚拟环境或异常压缩文件。"
                    )
                if not item.is_dir():
                    paths.append((item, PurePosixPath(raw)))
            if not paths:
                raise PackageError("ZIP 内没有文件。")
            prefix = ()
            if not any(str(p) == "submission.json" for _, p in paths):
                first = {p.parts[0] for _, p in paths}
                if len(first) == 1 and all(len(p.parts) > 1 for _, p in paths):
                    prefix = (next(iter(first)),)
            normalized = [(item, PurePosixPath(*p.parts[len(prefix) :])) for item, p in paths]
            mapping = {str(p): item for item, p in normalized}
            if "submission.json" not in mapping or "policy.py" not in mapping:
                raise PackageError(
                    "提交根目录需要 submission.json 和 policy.py；允许额外包一层目录。"
                )
            if (
                mapping["submission.json"].file_size > 65536
                or mapping["policy.py"].file_size > 262144
            ):
                raise PackageError("submission.json 或 policy.py 过大；模型请放在 models/。")
            try:
                manifest = json.loads(z.read(mapping["submission.json"]).decode("utf-8-sig"))
            except (UnicodeError, json.JSONDecodeError) as e:
                raise PackageError(f"submission.json 不是有效的 UTF-8 JSON：{e}") from e
            if not isinstance(manifest, dict):
                raise PackageError("submission.json 顶层必须是对象。")
            if type(manifest.get("api_version")) is not int or manifest["api_version"] != 1:
                raise PackageError("api_version 必须是整数 1。")
            if manifest.get("entry_point") != "policy:Policy":
                raise PackageError(
                    "entry_point 必须为 policy:Policy；请在 policy.py 中定义 Policy。"
                )
            if manifest.get("environment") not in set(settings.available_environments) | {
                settings.environment
            }:
                raise PackageError(f"当前可用环境为 {settings.environment}，请修改 environment。")
            if (
                not isinstance(manifest.get("name"), str)
                or not 1 <= len(manifest["name"].strip()) <= 60
            ):
                raise PackageError("清单 name 需要 1–60 个字符。")
            try:
                declared_order = validate_manifest(manifest)
            except ValueError as error:
                raise PackageError(str(error)) from error
            manifest["_expanded_bytes"] = total
            try:
                ast.parse(z.read(mapping["policy.py"]).decode("utf-8-sig"), filename="policy.py")
            except (SyntaxError, UnicodeError, ValueError, RecursionError) as e:
                raise PackageError(f"policy.py 语法检查失败：{e}") from e
            reports = [
                {
                    "name": "ZIP 路径与大小",
                    "state": "passed",
                    "detail": f"{len(paths)} 个文件，解压后 {total / 1024**2:.2f} MB",
                },
                {"name": "清单与入口", "state": "passed", "detail": "policy:Policy / API v1"},
                {
                    "name": "机器人与关节适配",
                    "state": "passed",
                    "detail": "Unitree G1 / 29 关节 / 弧度 / 位置控制；"
                    + (
                        "按声明的关节名称自动重排"
                        if declared_order
                        else "输出遵循观测 joint_names 顺序"
                    ),
                },
                {
                    "name": "Python 语法",
                    "state": "passed",
                    "detail": "只检查语法，未导入或执行代码",
                },
                {
                    "name": "编译与隔离运行接口",
                    "state": "waiting",
                    "detail": "等待包内全部 Python 文件编译、策略导入和 29 关节动作检查",
                },
            ]
            destination.mkdir(parents=True, exist_ok=False)
            for item, relative in normalized:
                target = destination.joinpath(*relative.parts)
                if not target.resolve().is_relative_to(destination.resolve()):
                    raise PackageError("路径越界。")
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(item) as source, target.open("xb") as output:
                    copied = 0
                    while chunk := source.read(1024 * 1024):
                        copied += len(chunk)
                        if copied > item.file_size:
                            raise PackageError("文件实际大小与 ZIP 声明不一致。")
                        output.write(chunk)
                target.chmod(0o644)
            return manifest, reports
    except (zipfile.BadZipFile, RuntimeError, OSError, NotImplementedError) as e:
        raise PackageError(f"ZIP 无法读取：{e}") from e


def template_zip(environment):
    buffer = io.BytesIO()
    manifest = {
        "name": "我的城市搜索策略",
        "api_version": 1,
        "entry_point": "policy:Policy",
        "environment": environment,
        "robot_id": "unitree_g1_29dof",
        "control_mode": "joint_position",
        "joint_unit": "rad",
        "description": "仅展示接口，请自行实现视觉和运动控制",
    }
    policy = '''"""接口示例：不构成稳定站立、行走或搜索策略。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent

class Policy:
    def __init__(self, player_id=0, config=None):
        self.player_id = player_id
        self.config = config or {}
        self.reset_count = None
        # 权重路径示例：ROOT / "models" / "model.onnx"

    def act(self, observation):
        if self.reset_count != observation["reset_count"]:
            self.reset_count = observation["reset_count"]
            # 在这里重置运控历史；慢视觉应缓存识别结果。
        return {"joint_targets": observation["proprio"]["q"].copy(), "fire": False}
'''
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("submission.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        z.writestr("policy.py", policy)
        z.writestr("models/.keep", "")
        z.writestr("src/__init__.py", "")
        z.writestr("api.py", (CAPI_ROOT / "api.py").read_bytes())
        z.writestr("robot.json", json.dumps(descriptor(), ensure_ascii=False, indent=2))
        guide = DOCS_ROOT / "SUBMISSION_GUIDE.md"
        z.writestr(
            "README.md",
            guide.read_text(encoding="utf-8")
            if guide.exists()
            else "# 参赛模板\n参见平台「接口与环境」。输出必须是 29 关节位置目标，单位 rad。模板不构成行走控制器。\n",
        )
    return buffer.getvalue()


def file_digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()
