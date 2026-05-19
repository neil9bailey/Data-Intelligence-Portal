from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlmodel import SQLModel

from app import models  # noqa: F401


revision = "20260519_0003"
down_revision = "20260519_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    SQLModel.metadata.create_all(bind=op.get_bind())
    inspector = sa.inspect(bind)
    document_columns = {column["name"] for column in inspector.get_columns("opportunitydocument")}
    for column in [
        sa.Column("storage_provider", sa.String(), server_default="none"),
        sa.Column("document_storage_ref", sa.String(), server_default=""),
        sa.Column("classification_label", sa.String(), server_default=""),
        sa.Column("retention_status", sa.String(), server_default="standard"),
        sa.Column("reviewed_by", sa.String(), server_default=""),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("source_access_notes", sa.String(), server_default=""),
    ]:
        if column.name not in document_columns:
            op.add_column("opportunitydocument", column)
    finding_columns = {column["name"] for column in inspector.get_columns("krafinding")}
    for column in [
        sa.Column("provider", sa.String(), server_default=""),
        sa.Column("model", sa.String(), server_default=""),
        sa.Column("prompt_version", sa.String(), server_default=""),
        sa.Column("system_prompt_hash", sa.String(), server_default=""),
        sa.Column("user_prompt_hash", sa.String(), server_default=""),
        sa.Column("source_context_hash", sa.String(), server_default=""),
        sa.Column("output_hash", sa.String(), server_default=""),
        sa.Column("reviewed_by", sa.String(), server_default=""),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
    ]:
        if column.name not in finding_columns:
            op.add_column("krafinding", column)


def downgrade() -> None:
    op.drop_table("digestprofile")
