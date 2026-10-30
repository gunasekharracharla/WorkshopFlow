"""Initial workshop schema

Revision ID: 1d5d0d42e5b4
Revises:
Create Date: 2026-09-22 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "1d5d0d42e5b4"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "participants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("whatsapp", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("experience", sa.String(), nullable=True),
        sa.Column("workshop", sa.String(), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("payment_status", sa.Enum("PENDING", "SUCCESS", "FAILED", name="paymentstatus"), nullable=False),
        sa.Column("razorpay_order_id", sa.String(), nullable=True),
        sa.Column("razorpay_payment_id", sa.String(), nullable=True),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payment_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_participants_id"), "participants", ["id"], unique=False)
    op.create_index(op.f("ix_participants_email"), "participants", ["email"], unique=False)
    op.create_index(op.f("ix_participants_razorpay_order_id"), "participants", ["razorpay_order_id"], unique=False)
    op.create_index("ix_participant_email_workshop", "participants", ["email", "workshop"], unique=False)
    op.create_index("ix_participants_payment_id", "participants", ["razorpay_payment_id"], unique=False)
    op.create_index("ix_participants_order_id", "participants", ["razorpay_order_id"], unique=False)

    op.create_table(
        "payment_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("participant_id", sa.Integer(), nullable=False),
        sa.Column("razorpay_order_id", sa.String(), nullable=False),
        sa.Column("razorpay_payment_id", sa.String(), nullable=True),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("status", sa.Enum("PENDING", "SUCCESS", "FAILED", name="paymentstatus"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["participant_id"], ["participants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_payment_attempts_id"), "payment_attempts", ["id"], unique=False)
    op.create_index(op.f("ix_payment_attempts_participant_id"), "payment_attempts", ["participant_id"], unique=False)
    op.create_index(op.f("ix_payment_attempts_razorpay_order_id"), "payment_attempts", ["razorpay_order_id"], unique=True)
    op.create_index(op.f("ix_payment_attempts_razorpay_payment_id"), "payment_attempts", ["razorpay_payment_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_payment_attempts_razorpay_payment_id"), table_name="payment_attempts")
    op.drop_index(op.f("ix_payment_attempts_razorpay_order_id"), table_name="payment_attempts")
    op.drop_index(op.f("ix_payment_attempts_participant_id"), table_name="payment_attempts")
    op.drop_index(op.f("ix_payment_attempts_id"), table_name="payment_attempts")
    op.drop_table("payment_attempts")
    op.drop_index("ix_participants_order_id", table_name="participants")
    op.drop_index("ix_participants_payment_id", table_name="participants")
    op.drop_index("ix_participant_email_workshop", table_name="participants")
    op.drop_index(op.f("ix_participants_razorpay_order_id"), table_name="participants")
    op.drop_index(op.f("ix_participants_email"), table_name="participants")
    op.drop_index(op.f("ix_participants_id"), table_name="participants")
    op.drop_table("participants")
