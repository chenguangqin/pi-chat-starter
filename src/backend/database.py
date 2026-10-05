from __future__ import annotations

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import Settings


def create_engine(settings: Settings):
    engine = create_async_engine(settings.db_url, echo=False)

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, _connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def create_session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def run_migrations(engine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS conversations (
                id              TEXT PRIMARY KEY,
                tenant_id       TEXT NOT NULL,
                user_id         TEXT NOT NULL,
                title           TEXT NOT NULL DEFAULT 'New conversation',
                pi_session_path TEXT,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            )
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_conversations_tenant
            ON conversations(tenant_id, updated_at DESC)
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS messages (
                id              TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                role            TEXT NOT NULL,
                content         TEXT NOT NULL,
                created_at      TEXT NOT NULL
            )
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_messages_conversation
            ON messages(conversation_id, created_at)
        """))
