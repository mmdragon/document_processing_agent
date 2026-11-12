from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Runtime settings, read from environment variables or backend/.env."""

    model_config = SettingsConfigDict(env_file=BACKEND_ROOT / ".env", extra="ignore")

    # Uploads and the database live under backend/data/, never in frontend assets.
    upload_dir: Path = BACKEND_ROOT / "data" / "uploads"
    database_path: Path = BACKEND_ROOT / "data" / "documents.sqlite3"
    max_upload_bytes: int = 10 * 1024 * 1024  # 10 MB
    max_pages: int = 50
    # A page with fewer characters than this is treated as having no usable text layer.
    min_text_chars_per_page: int = 20
    # OCR runs only when this is true AND the tesseract binary is installed.
    ocr_enabled: bool = True
    ocr_language: str = "eng"
    cors_origins: list[str] = ["http://localhost:3000"]
    explainer_mode: str = "mock"  # only "mock" is implemented; no paid APIs


@lru_cache
def get_settings() -> Settings:
    return Settings()
