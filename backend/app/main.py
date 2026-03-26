from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.engine.url import make_url

from app.api.router import router as api_router
from app.core.config import get_settings
from app.db.session import Base, engine
from app.services.storage_service import ensure_storage_layout


settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_storage_layout()
    # Postgres 등은 Alembic만으로 스키마를 맞춘다. create_all은 SQLite 로컬/스모크용.
    if make_url(settings.database_url).get_backend_name() == "sqlite":
        Base.metadata.create_all(bind=engine)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    origins = [o.strip() for o in settings.cors_allowed_origins.split(",") if o.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/health")
    def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
