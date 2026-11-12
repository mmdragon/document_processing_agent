import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(upload_dir=tmp_path / "uploads", max_upload_bytes=1024)


@pytest.fixture
def client(settings) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)
