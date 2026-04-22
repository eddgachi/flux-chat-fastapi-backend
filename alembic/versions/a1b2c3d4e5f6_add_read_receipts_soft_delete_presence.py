"""add read receipts, soft delete, and presence

Revision ID: a1b2c3d4e5f6
Revises: 6c93d0c0dead
Create Date: 2026-04-22 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "6c93d0c0dead"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add soft-delete and edit tracking to messages
    op.add_column("messages", sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("messages", sa.Column("edited_at", sa.DateTime(), nullable=True))

    # Add last_seen_at to users for presence tracking
    op.add_column("users", sa.Column("last_seen_at", sa.DateTime(), nullable=True))

    # Create message_reads table for read receipts
    op.create_table(
        "message_reads",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("read_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", "user_id", name="uq_message_read"),
    )
    op.create_index(op.f("ix_message_reads_id"), "message_reads", ["id"], unique=False)
    op.create_index(op.f("ix_message_reads_message_id"), "message_reads", ["message_id"], unique=False)
    op.create_index(op.f("ix_message_reads_user_id"), "message_reads", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_message_reads_user_id"), table_name="message_reads")
    op.drop_index(op.f("ix_message_reads_message_id"), table_name="message_reads")
    op.drop_index(op.f("ix_message_reads_id"), table_name="message_reads")
    op.drop_table("message_reads")
    op.drop_column("users", "last_seen_at")
    op.drop_column("messages", "edited_at")
    op.drop_column("messages", "is_deleted")
