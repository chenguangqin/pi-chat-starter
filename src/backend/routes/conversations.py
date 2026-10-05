from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from auth import Identity, get_identity
from repositories import ConversationRepository, MessageRepository

router = APIRouter(prefix="/api/conversations", tags=["conversations"])

IdentityDep = Annotated[Identity, Depends(get_identity)]


@router.get("")
async def list_conversations(request: Request, identity: IdentityDep):
    async with request.app.state.session_factory() as session:
        repo = ConversationRepository(session)
        convs = await repo.list(identity.tenant_id)
        return [
            {
                "id": c.id,
                "title": c.title,
                "created_at": c.created_at,
                "updated_at": c.updated_at,
            }
            for c in convs
        ]


@router.post("", status_code=201)
async def create_conversation(request: Request, identity: IdentityDep):
    body = await request.json() if await request.body() else {}
    title = body.get("title")
    async with request.app.state.session_factory() as session:
        repo = ConversationRepository(session)
        conv = await repo.create(identity.tenant_id, identity.user_id, title)
        return {"id": conv.id, "title": conv.title, "created_at": conv.created_at}


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: str, request: Request, identity: IdentityDep
):
    async with request.app.state.session_factory() as session:
        repo = ConversationRepository(session)
        conv = await repo.get_by_id(conversation_id, identity.tenant_id)
        if conv is None:
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        return {
            "id": conv.id,
            "title": conv.title,
            "created_at": conv.created_at,
            "updated_at": conv.updated_at,
        }


@router.patch("/{conversation_id}")
async def rename_conversation(
    conversation_id: str, request: Request, identity: IdentityDep
):
    body = await request.json()
    title = body.get("title")
    if not title:
        return JSONResponse(status_code=422, content={"detail": "title is required"})
    async with request.app.state.session_factory() as session:
        repo = ConversationRepository(session)
        conv = await repo.rename(conversation_id, identity.tenant_id, title)
        if conv is None:
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        return {"id": conv.id, "title": conv.title, "updated_at": conv.updated_at}


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: str, request: Request, identity: IdentityDep
):
    async with request.app.state.session_factory() as session:
        repo = ConversationRepository(session)
        deleted = await repo.delete(conversation_id, identity.tenant_id)
        if not deleted:
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        return None


@router.get("/{conversation_id}/messages")
async def list_messages(
    conversation_id: str, request: Request, identity: IdentityDep
):
    async with request.app.state.session_factory() as session:
        msg_repo = MessageRepository(session)
        messages = await msg_repo.list_for_conversation(conversation_id, identity.tenant_id)
        if messages is None:
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        return [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at,
            }
            for m in messages
        ]
