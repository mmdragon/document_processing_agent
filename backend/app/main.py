from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import documents, health
from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Document Processing Agent",
        version="0.1.0",
        description="Local-first invoice extraction and validation. No payment actions.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],  # no PUT/DELETE endpoints exist
        allow_headers=["*"],
    )
    app.include_router(health.router, prefix="/api")
    app.include_router(documents.router, prefix="/api")
    return app


app = create_app()
