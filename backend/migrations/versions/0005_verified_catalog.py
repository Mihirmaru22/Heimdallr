"""persistent organization catalog with claim level provenance and review states

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-05 10:00:00
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def _tenant(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""CREATE POLICY tenant_isolation ON {table}
            USING (current_setting('app.bypass_rls', true) = 'on'
                   OR org_id::text = current_setting('app.org_id', true))
            WITH CHECK (current_setting('app.bypass_rls', true) = 'on'
                   OR org_id::text = current_setting('app.org_id', true))"""
    )


def upgrade() -> None:
    op.create_table(
        "catalog_companies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("identity_key", sa.String(length=512), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("website", sa.Text(), nullable=False),
        sa.Column("domain", sa.String(length=300), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "identity_key"),
    )
    op.create_index("ix_catalog_companies_org_id", "catalog_companies", ["org_id"])
    _tenant("catalog_companies")

    op.create_table(
        "catalog_claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_key", sa.String(length=64), nullable=False),
        sa.Column("field_key", sa.String(length=120), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("display_value", sa.Text(), nullable=False),
        sa.Column("verification_status", sa.String(length=20), nullable=False),
        sa.Column("verification_method", sa.String(length=40), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(length=100), nullable=False),
        sa.Column("source_date", sa.String(length=10), nullable=False),
        sa.Column("relationship", sa.String(length=40), nullable=False),
        sa.Column("source_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_evidence_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("verified_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["catalog_companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_job_id"], ["crawl_jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_evidence_id"], ["evidence.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["verified_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "claim_key"),
    )
    op.create_index("ix_catalog_claims_org_id", "catalog_claims", ["org_id"])
    op.create_index("ix_catalog_claims_company_id", "catalog_claims", ["company_id"])
    op.create_index("ix_catalog_claims_company_status", "catalog_claims", ["company_id", "verification_status"])
    op.create_index("ix_catalog_claims_org_field", "catalog_claims", ["org_id", "field_key"])
    _tenant("catalog_claims")


def downgrade() -> None:
    op.drop_table("catalog_claims")
    op.drop_table("catalog_companies")
