from __future__ import annotations

from alembic import op
from sqlmodel import SQLModel

from app import models  # noqa: F401


revision = "20260519_0002"
down_revision = "20260519_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    SQLModel.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    op.drop_table("opportunityfeedback")
    op.drop_table("opportunitymatchevidence")
