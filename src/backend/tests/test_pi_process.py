from __future__ import annotations

from pathlib import Path

import pytest

from config import Settings
from models import Conversation
from pi_process import PiProcess
from process_manager import CapacityError, ProcessManager


def _make_settings(tmp_path: Path, max_procs: int = 20) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        pi_model="us.anthropic.claude-haiku-4-5-20251001-v1:0",
        max_pi_processes=max_procs,
    )


def _make_conversation(
    cid: str = "conv-1",
    tenant_id: str = "tenant-a",
    user_id: str = "user-1",
    pi_session_path: str | None = None,
) -> Conversation:
    return Conversation(
        id=cid,
        tenant_id=tenant_id,
        user_id=user_id,
        title="Test",
        pi_session_path=pi_session_path,
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )


@pytest.mark.asyncio
async def test_it3_spawn_get_state_prompt_stream(tmp_path):
    """IT-3: spawn pi, get_state, send prompt, receive events through agent_settled,
    verify >1 text_delta."""
    settings = _make_settings(tmp_path)
    conv = _make_conversation()
    workdir = settings.data_dir / "tenants" / conv.tenant_id / "workdirs" / conv.id
    workdir.mkdir(parents=True)
    session_dir = settings.data_dir / "tenants" / conv.tenant_id / "sessions"
    session_dir.mkdir(parents=True)

    import os

    cmd = [
        "pi", "--mode", "rpc", "--no-tools", "--no-context-files",
        "--provider", "amazon-bedrock",
        "--model", settings.pi_model,
        "--session-dir", str(session_dir),
    ]
    env = {**os.environ, "AWS_PROFILE": "default"}

    proc = PiProcess()
    await proc.start(cmd, env, str(workdir))

    try:
        assert proc.is_alive
        assert proc.state == "ready"
        assert not proc.is_streaming

        state_resp = await proc.send_get_state()
        assert state_resp.get("success") is True
        assert state_resp["data"]["isStreaming"] is False
        assert state_resp["data"]["sessionFile"] is not None

        prompt_resp = await proc.send_prompt("Reply with exactly three words: hello world test")
        assert prompt_resp.get("success") is True

        text_deltas = []
        event_types = []

        async for event in proc.iter_events():
            etype = event.get("type")
            event_types.append(etype)

            if etype == "message_update":
                ame = event.get("assistantMessageEvent", {})
                if ame.get("type") == "text_delta":
                    text_deltas.append(ame["delta"])

        assert "agent_settled" in event_types
        assert len(text_deltas) > 1, f"Expected >1 text_delta, got {len(text_deltas)}"
        full_text = "".join(text_deltas)
        assert len(full_text.strip()) > 0

        assert proc.state == "idle"
        assert not proc.is_streaming
    finally:
        await proc.shutdown()


@pytest.mark.asyncio
async def test_it10_no_tools_enabled(tmp_path):
    """IT-10: verify pi process reports no enabled tools."""
    settings = _make_settings(tmp_path)
    conv = _make_conversation()
    workdir = settings.data_dir / "tenants" / conv.tenant_id / "workdirs" / conv.id
    workdir.mkdir(parents=True)
    session_dir = settings.data_dir / "tenants" / conv.tenant_id / "sessions"
    session_dir.mkdir(parents=True)

    import os

    cmd = [
        "pi", "--mode", "rpc", "--no-tools", "--no-context-files",
        "--provider", "amazon-bedrock",
        "--model", settings.pi_model,
        "--session-dir", str(session_dir),
    ]
    env = {**os.environ, "AWS_PROFILE": "default"}

    proc = PiProcess()
    await proc.start(cmd, env, str(workdir))

    try:
        await proc.send_prompt("Reply with exactly: ok")
        agent_end_event = None
        async for event in proc.iter_events():
            if event.get("type") == "agent_end":
                agent_end_event = event

        assert agent_end_event is not None
        messages = agent_end_event.get("messages", [])
        system_msg = next((m for m in messages if m.get("role") == "system"), None)
        assert system_msg is not None

        tools_section = system_msg.get("sections", {}).get("tools", "")
        assert "(none)" in tools_section, (
            f"Expected '(none)' in tools section, got: {tools_section[:200]}"
        )
    finally:
        await proc.shutdown()


@pytest.mark.asyncio
async def test_process_manager_cap_yields_503(tmp_path, app):
    """MAX_PI_PROCESSES cap: when at capacity, get_or_create raises CapacityError."""
    settings = Settings(
        data_dir=tmp_path / "data",
        pi_model="us.anthropic.claude-haiku-4-5-20251001-v1:0",
        max_pi_processes=1,
    )
    pm = ProcessManager(settings, app.state.session_factory)
    await pm.start()

    conv1 = _make_conversation(cid="conv-cap-1")
    conv2 = _make_conversation(cid="conv-cap-2")

    try:
        proc1 = await pm.get_or_create(conv1)
        assert proc1.is_alive

        with pytest.raises(CapacityError):
            await pm.get_or_create(conv2)
    finally:
        await pm.shutdown_all()


@pytest.mark.asyncio
async def test_workdir_created_under_tenant_data_root(tmp_path, app):
    """ProcessManager creates cwd under DATA_DIR/tenants/<tid>/workdirs/<cid>/."""
    settings = Settings(
        data_dir=tmp_path / "data",
        pi_model="us.anthropic.claude-haiku-4-5-20251001-v1:0",
    )
    pm = ProcessManager(settings, app.state.session_factory)
    await pm.start()

    conv = _make_conversation(cid="conv-wd-1", tenant_id="tenant-wd")

    try:
        await pm.get_or_create(conv)
        workdir = tmp_path / "data" / "tenants" / "tenant-wd" / "workdirs" / "conv-wd-1"
        assert workdir.exists()
        assert workdir.is_dir()
    finally:
        await pm.shutdown_all()


@pytest.mark.asyncio
async def test_session_path_saved(tmp_path, app):
    """After spawning a new conversation, pi_session_path is set on the Conversation object."""
    settings = Settings(
        data_dir=tmp_path / "data",
        pi_model="us.anthropic.claude-haiku-4-5-20251001-v1:0",
    )
    pm = ProcessManager(settings, app.state.session_factory)
    await pm.start()

    conv = _make_conversation(cid="conv-sp-1")
    # Insert the conversation into DB so the update works
    async with app.state.session_factory() as session:
        from datetime import UTC, datetime

        from models import Conversation as ConvModel

        now = datetime.now(UTC).isoformat()
        db_conv = ConvModel(
            id=conv.id,
            tenant_id=conv.tenant_id,
            user_id=conv.user_id,
            title="Test",
            created_at=now,
            updated_at=now,
        )
        session.add(db_conv)
        await session.commit()

    try:
        await pm.get_or_create(conv)
        assert conv.pi_session_path is not None
        assert conv.pi_session_path.endswith(".jsonl")
    finally:
        await pm.shutdown_all()
