"""Rename the original branded workshop for the owner's project.

Revision ID: 5e1c8b7a3d24
Revises: 8c7d4e2f1a90
"""

from alembic import op
from sqlalchemy import text


revision = "5e1c8b7a3d24"
down_revision = "8c7d4e2f1a90"
branch_labels = None
depends_on = None

LEGACY_NAME = "MNRATHI AI Power Hour"
WORKSHOP_NAME = "Full-Stack Web Development Workshop"
WORKSHOP_SLUG = "full-stack-web-development"


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        text(
            "UPDATE participants SET workshop = :new_name "
            "WHERE workshop = :old_name"
        ),
        {"new_name": WORKSHOP_NAME, "old_name": LEGACY_NAME},
    )
    bind.execute(
        text(
            "UPDATE seat_counters SET workshop = :new_name "
            "WHERE workshop = :old_name"
        ),
        {"new_name": WORKSHOP_NAME, "old_name": LEGACY_NAME},
    )
    bind.execute(
        text(
            "UPDATE workshops SET workshop_name = :new_name, slug = :new_slug, "
            "description = :description, updated_at = CURRENT_TIMESTAMP, "
            "updated_by = 'migration' WHERE workshop_name = :old_name"
        ),
        {
            "new_name": WORKSHOP_NAME,
            "new_slug": WORKSHOP_SLUG,
            "description": "A practical, hands-on full-stack web development workshop.",
            "old_name": LEGACY_NAME,
        },
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        text(
            "UPDATE participants SET workshop = :old_name "
            "WHERE workshop = :new_name"
        ),
        {"new_name": WORKSHOP_NAME, "old_name": LEGACY_NAME},
    )
    bind.execute(
        text(
            "UPDATE seat_counters SET workshop = :old_name "
            "WHERE workshop = :new_name"
        ),
        {"new_name": WORKSHOP_NAME, "old_name": LEGACY_NAME},
    )
    bind.execute(
        text(
            "UPDATE workshops SET workshop_name = :old_name, slug = 'ai-power-hour', "
            "description = 'MNRATHI AI Power Hour workshop', updated_at = CURRENT_TIMESTAMP, "
            "updated_by = 'migration' WHERE workshop_name = :new_name"
        ),
        {"new_name": WORKSHOP_NAME, "old_name": LEGACY_NAME},
    )
