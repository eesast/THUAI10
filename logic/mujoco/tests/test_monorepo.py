import hashlib
import json
from pathlib import Path

import pytest
from embodied_arena.config import CAPI_ROOT, DOCS_ROOT, FRONTEND_ROOT, REPOSITORY_ROOT, ROOT
from embodied_arena.platform.packages import template_zip

from dependency.shell.mujoco.build_package import build_package


def test_monorepo_components_resolve_to_their_assigned_directories():
    assert ROOT == REPOSITORY_ROOT / "logic/mujoco"
    assert FRONTEND_ROOT == REPOSITORY_ROOT / "interface/mujoco"
    assert CAPI_ROOT == REPOSITORY_ROOT / "CAPI/python/mujoco"
    assert DOCS_ROOT == REPOSITORY_ROOT / "docs/mujoco"
    assert (FRONTEND_ROOT / "index.html").is_file()
    assert (CAPI_ROOT / "api.py").is_file()


def test_player_package_matches_launcher_catalog_without_private_state(tmp_path):
    output = tmp_path / "release"
    catalog = build_package(output)
    assert catalog["version"] == "0.4.0-prototype"
    paths = {item["path"] for item in catalog["files"]}
    assert "thuai10-launch.json" in paths
    assert "interface/mujoco/index.html" in paths
    assert "CAPI/python/mujoco/policy.py" in paths
    forbidden = {".git", ".venv", "var", "artifacts", "third_party", "node_modules"}
    for item in catalog["files"]:
        assert not set(Path(item["path"]).parts) & forbidden
        assert ".thuai10-state.json" not in item["path"]
        payload = (output / "payload" / item["path"]).read_bytes()
        assert len(payload) == item["size"]
        assert hashlib.sha256(payload).hexdigest() == item["sha256"]
        assert item["url"].startswith("payload/")
    launch = json.loads((output / "payload/thuai10-launch.json").read_text())
    assert launch["server"]["path"] == "logic/mujoco/.venv/Scripts/python.exe"
    assert launch["players"] == []
    with pytest.raises(FileExistsError):
        build_package(output)


def test_download_template_includes_the_canonical_capi_types():
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(template_zip("arena-python-v1"))) as package:
        assert package.read("api.py") == (CAPI_ROOT / "api.py").read_bytes()
