"""device api keys, alert webhooks and their delivery log

Revision ID: 013
Revises: 012
Create Date: 2026-08-18 14:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())

    if "api_keys" not in tables:
        op.create_table(
            "api_keys",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("key_prefix", sa.String(16), nullable=False),
            sa.Column("key_hash", sa.String(64), nullable=False, unique=True),
            sa.Column(
                "created_by_id",
                UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_api_keys_key_prefix", "api_keys", ["key_prefix"])
        op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"])

    if "webhooks" not in tables:
        op.create_table(
            "webhooks",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("url", sa.String(1000), nullable=False),
            sa.Column("secret", sa.String(64), nullable=False),
            sa.Column("min_severity", sa.String(20), nullable=False, server_default="warning"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("headers", JSONB, nullable=False, server_default="{}"),
            sa.Column("last_status_code", sa.Integer(), nullable=True),
            sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if "webhook_deliveries" not in tables:
        op.create_table(
            "webhook_deliveries",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "webhook_id",
                UUID(as_uuid=True),
                sa.ForeignKey("webhooks.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("event", sa.String(60), nullable=False),
            sa.Column("payload", JSONB, nullable=False, server_default="{}"),
            sa.Column("status_code", sa.Integer(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_webhook_deliveries_webhook_id", "webhook_deliveries", ["webhook_id"])
        op.create_index("ix_webhook_deliveries_created_at", "webhook_deliveries", ["created_at"])


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())

    if "webhook_deliveries" in tables:
        op.drop_index("ix_webhook_deliveries_created_at", table_name="webhook_deliveries")
        op.drop_index("ix_webhook_deliveries_webhook_id", table_name="webhook_deliveries")
        op.drop_table("webhook_deliveries")
    if "webhooks" in tables:
        op.drop_table("webhooks")
    if "api_keys" in tables:
        op.drop_index("ix_api_keys_key_hash", table_name="api_keys")
        op.drop_index("ix_api_keys_key_prefix", table_name="api_keys")
        op.drop_table("api_keys")
