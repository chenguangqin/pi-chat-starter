from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from config import Settings
from database import create_engine, create_session_factory, run_migrations


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings: Settings = app.state.settings
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    await run_migrations(engine)

    app.state.engine = engine
    app.state.session_factory = session_factory

    yield

    await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = Settings()

    app = FastAPI(title="common_agent", lifespan=lifespan)
    app.state.settings = settings

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    return app
