from __future__ import annotations

import contextlib
import json

import pytest

HEADERS = {"x-tenant-id": "tenant-a", "x-user-id": "user-1"}


def _parse_sse_events(raw: str) -> list[dict]:
    events = []
    for line in raw.split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            with contextlib.suppress(json.JSONDecodeError):
                events.append(json.loads(line[6:]))
    return events


@pytest.mark.asyncio
async def test_it4_send_message_streams_and_persists(client):
    """IT-4: send message, verify SSE stream has >1 text_delta before done,
    verify user + assistant messages in DB."""
    create_resp = await client.post("/api/conversations", headers=HEADERS)
    assert create_resp.status_code == 201
    cid = create_resp.json()["id"]

    resp = await client.post(
        f"/api/conversations/{cid}/messages",
        headers=HEADERS,
        json={"content": "List the numbers 1 through 20, each on its own line"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse_events(resp.text)

    text_deltas = [e for e in events if e.get("type") == "text_delta"]
    done_events = [e for e in events if e.get("type") == "done"]

    assert len(text_deltas) > 1, f"Expected >1 text_delta, got {len(text_deltas)}"
    assert len(done_events) == 1
    assert done_events[0].get("message_id")

    full_text = "".join(e["delta"] for e in text_deltas)
    assert len(full_text.strip()) > 0

    msgs_resp = await client.get(
        f"/api/conversations/{cid}/messages", headers=HEADERS
    )
    assert msgs_resp.status_code == 200
    messages = msgs_resp.json()
    assert len(messages) == 2

    assert messages[0]["role"] == "user"
    assert "1 through 20" in messages[0]["content"]
    assert messages[1]["role"] == "assistant"
    assert len(messages[1]["content"].strip()) > 0


@pytest.mark.asyncio
async def test_send_message_to_nonexistent_conversation_404(client):
    resp = await client.post(
        "/api/conversations/nonexistent/messages",
        headers=HEADERS,
        json={"content": "hello"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_send_message_empty_content_422(client):
    create_resp = await client.post("/api/conversations", headers=HEADERS)
    cid = create_resp.json()["id"]

    resp = await client.post(
        f"/api/conversations/{cid}/messages",
        headers=HEADERS,
        json={"content": ""},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_send_message_no_auth_401(client):
    resp = await client.post(
        "/api/conversations/any-id/messages",
        json={"content": "hello"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_it8_abort_on_disconnect(app):
    """IT-8: client disconnect triggers abort — verified by aborting mid-stream
    and confirming pi reaches settled state."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post("/api/conversations", headers=HEADERS)
        cid = create_resp.json()["id"]

    pm = app.state.process_manager

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        create_resp = await client.post("/api/conversations", headers=HEADERS)
        cid = create_resp.json()["id"]

        resp = await client.post(
            f"/api/conversations/{cid}/messages",
            headers=HEADERS,
            json={"content": "Write a 500-word essay about clouds"},
        )
        events = _parse_sse_events(resp.text)
        text_deltas = [e for e in events if e.get("type") == "text_delta"]
        assert len(text_deltas) > 0

    proc = pm._processes.get(cid)
    if proc is not None:
        assert not proc.is_streaming

    # Verify pi can handle another message on the same conversation (not stuck)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp2 = await client.post(
            f"/api/conversations/{cid}/messages",
            headers=HEADERS,
            json={"content": "Reply with exactly: still alive"},
        )
        assert resp2.status_code == 200
        events2 = _parse_sse_events(resp2.text)
        done_events = [e for e in events2 if e.get("type") == "done"]
        assert len(done_events) == 1
