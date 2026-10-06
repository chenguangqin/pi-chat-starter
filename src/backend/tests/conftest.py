from __future__ import annotations

import asyncio
import socket
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from pathlib import Path

import pytest
import uvicorn
from fastapi import FastAPI
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


@dataclass
class LiveServer:
    """A real uvicorn server on a real port, plus the app whose state it serves."""

    base_url: str
    app: FastAPI


@pytest.fixture
async def live_server(settings: Settings) -> AsyncGenerator[LiveServer]:
    """Serve the app over real TCP.

    Why this exists instead of reusing the `client` fixture: httpx's `ASGITransport`
    buffers the entire response body, so every SSE event appears to the test client at
    the same instant (measured: a 12-delta reply arrives with a 0.00s spread) and two
    `asyncio.gather`-ed requests complete one after the other. That makes it impossible
    to tell real incremental streaming from a server that accumulated the whole reply,
    or real concurrency from serialization — both of which `vision.md` requires. Tests
    that assert on *timing* must go over the wire; `ASGITransport` is fine for
    everything else and is cheaper, so both fixtures exist.
    """
    application = create_app(settings)

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    server = uvicorn.Server(
        uvicorn.Config(
            application,
            host="127.0.0.1",
            port=port,
            log_level="warning",
            lifespan="on",
        )
    )
    serve_task = asyncio.create_task(server.serve())
    try:
        async with asyncio.timeout(30):
            # noqa: ASYNC110 — uvicorn exposes readiness as a plain bool, not an
            # asyncio.Event, so polling is the only option.
            while not server.started:  # noqa: ASYNC110
                await asyncio.sleep(0.02)
        yield LiveServer(base_url=f"http://127.0.0.1:{port}", app=application)
    finally:
        server.should_exit = True
        # `asyncio.timeout` is an async context manager — `with` raises TypeError here
        # and leaves the server task unawaited.
        async with asyncio.timeout(30):
            await serve_task
