"""Add payment authorization, atomic seats, webhook receipts, and outbox.

Revision ID: 7f4a2d1c9e11
Revises: 1d5d0d42e5b4
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = "7f4a2d1c9e11"
down_revision = "1d5d0d42e5b4"
branch_labels = None
depends_on = None


def _columns(table):
    return {column["name"] for column in inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    participant_columns = _columns("participants")
    if "amount_paise" not in participant_columns:
        op.add_column("participants", sa.Column("amount_paise", sa.Integer(), nullable=True))
    if "payment_token_hash" not in participant_columns:
        op.add_column("participants", sa.Column("payment_token_hash", sa.String(), nullable=True))
    if "amount" in participant_columns:
        bind.execute(text("UPDATE participants SET amount_paise = CAST(ROUND(amount * 100) AS INTEGER) WHERE amount_paise IS NULL"))

    attempt_columns = _columns("payment_attempts")
    if "amount_paise" not in attempt_columns:
        op.add_column("payment_attempts", sa.Column("amount_paise", sa.Integer(), nullable=True))
        if "amount" in attempt_columns:
            bind.execute(text("UPDATE payment_attempts SET amount_paise = amount * 100 WHERE amount_paise IS NULL"))

    op.create_index("ix_participants_payment_token_hash", "participants", ["payment_token_hash"], unique=True)
    op.create_index("ix_participants_email_workshop_unique", "participants", [sa.text("LOWER(email)"), "workshop"], unique=True)
    op.create_index("ix_participants_whatsapp_workshop_unique", "participants", [sa.text("LOWER(whatsapp)"), "workshop"], unique=True)

    op.create_table(
        "seat_counters",
        sa.Column("workshop", sa.String(), primary_key=True),
        sa.Column("max_seats", sa.Integer(), nullable=False),
        sa.Column("allocated_seats", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "webhook_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider_event_id", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("participant_id", sa.Integer(), sa.ForeignKey("participants.id"), nullable=True),
        sa.Column("payment_attempt_id", sa.Integer(), sa.ForeignKey("payment_attempts.id"), nullable=True),
    )
    op.create_index("ix_webhook_events_provider_event_id", "webhook_events", ["provider_event_id"], unique=True)
    op.create_table(
        "notification_outbox",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("participant_id", sa.Integer(), sa.ForeignKey("participants.id"), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("status", sa.Enum("PENDING", "PROCESSING", "SENT", "FAILED", name="notificationstatus"), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_notification_outbox_idempotency_key", "notification_outbox", ["idempotency_key"], unique=True)
    op.create_index("ix_notification_outbox_participant_id", "notification_outbox", ["participant_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_notification_outbox_participant_id", table_name="notification_outbox")
    op.drop_index("ix_notification_outbox_idempotency_key", table_name="notification_outbox")
    op.drop_table("notification_outbox")
    op.drop_index("ix_webhook_events_provider_event_id", table_name="webhook_events")
    op.drop_table("webhook_events")
    op.drop_table("seat_counters")
    op.drop_index("ix_participants_whatsapp_workshop_unique", table_name="participants")
    op.drop_index("ix_participants_email_workshop_unique", table_name="participants")
    op.drop_index("ix_participants_payment_token_hash", table_name="participants")
    op.drop_column("payment_attempts", "amount_paise")
    op.drop_column("participants", "payment_token_hash")
    op.drop_column("participants", "amount_paise")
