from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models import Conversation, Message


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self, tenant_id: str) -> list[Conversation]:
        result = await self._session.execute(
            select(Conversation)
            .where(Conversation.tenant_id == tenant_id)
            .order_by(Conversation.updated_at.desc())
        )
        return list(result.scalars().all())

    async def create(self, tenant_id: str, user_id: str, title: str | None = None) -> Conversation:
        now = datetime.now(UTC).isoformat()
        conv = Conversation(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            user_id=user_id,
            title=title or "New conversation",
            created_at=now,
            updated_at=now,
        )
        self._session.add(conv)
        await self._session.commit()
        return conv

    async def get_by_id(self, conversation_id: str, tenant_id: str) -> Conversation | None:
        result = await self._session.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def rename(self, conversation_id: str, tenant_id: str, title: str) -> Conversation | None:
        conv = await self.get_by_id(conversation_id, tenant_id)
        if conv is None:
            return None
        now = datetime.now(UTC).isoformat()
        await self._session.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id, Conversation.tenant_id == tenant_id)
            .values(title=title, updated_at=now)
        )
        await self._session.commit()
        conv.title = title
        conv.updated_at = now
        return conv

    async def delete(self, conversation_id: str, tenant_id: str) -> bool:
        conv = await self.get_by_id(conversation_id, tenant_id)
        if conv is None:
            return False
        await self._session.execute(
            delete(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.tenant_id == tenant_id,
            )
        )
        await self._session.commit()
        return True


class MessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_conversation(
        self, conversation_id: str, tenant_id: str
    ) -> list[Message] | None:
        conv_result = await self._session.execute(
            select(Conversation.id).where(
                Conversation.id == conversation_id,
                Conversation.tenant_id == tenant_id,
            )
        )
        if conv_result.scalar_one_or_none() is None:
            return None

        result = await self._session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        )
        return list(result.scalars().all())

    async def create(
        self,
        conversation_id: str,
        tenant_id: str,
        role: str,
        content: str,
    ) -> Message | None:
        conv_result = await self._session.execute(
            select(Conversation.id).where(
                Conversation.id == conversation_id,
                Conversation.tenant_id == tenant_id,
            )
        )
        if conv_result.scalar_one_or_none() is None:
            return None

        now = datetime.now(UTC).isoformat()
        msg = Message(
            id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            role=role,
            content=content,
            created_at=now,
        )
        self._session.add(msg)
        await self._session.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(updated_at=now)
        )
        await self._session.commit()
        return msg
