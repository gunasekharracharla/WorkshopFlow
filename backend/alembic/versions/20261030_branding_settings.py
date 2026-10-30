"""Persist editable white-label settings for each installation.

Revision ID: 6b9f1e4a2c83
Revises: 5e1c8b7a3d24
"""

import json
import os
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "6b9f1e4a2c83"
down_revision = "5e1c8b7a3d24"
branch_labels = None
depends_on = None


def _env(name: str, default: str) -> str:
    return os.getenv(name, default).strip()


def upgrade() -> None:
    op.create_table(
        "branding_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("brand_name", sa.String(length=80), nullable=False),
        sa.Column("brand_mark", sa.String(length=5), nullable=False),
        sa.Column("brand_accent_color", sa.String(length=7), nullable=False),
        sa.Column("instructor_name", sa.String(length=120), nullable=False),
        sa.Column("instructor_title", sa.String(length=120), nullable=False),
        sa.Column("instructor_bio", sa.Text(), nullable=False),
        sa.Column("instructor_email", sa.String(length=254), nullable=False),
        sa.Column("registration_roles", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(), nullable=True),
    )
    op.bulk_insert(
        sa.table(
            "branding_settings",
            sa.column("id", sa.Integer()),
            sa.column("brand_name", sa.String()),
            sa.column("brand_mark", sa.String()),
            sa.column("brand_accent_color", sa.String()),
            sa.column("instructor_name", sa.String()),
            sa.column("instructor_title", sa.String()),
            sa.column("instructor_bio", sa.Text()),
            sa.column("instructor_email", sa.String()),
            sa.column("registration_roles", sa.Text()),
            sa.column("updated_at", sa.DateTime()),
            sa.column("updated_by", sa.String()),
        ),
        [
            {
                "id": 1,
                "brand_name": _env("BRAND_NAME", "BUILD THE WEB"),
                "brand_mark": _env("BRAND_MARK", "BW"),
                "brand_accent_color": _env("BRAND_ACCENT_COLOR", "#6b5bdd").strip('"'),
                "instructor_name": _env("INSTRUCTOR_NAME", "Your Name"),
                "instructor_title": _env("INSTRUCTOR_TITLE", "Full-Stack Developer"),
                "instructor_bio": _env(
                    "INSTRUCTOR_BIO",
                    "I build useful web products across frontend interfaces, backend application logic, and the data that connects them.",
                ),
                "instructor_email": _env("INSTRUCTOR_EMAIL", "your.email@example.com"),
                "registration_roles": json.dumps(
                    [
                        role.strip()
                        for role in _env(
                            "REGISTRATION_ROLES",
                            "Full-Stack Developer,Frontend Developer,Backend Developer,Web Designer,Student/Fresher,Other",
                        ).split(",")
                        if role.strip()
                    ]
                ),
                "updated_at": datetime.now(timezone.utc),
                "updated_by": "migration",
            }
        ],
    )


def downgrade() -> None:
    op.drop_table("branding_settings")
