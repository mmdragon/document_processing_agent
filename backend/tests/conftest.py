import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path) -> Settings:
    # OCR off by default so results don't depend on whether tesseract is installed.
    return Settings(
        upload_dir=tmp_path / "uploads",
        database_path=tmp_path / "test.sqlite3",
        max_upload_bytes=200_000,
        max_pages=3,
        ocr_enabled=False,
    )


@pytest.fixture
def client(settings) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def make_pdf(*page_texts: str) -> bytes:
    """Build a PDF with one page per entry; an empty string makes a blank page."""
    doc = pymupdf.open()
    for text in page_texts:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
    return doc.tobytes()


def make_png() -> bytes:
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 60, 40), False)
    pix.set_rect(pix.irect, (255, 255, 255))
    return pix.tobytes("png")


def upload(client, name: str, data: bytes, content_type: str = "application/pdf"):
    return client.post("/api/documents", files={"file": (name, data, content_type)})
