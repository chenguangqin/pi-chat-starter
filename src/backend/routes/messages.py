from __future__ import annotations

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from starlette.responses import StreamingResponse

from auth import Identity, get_identity
from pi_process import PiProcess
from process_manager import CapacityError
from repositories import ConversationRepository, MessageRepository
from sse import done_event, status_event, text_delta_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/conversations", tags=["messages"])

IdentityDep = Annotated[Identity, Depends(get_identity)]


async def _cleanup_streaming(pi_proc: PiProcess) -> None:
    try:
        await pi_proc.abort()
        async for event in pi_proc.iter_events():
            if event.get("type") == "agent_settled":
                break
    except Exception:
        logger.exception("Error during pi abort cleanup")


@router.post("/{conversation_id}/messages")
async def send_message(
    conversation_id: str, request: Request, identity: IdentityDep
):
    body = await request.json()
    content = body.get("content", "").strip()
    if not content:
        return JSONResponse(status_code=422, content={"detail": "content is required"})

    async with request.app.state.session_factory() as session:
        conv_repo = ConversationRepository(session)
        conversation = await conv_repo.get_by_id(conversation_id, identity.tenant_id)
        if conversation is None:
            return JSONResponse(status_code=404, content={"detail": "Not found"})

        msg_repo = MessageRepository(session)
        await msg_repo.create(conversation_id, identity.tenant_id, "user", content)

    pm = request.app.state.process_manager
    try:
        pi_proc = await pm.get_or_create(conversation)
    except CapacityError:
        return JSONResponse(
            status_code=503, content={"detail": "Too many active conversations"}
        )

    if pi_proc.is_streaming:
        return JSONResponse(
            status_code=409, content={"detail": "Conversation is busy"}
        )

    await pi_proc.send_prompt(content)

    session_factory = request.app.state.session_factory
    tenant_id = identity.tenant_id

    async def event_stream():
        accumulated_text: list[str] = []
        assistant_msg_id: str | None = None
        try:
            async for event in pi_proc.iter_events():
                etype = event.get("type")

                if etype == "message_update":
                    ame = event.get("assistantMessageEvent", {})
                    ame_type = ame.get("type")

                    if ame_type == "text_delta":
                        delta = ame.get("delta", "")
                        accumulated_text.append(delta)
                        yield text_delta_event(delta)

                    # The model reasons before answering, and that phase emits only
                    # `thinking_delta` events — measured at up to 218 of them over 7.4s
                    # with no text at all. Those deltas are deliberately not forwarded
                    # (reasoning is not part of the reply and is not persisted), but the
                    # client needs to know the agent is working, or it shows an empty
                    # bubble for the whole reasoning phase.
                    elif ame_type == "thinking_start":
                        yield status_event("thinking")
                    elif ame_type == "text_start":
                        yield status_event("responding")

                elif etype == "message_end":
                    full_text = "".join(accumulated_text)
                    if full_text:
                        async with session_factory() as session:
                            msg_repo = MessageRepository(session)
                            msg = await msg_repo.create(
                                conversation_id, tenant_id, "assistant", full_text
                            )
                            if msg:
                                assistant_msg_id = msg.id

                elif etype == "agent_settled":
                    yield done_event(assistant_msg_id or "")

        except BaseException:
            if pi_proc.is_streaming:
                asyncio.create_task(_cleanup_streaming(pi_proc))
            raise

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
