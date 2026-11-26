import pytest
from embodied_arena.platform.app import create_app
from embodied_arena.platform.settings import Settings
from fastapi.testclient import TestClient


@pytest.fixture
def portal(tmp_path):
    app = create_app(Settings(data=tmp_path, workers=False))
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as client:
        yield app, client
