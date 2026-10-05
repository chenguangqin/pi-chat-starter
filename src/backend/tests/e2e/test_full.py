"""End-to-end test — the "Done" gate from vision.md.

Exercises all six criteria against real Bedrock-backed pi:
1. Two tenants, each with a user
2. Each user creates two conversations and exchanges messages
3. Streamed replies are incremental (>1 text_delta before done)
4. History survives a backend restart
5. Cross-tenant access refused on every endpoint, both directions
6. Agent has no file or shell tools
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app import create_app
from config import Settings

TENANT_A = {"x-tenant-id": "tenant-a", "x-user-id": "user-a1"}
TENANT_B = {"x-tenant-id": "tenant-b", "x-user-id": "user-b1"}


def _parse_sse_events(raw: str) -> list[dict]:
    events = []
    for line in raw.split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            with contextlib.suppress(json.JSONDecodeError):
                events.append(json.loads(line[6:]))
    return events


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        pi_model="us.anthropic.claude-haiku-4-5-20251001-v1:0",
    )


async def _create_conversation(client: AsyncClient, headers: dict) -> str:
    resp = await client.post("/api/conversations", headers=headers)
    assert resp.status_code == 201
    return resp.json()["id"]


async def _send_and_verify_stream(
    client: AsyncClient, cid: str, headers: dict, content: str
) -> str:
    """Send a message, verify incremental streaming, return full assistant text."""
    resp = await client.post(
        f"/api/conversations/{cid}/messages",
        headers=headers,
        json={"content": content},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse_events(resp.text)
    text_deltas = [e for e in events if e.get("type") == "text_delta"]
    done_events = [e for e in events if e.get("type") == "done"]

    assert len(text_deltas) > 1, (
        f"Expected >1 text_delta (incremental streaming), got {len(text_deltas)}"
    )
    assert len(done_events) == 1
    assert done_events[0].get("message_id")

    return "".join(e["delta"] for e in text_deltas)


def _assert_opaque_404(resp) -> None:
    assert resp.status_code == 404
    body = resp.json()
    assert "detail" in body
    for key in ("tenant_id", "user_id", "title", "content", "pi_session_path"):
        assert key not in body, f"Leaked field '{key}'"


@pytest.mark.asyncio
async def test_e2e_full(settings):
    """Complete Done gate: two tenants, streaming, restart, isolation, no-tools."""

    # =====================================================================
    # Phase 1 & 2 & 3: Two tenants × two conversations × real Bedrock
    #                   with incremental streaming asserted
    # =====================================================================
    app1 = create_app(settings)
    conversation_ids: dict[str, list[str]] = {"a": [], "b": []}

    async with app1.router.lifespan_context(app1), AsyncClient(
        transport=ASGITransport(app=app1), base_url="http://test"
    ) as client:
        # Tenant A: two conversations
        cid_a1 = await _create_conversation(client, TENANT_A)
        cid_a2 = await _create_conversation(client, TENANT_A)
        conversation_ids["a"] = [cid_a1, cid_a2]

        text_a1 = await _send_and_verify_stream(
            client, cid_a1, TENANT_A,
            "List the numbers 1 through 20, each on its own line",
        )
        assert len(text_a1.strip()) > 0

        await _send_and_verify_stream(
            client, cid_a1, TENANT_A,
            "Now list the numbers 21 through 30, each on its own line",
        )

        await _send_and_verify_stream(
            client, cid_a2, TENANT_A,
            "Explain what the number pi is in exactly three sentences",
        )

        # Tenant B: two conversations
        cid_b1 = await _create_conversation(client, TENANT_B)
        cid_b2 = await _create_conversation(client, TENANT_B)
        conversation_ids["b"] = [cid_b1, cid_b2]

        await _send_and_verify_stream(
            client, cid_b1, TENANT_B,
            "List the first 15 prime numbers, each on its own line",
        )

        await _send_and_verify_stream(
            client, cid_b2, TENANT_B,
            "Write a haiku about the ocean, then explain each line",
        )

        # Verify message counts in DB
        msgs_a1 = await client.get(
            f"/api/conversations/{cid_a1}/messages", headers=TENANT_A
        )
        assert len(msgs_a1.json()) == 4  # 2 user + 2 assistant

        msgs_b1 = await client.get(
            f"/api/conversations/{cid_b1}/messages", headers=TENANT_B
        )
        assert len(msgs_b1.json()) == 2  # 1 user + 1 assistant

    # App1 fully shut down

    # =====================================================================
    # Phase 4: History survives backend restart
    # =====================================================================
    app2 = create_app(settings)
    async with app2.router.lifespan_context(app2), AsyncClient(
        transport=ASGITransport(app=app2), base_url="http://test"
    ) as client:
        # Verify messages persisted for both tenants
        msgs_a1 = await client.get(
            f"/api/conversations/{cid_a1}/messages", headers=TENANT_A
        )
        assert msgs_a1.status_code == 200
        assert len(msgs_a1.json()) == 4

        msgs_b1 = await client.get(
            f"/api/conversations/{cid_b1}/messages", headers=TENANT_B
        )
        assert msgs_b1.status_code == 200
        assert len(msgs_b1.json()) == 2

        # Verify conversation lists
        convs_a = await client.get("/api/conversations", headers=TENANT_A)
        assert len(convs_a.json()) == 2

        convs_b = await client.get("/api/conversations", headers=TENANT_B)
        assert len(convs_b.json()) == 2

        # Send a new message — pi reloads session, reply is context-aware
        resp = await client.post(
            f"/api/conversations/{cid_a1}/messages",
            headers=TENANT_A,
            json={
                "content": (
                    "What was the first set of numbers I asked you to list? "
                    "Reply with just the range."
                )
            },
        )
        assert resp.status_code == 200
        events = _parse_sse_events(resp.text)
        text = "".join(
            e["delta"] for e in events if e.get("type") == "text_delta"
        )
        done = [e for e in events if e.get("type") == "done"]
        assert len(done) == 1
        assert "1" in text and "20" in text, (
            f"Expected context-aware reply about 1-20, got: {text[:200]}"
        )

    # App2 fully shut down

    # =====================================================================
    # Phase 5: Cross-tenant access refused on EVERY endpoint, BOTH directions
    # =====================================================================
    app3 = create_app(settings)
    async with app3.router.lifespan_context(app3), AsyncClient(
        transport=ASGITransport(app=app3), base_url="http://test"
    ) as client:
        for cid_a in conversation_ids["a"]:
            # Tenant B tries to access Tenant A's conversations
            _assert_opaque_404(
                await client.get(
                    f"/api/conversations/{cid_a}", headers=TENANT_B
                )
            )
            _assert_opaque_404(
                await client.patch(
                    f"/api/conversations/{cid_a}",
                    headers=TENANT_B,
                    json={"title": "Hacked"},
                )
            )
            _assert_opaque_404(
                await client.delete(
                    f"/api/conversations/{cid_a}", headers=TENANT_B
                )
            )
            _assert_opaque_404(
                await client.get(
                    f"/api/conversations/{cid_a}/messages",
                    headers=TENANT_B,
                )
            )
            _assert_opaque_404(
                await client.post(
                    f"/api/conversations/{cid_a}/messages",
                    headers=TENANT_B,
                    json={"content": "probe"},
                )
            )

        for cid_b in conversation_ids["b"]:
            # Tenant A tries to access Tenant B's conversations
            _assert_opaque_404(
                await client.get(
                    f"/api/conversations/{cid_b}", headers=TENANT_A
                )
            )
            _assert_opaque_404(
                await client.patch(
                    f"/api/conversations/{cid_b}",
                    headers=TENANT_A,
                    json={"title": "Hacked"},
                )
            )
            _assert_opaque_404(
                await client.delete(
                    f"/api/conversations/{cid_b}", headers=TENANT_A
                )
            )
            _assert_opaque_404(
                await client.get(
                    f"/api/conversations/{cid_b}/messages",
                    headers=TENANT_A,
                )
            )
            _assert_opaque_404(
                await client.post(
                    f"/api/conversations/{cid_b}/messages",
                    headers=TENANT_A,
                    json={"content": "probe"},
                )
            )

        # List isolation: each tenant sees only their own
        convs_a = await client.get("/api/conversations", headers=TENANT_A)
        convs_b = await client.get("/api/conversations", headers=TENANT_B)
        a_ids = {c["id"] for c in convs_a.json()}
        b_ids = {c["id"] for c in convs_b.json()}
        assert a_ids == set(conversation_ids["a"])
        assert b_ids == set(conversation_ids["b"])
        assert a_ids.isdisjoint(b_ids)

    # App3 fully shut down

    # =====================================================================
    # Phase 6: Agent has no file or shell tools
    # =====================================================================
    app4 = create_app(settings)
    async with app4.router.lifespan_context(app4):
        async with AsyncClient(
            transport=ASGITransport(app=app4), base_url="http://test"
        ) as client:
            # Create a fresh conversation and send a prompt to get agent_end
            cid_check = await _create_conversation(client, TENANT_A)

        # Access process manager directly for the tools check
        pm = app4.state.process_manager
        conv_model = None
        async with app4.state.session_factory() as session:
            from repositories import ConversationRepository

            repo = ConversationRepository(session)
            conv_model = await repo.get_by_id(cid_check, "tenant-a")

        assert conv_model is not None
        pi_proc = await pm.get_or_create(conv_model)
        await pi_proc.send_prompt("Reply with exactly: ok")

        agent_end_event = None
        async for event in pi_proc.iter_events():
            if event.get("type") == "agent_end":
                agent_end_event = event

        assert agent_end_event is not None
        messages = agent_end_event.get("messages", [])
        system_msg = next(
            (m for m in messages if m.get("role") == "system"), None
        )
        assert system_msg is not None

        tools_section = system_msg.get("sections", {}).get("tools", "")
        assert "(none)" in tools_section, (
            f"Expected '(none)' in tools section, got: {tools_section[:200]}"
        )
