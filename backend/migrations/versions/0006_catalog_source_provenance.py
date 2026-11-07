"""retain normalized and original catalog values plus source metadata

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-05
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("catalog_claims", sa.Column(
        "raw_value", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("catalog_claims", sa.Column(
        "source_origin", sa.String(length=300), nullable=False, server_default=""))
    op.add_column("catalog_claims", sa.Column(
        "source_group", sa.String(length=300), nullable=False, server_default=""))
    op.add_column("catalog_claims", sa.Column(
        "source_record_id", sa.String(length=300), nullable=False, server_default=""))
    op.add_column("catalog_claims", sa.Column(
        "source_license", sa.Text(), nullable=False, server_default=""))
    op.add_column("catalog_claims", sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("catalog_claims", "retrieved_at")
    op.drop_column("catalog_claims", "source_license")
    op.drop_column("catalog_claims", "source_record_id")
    op.drop_column("catalog_claims", "source_group")
    op.drop_column("catalog_claims", "source_origin")
    op.drop_column("catalog_claims", "raw_value")
