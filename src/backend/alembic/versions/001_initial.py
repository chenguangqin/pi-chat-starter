"""Initial tables: conversations and messages

Revision ID: 001
Revises:
Create Date: 2026-10-05
"""

import sqlalchemy as sa

from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False, server_default="New conversation"),
        sa.Column("pi_session_path", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_conversations_tenant", "conversations", ["tenant_id", sa.text("updated_at DESC")]
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.Text(),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_index("ix_messages_conversation", "messages", ["conversation_id", "created_at"])


def downgrade() -> None:
    op.drop_table("messages")
    op.drop_table("conversations")
