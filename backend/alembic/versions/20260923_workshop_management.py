"""Create centralized workshop management and audit history.

Revision ID: 8c7d4e2f1a90
Revises: 7f4a2d1c9e11
"""

import json
import os
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = "8c7d4e2f1a90"
down_revision = "7f4a2d1c9e11"
branch_labels = None
depends_on = None


def _env(name, default=""):
    return os.getenv(name, default).strip()


def _int_env(name, default):
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def upgrade() -> None:
    op.create_table(
        "workshops",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workshop_name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("workshop_date", sa.String(), nullable=False),
        sa.Column("start_time", sa.String(), nullable=False),
        sa.Column("end_time", sa.String(), nullable=False),
        sa.Column("timezone", sa.String(), nullable=False),
        sa.Column("price_paise", sa.Integer(), nullable=False),
        sa.Column("max_seats", sa.Integer(), nullable=False),
        sa.Column("registration_status", sa.Enum("DRAFT", "PUBLISHED", "REGISTRATION_OPEN", "REGISTRATION_CLOSED", "COMPLETED", "CANCELLED", name="registrationstatus"), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("learning_points", sa.Text(), nullable=False),
        sa.Column("meeting_platform", sa.String(), nullable=True),
        sa.Column("meeting_id", sa.String(), nullable=True),
        sa.Column("meeting_url", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_workshops_slug", "workshops", ["slug"], unique=True)
    op.create_table(
        "workshop_audits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workshop_id", sa.Integer(), sa.ForeignKey("workshops.id"), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("changed_by", sa.String(), nullable=False),
        sa.Column("old_values", sa.Text(), nullable=False),
        sa.Column("new_values", sa.Text(), nullable=False),
    )
    op.create_index("ix_workshop_audits_workshop_id", "workshop_audits", ["workshop_id"], unique=False)

    now = datetime.now(timezone.utc)
    op.bulk_insert(sa.table(
        "workshops",
        sa.column("id", sa.Integer()), sa.column("workshop_name", sa.String()), sa.column("slug", sa.String()),
        sa.column("workshop_date", sa.String()), sa.column("start_time", sa.String()), sa.column("end_time", sa.String()),
        sa.column("timezone", sa.String()), sa.column("price_paise", sa.Integer()), sa.column("max_seats", sa.Integer()),
        sa.column("registration_status", sa.String()), sa.column("description", sa.Text()), sa.column("mode", sa.String()),
        sa.column("learning_points", sa.Text()), sa.column("meeting_platform", sa.String()), sa.column("meeting_id", sa.String()),
        sa.column("meeting_url", sa.String()), sa.column("created_at", sa.DateTime()), sa.column("updated_at", sa.DateTime()), sa.column("updated_by", sa.String()),
    ), [{
        "id": 1,
        "workshop_name": _env("WORKSHOP_NAME", "Full-Stack Web Development Workshop"),
        "slug": "full-stack-web-development",
        "workshop_date": _env("WORKSHOP_DATE", "To be announced"),
        "start_time": _env("WORKSHOP_START_TIME", "4:00 PM"),
        "end_time": _env("WORKSHOP_END_TIME", "5:00 PM"),
        "timezone": "Asia/Kolkata",
        "price_paise": _int_env("WORKSHOP_PRICE", 399) * 100,
        "max_seats": _int_env("MAX_SEATS", 100),
        "registration_status": "REGISTRATION_OPEN",
        "description": "A practical, hands-on full-stack web development workshop.",
        "mode": "Online Live Session",
        "learning_points": json.dumps([]),
        "meeting_platform": None,
        "meeting_id": None,
        "meeting_url": _env("MEETING_URL") or None,
        "created_at": now,
        "updated_at": now,
        "updated_by": "migration",
    }])


def downgrade() -> None:
    op.drop_index("ix_workshop_audits_workshop_id", table_name="workshop_audits")
    op.drop_table("workshop_audits")
    op.drop_index("ix_workshops_slug", table_name="workshops")
    op.drop_table("workshops")
