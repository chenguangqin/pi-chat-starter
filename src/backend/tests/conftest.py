from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app import create_app
from config import Settings


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture
def settings(tmp_data_dir: Path) -> Settings:
    return Settings(
        data_dir=tmp_data_dir,
        pi_model="us.anthropic.claude-haiku-4-5-20251001-v1:0",
    )


@pytest.fixture
async def app(settings: Settings):
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app) -> AsyncGenerator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
