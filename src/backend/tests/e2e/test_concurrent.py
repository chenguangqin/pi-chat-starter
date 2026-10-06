"""IT-9 — true concurrent streaming across two tenants, over real HTTP.

`vision.md` promises: "Two users send messages at the same time → both get their own
streamed replies; neither sees the other's tokens." The original e2e test exercised the
two tenants *sequentially*, so it could not have caught a backend that serialized every
stream behind one lock, nor one that leaked tokens between two in-flight pi processes.

This test uses the `live_server` fixture (a real uvicorn on a real port) rather than the
`client` fixture, because httpx's `ASGITransport` buffers the whole response body — under
it, every SSE delta lands at the same instant and gathered requests finish one after the
other, which would make both assertions below meaningless. See `conftest.live_server`.

Asserted here:

1. **Incremental delivery** — within each stream, the deltas span more than
   `MIN_SPREAD_SECONDS`. A backend that accumulated the full reply and flushed once
   fails. This requires a long enough reply to be meaningful — see the prompt below.
2. **Temporal overlap** — the two streams are in flight simultaneously. A serializing
   backend fails here even though every other assertion would still pass.
3. **No token cross-talk** — each stream carries only its own tenant's marker.
4. **Concurrent processes** — the ProcessManager holds two live pi processes at once.
5. **Correct persistence** — each conversation stores exactly what its own stream
   delivered, with no bleed across tenants.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time

import pytest
from httpx import AsyncClient

from tests.conftest import LiveServer

TENANT_A = {"x-tenant-id": "tenant-a", "x-user-id": "user-a1"}
TENANT_B = {"x-tenant-id": "tenant-b", "x-user-id": "user-b1"}

MARKER_A = "ALPHA"
MARKER_B = "BRAVO"

# The prompt has to be chosen carefully, and for a non-obvious reason: the model thinks
# before it answers, and only `text_delta` events reach the client.
#
# Measured against raw pi, same model:
#   "...300 words, begin every sentence with ALPHA"  -> 218 thinking deltas over 7.4s,
#                                                       then 50 text deltas in 0.03s
#   "start with ALPHA, then a 400-word essay..."     ->  20 thinking deltas over 0.6s,
#                                                       then 238 text deltas over 5.6s
#
# A constraint the model has to reason about moves all the elapsed time into the thinking
# phase and leaves a short answer that arrives in one burst — `first` collapses onto
# `last`, and the overlap assertion ends up comparing two *generation end times* rather
# than two streaming windows, which fails on any backend, concurrent or not. So: put the
# marker somewhere trivial and ask for a long answer.
MIN_SPREAD_SECONDS = 1.0


def _prompt_for(marker: str) -> str:
    return (
        f"Start your reply with the single word {marker}, then write a detailed "
        f"400-word essay about the history of sailing ships in plain prose."
    )


async def _stream_with_timings(
    base_url: str, headers: dict, prompt: str
) -> dict:
    """Create a conversation and stream one reply, timestamping every delta.

    Each call uses its **own** `AsyncClient`. Sharing one client would put both
    streams on a single HTTP/1.1 connection, where head-of-line blocking could
    serialize them in the client and be misread as a backend defect.
    """
    deltas: list[str] = []
    stamps: list[float] = []
    saw_done = False

    async with AsyncClient(base_url=base_url, timeout=180.0) as client:
        created = await client.post("/api/conversations", headers=headers)
        assert created.status_code == 201, created.text
        cid = created.json()["id"]

        async with client.stream(
            "POST",
            f"/api/conversations/{cid}/messages",
            headers=headers,
            json={"content": prompt},
        ) as resp:
            assert resp.status_code == 200, f"stream failed: {resp.status_code}"
            assert resp.headers["content-type"].startswith("text/event-stream")

            async for line in resp.aiter_lines():
                line = line.strip()
                if not line.startswith("data: "):
                    continue
                with contextlib.suppress(json.JSONDecodeError):
                    event = json.loads(line[6:])
                    if event.get("type") == "text_delta":
                        deltas.append(event.get("delta", ""))
                        stamps.append(time.monotonic())
                    elif event.get("type") == "done":
                        saw_done = True

        assert saw_done, "stream ended without a done event"
        assert len(deltas) > 1, (
            f"expected incremental streaming, got {len(deltas)} delta(s)"
        )

        history = await client.get(
            f"/api/conversations/{cid}/messages", headers=headers
        )
        assert history.status_code == 200
        rows = history.json()

    return {
        "id": cid,
        "text": "".join(deltas),
        "rows": rows,
        "first": stamps[0],
        "last": stamps[-1],
        "spread": stamps[-1] - stamps[0],
        "count": len(deltas),
    }


@pytest.mark.asyncio
async def test_it9_concurrent_streams_do_not_interfere(live_server: LiveServer):
    """Two tenants stream simultaneously: overlapping in time, isolated in content."""
    # The actual concurrency: both streams in flight at once, on separate connections.
    stream_a, stream_b = await asyncio.gather(
        _stream_with_timings(live_server.base_url, TENANT_A, _prompt_for(MARKER_A)),
        _stream_with_timings(live_server.base_url, TENANT_B, _prompt_for(MARKER_B)),
    )

    # 1. Each stream was delivered incrementally, not flushed in one block.
    for tag, stream in (("A", stream_a), ("B", stream_b)):
        assert stream["spread"] > MIN_SPREAD_SECONDS, (
            f"tenant {tag}: {stream['count']} deltas arrived within "
            f"{stream['spread']:.2f}s — the reply was buffered, not streamed"
        )

    # 2. Temporal overlap — neither stream waited for the other to finish.
    overlap = min(stream_a["last"], stream_b["last"]) - max(
        stream_a["first"], stream_b["first"]
    )
    assert overlap > 0.0, (
        f"no overlap ({overlap:.2f}s): one stream began only after the other had "
        "finished — the backend is serializing concurrent streams"
    )

    # 3. No token cross-talk between the two in-flight streams.
    assert MARKER_A in stream_a["text"], (
        f"tenant A's reply lacks its own marker: {stream_a['text'][:200]!r}"
    )
    assert MARKER_B in stream_b["text"], (
        f"tenant B's reply lacks its own marker: {stream_b['text'][:200]!r}"
    )
    assert MARKER_B not in stream_a["text"], (
        f"tenant B's marker leaked into tenant A's stream: "
        f"{stream_a['text'][:200]!r}"
    )
    assert MARKER_A not in stream_b["text"], (
        f"tenant A's marker leaked into tenant B's stream: "
        f"{stream_b['text'][:200]!r}"
    )

    # 4. Two live pi processes coexisted — one per conversation, not a shared one.
    active = live_server.app.state.process_manager.active_count
    assert active == 2, f"expected one live pi process per conversation, got {active}"

    # 5. Persistence matches each stream, with no bleed across tenants.
    for stream, own, foreign in (
        (stream_a, MARKER_A, MARKER_B),
        (stream_b, MARKER_B, MARKER_A),
    ):
        rows = stream["rows"]
        assert [r["role"] for r in rows] == ["user", "assistant"], rows

        assistant = rows[1]["content"]
        assert assistant == stream["text"], (
            "stored assistant message differs from what the stream delivered"
        )
        assert own in assistant
        assert foreign not in assistant, (
            f"marker {foreign} from the other tenant leaked into stored rows"
        )
