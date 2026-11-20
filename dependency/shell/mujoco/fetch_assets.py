"""Fetch pinned, openly licensed G1 assets and Unitree's walking checkpoint."""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import time
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "logic/mujoco"
SOURCES = {
    "menagerie": ("google-deepmind/mujoco_menagerie", "370c43965323c0944b433b202aac5058b5f907a9"),
    "unitree_rl_gym": (
        "unitreerobotics/unitree_rl_gym",
        "276801e46c5d433564f24658bac64f254b7d2d4b",
    ),
    "holosoma": ("amazon-far/holosoma", "78aeb23ed478de980c43e979f5e70be1b9699187"),
    "orbitron": ("google/fonts", "8b0a1d0f5983c89bc2b93f1b5fb55f9e252744b5"),
}


def fetch(source: str, remote: str, local: str) -> dict:
    repo, revision = SOURCES[source]
    url = f"https://raw.githubusercontent.com/{repo}/{revision}/{remote}"
    destination = ROOT / "third_party" / local
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        for attempt in range(4):
            try:
                request = urllib.request.Request(
                    url, headers={"User-Agent": "embodied-arena-prototype"}
                )
                with urllib.request.urlopen(request, timeout=60) as response:
                    data = response.read()
                temporary = destination.with_suffix(destination.suffix + ".part")
                temporary.write_bytes(data)
                temporary.replace(destination)
                break
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(attempt + 1)
    data = destination.read_bytes()
    if data.startswith(b"version https://git-lfs"):
        raise RuntimeError(f"Unresolved Git LFS pointer: {destination}")
    digest = hashlib.sha256(data).hexdigest()
    lock_path = ROOT / "assets.lock.json"
    relative = str(destination.relative_to(ROOT)).replace("\\", "/")
    if lock_path.exists():
        locked = {
            item["path"]: item["sha256"]
            for item in json.loads(lock_path.read_text(encoding="utf-8"))["files"]
        }
        if relative in locked and digest != locked[relative]:
            raise RuntimeError(
                f"Asset checksum mismatch: {relative}. Restore this file from the pinned source."
            )
    return {
        "source": source,
        "revision": revision,
        "url": url,
        "path": str(destination.relative_to(ROOT)).replace("\\", "/"),
        "sha256": digest,
        "bytes": len(data),
    }


def main() -> None:
    records = [fetch("menagerie", "unitree_g1/g1.xml", "g1/g1.xml")]
    xml = ET.parse(ROOT / "third_party/g1/g1.xml")
    meshes = sorted({node.attrib["file"] for node in xml.iter("mesh")})
    jobs = [("menagerie", f"unitree_g1/assets/{name}", f"g1/assets/{name}") for name in meshes]
    jobs.extend(
        [
            ("menagerie", "unitree_g1/LICENSE", "g1/LICENSE"),
            ("menagerie", "unitree_g1/README.md", "g1/UPSTREAM_README.md"),
            ("unitree_rl_gym", "LICENSE", "unitree_rl_gym/LICENSE"),
            ("unitree_rl_gym", "deploy/pre_train/g1/motion.pt", "unitree_rl_gym/motion.pt"),
            ("unitree_rl_gym", "deploy/deploy_mujoco/configs/g1.yaml", "unitree_rl_gym/g1.yaml"),
            (
                "unitree_rl_gym",
                "deploy/deploy_mujoco/deploy_mujoco.py",
                "unitree_rl_gym/UPSTREAM_deploy.py",
            ),
            ("holosoma", "LICENSE", "holosoma/LICENSE"),
            (
                "holosoma",
                "src/holosoma_inference/holosoma_inference/models/loco/g1_29dof/fastsac_g1_29dof.onnx",
                "holosoma/fastsac_g1_29dof.onnx",
            ),
            (
                "holosoma",
                "src/holosoma_inference/holosoma_cpp/config/inference/g1-29dof-loco.yaml",
                "holosoma/deploy.yaml",
            ),
            (
                "holosoma",
                "src/holosoma_inference/holosoma_cpp/tests/python_reference/locomotion.py",
                "holosoma/UPSTREAM_reference.py",
            ),
            ("orbitron", "ofl/orbitron/Orbitron%5Bwght%5D.ttf", "orbitron/Orbitron.ttf"),
            ("orbitron", "ofl/orbitron/OFL.txt", "orbitron/OFL.txt"),
        ]
    )
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        records.extend(pool.map(lambda args: fetch(*args), jobs))
    temporary_manifest = ROOT / f"third_party/manifest-{uuid.uuid4().hex}.tmp"
    temporary_manifest.write_text(
        json.dumps({"sources": SOURCES, "files": records}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary_manifest.replace(ROOT / "third_party/manifest.json")
    print(
        f"Fetched {len(records)} files, {sum(r['bytes'] for r in records) / 1e6:.1f} MB; manifest saved."
    )


if __name__ == "__main__":
    main()
