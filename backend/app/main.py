from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import router as api_router
from app.core.config import get_settings
from app.db.session import Base, engine
from app.services.storage_service import ensure_storage_layout


settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_storage_layout()
    Base.metadata.create_all(bind=engine)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/health")
    def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
