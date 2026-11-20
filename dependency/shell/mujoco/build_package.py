"""Build a clean source player package compatible with installer catalog.json.

Only declared source paths enter the package. User submissions, databases,
virtual environments, generated tests and downloaded assets are excluded by
default. Optional assets must match assets.lock.json before redistribution.
"""

import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path
from urllib.parse import quote

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CORE_ROOT = REPOSITORY_ROOT / "logic/mujoco"


def package_sources(repository):
    repository = Path(repository).resolve()
    patterns = [
        "logic/mujoco/embodied_arena/**/*.py",
        "logic/mujoco/configs/*.toml",
        "logic/mujoco/configs/*.json",
        "logic/mujoco/assets/cyber_city/*.png",
        "logic/mujoco/assets/cyber_city/*.json",
        "interface/mujoco/*.js",
        "interface/mujoco/*.css",
        "interface/mujoco/*.html",
        "interface/mujoco/*.png",
        "interface/mujoco/*.svg",
        "CAPI/python/mujoco/*.py",
        "CAPI/python/mujoco/README.md",
        "dependency/shell/mujoco/*.py",
        "dependency/shell/mujoco/*.ps1",
        "dependency/shell/mujoco/*.cmd",
        "dependency/python/mujoco/requirements-lock.txt",
        "dependency/docker/mujoco/Dockerfile",
        "dependency/docker/mujoco/Dockerfile.torch",
        "dependency/docker/mujoco/Dockerfile.cuda",
        "docs/mujoco/*.md",
        "playback/mujoco/*.py",
        "playback/mujoco/README.md",
        "installer/mujoco/README.md",
        "logic/mujoco/README.md",
        "logic/mujoco/pyproject.toml",
        "logic/mujoco/.dockerignore",
        "logic/mujoco/assets.lock.json",
        "logic/mujoco/THIRD_PARTY.md",
        "LICENSE",
    ]
    sources = {path for pattern in patterns for path in repository.glob(pattern) if path.is_file()}
    for path in sources:
        if path.is_symlink() or not path.resolve().is_relative_to(repository):
            raise ValueError("Package sources must be regular files inside the repository")
    return sorted(sources)


def build_package(
    output, version="0.4.0-prototype", include_assets=False, repository=REPOSITORY_ROOT
):
    repository = Path(repository).resolve()
    output = Path(output).resolve()
    sources = package_sources(repository)
    if not version.strip() or not sources:
        raise ValueError("A version and package sources are required")
    if include_assets:
        lock = json.loads(
            (repository / "logic/mujoco/assets.lock.json").read_text(encoding="utf-8")
        )
        for item in lock["files"]:
            path = repository / "logic/mujoco" / item["path"]
            if not path.resolve().is_relative_to(repository / "logic/mujoco/third_party"):
                raise ValueError("Asset path escapes third_party")
            if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
                raise ValueError("Asset SHA-256 does not match the lock file")
            sources.append(path)
    # A fresh destination avoids overwriting an earlier release or local data.
    output.mkdir(parents=True, exist_ok=False)
    payload = output / "payload"
    payload.mkdir()
    for source in sources:
        destination = payload / source.relative_to(repository)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    shutil.copyfile(
        repository / "installer/mujoco/thuai10-launch.json", payload / "thuai10-launch.json"
    )
    (payload / "docs/README.md").write_text(
        "# THUAI10 MuJoCo 原型\n\n"
        "安装与启动见 [接入说明](mujoco/INTEGRATION.md)，"
        "选手接口见 [提交指南](mujoco/SUBMISSION_GUIDE.md)。\n",
        encoding="utf-8",
    )
    files = []
    for path in sorted(payload.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(payload).as_posix()
        files.append(
            {
                "path": relative,
                "url": "payload/" + quote(relative, safe="/"),
                "size": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    catalog = {"version": version, "files": files}
    (output / "catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=4) + "\n", encoding="utf-8"
    )
    with zipfile.ZipFile(
        output / "thuai10-mujoco-source.zip", "w", zipfile.ZIP_DEFLATED
    ) as archive:
        for item in files:
            archive.write(payload / item["path"], item["path"])
    return catalog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--version", default="0.4.0-prototype")
    parser.add_argument("--include-assets", action="store_true")
    args = parser.parse_args()
    catalog = build_package(args.output, args.version, args.include_assets)
    print(json.dumps({"version": catalog["version"], "files": len(catalog["files"])}))


if __name__ == "__main__":
    main()
