from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Runtime settings, read from environment variables or backend/.env."""

    model_config = SettingsConfigDict(env_file=BACKEND_ROOT / ".env", extra="ignore")

    # Uploads live under backend/, never inside the frontend's public assets.
    upload_dir: Path = BACKEND_ROOT / "data" / "uploads"
    max_upload_bytes: int = 10 * 1024 * 1024  # 10 MB
    cors_origins: list[str] = ["http://localhost:3000"]
    explainer_mode: str = "mock"  # only "mock" is implemented; no paid APIs


@lru_cache
def get_settings() -> Settings:
    return Settings()
