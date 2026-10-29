"""company records: facts sources establish about companies, and one decision per company

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-29 10:00:00
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def _tenant(table: str) -> None:
    # The same tenant isolation as the other tenant tables (see 0001).
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
    op.create_table('company_facts',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('org_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('job_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('site', sa.String(length=300), nullable=False),
        sa.Column('company', sa.String(length=300), nullable=False),
        sa.Column('kind', sa.String(length=40), nullable=False),
        sa.Column('value', sa.String(length=300), nullable=False),
        sa.Column('by', sa.String(length=120), nullable=False),
        sa.Column('detail', sa.Text(), nullable=False),
        sa.Column('source_url', sa.Text(), nullable=False),
        sa.Column('quote', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['job_id'], ['crawl_jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_company_facts_org_id', 'company_facts', ['org_id'])
    op.create_index('ix_company_facts_job_id', 'company_facts', ['job_id'])
    _tenant('company_facts')
    op.create_table('job_companies',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('org_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('job_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('key', sa.String(length=320), nullable=False),
        sa.Column('name', sa.String(length=300), nullable=False),
        sa.Column('website', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=40), nullable=False),
        sa.Column('reasons', postgresql.JSONB(), nullable=False),
        sa.Column('proof_verdict', sa.String(length=20), nullable=False),
        sa.Column('proof_url', sa.Text(), nullable=False),
        sa.Column('proof_quote', sa.Text(), nullable=False),
        sa.Column('country', sa.String(length=8), nullable=False),
        sa.Column('country_by', sa.Text(), nullable=False),
        sa.Column('sources', postgresql.JSONB(), nullable=False),
        sa.Column('record_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['job_id'], ['crawl_jobs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['record_id'], ['extracted_records.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_id', 'key'),
    )
    op.create_index('ix_job_companies_org_id', 'job_companies', ['org_id'])
    op.create_index('ix_job_companies_job_id', 'job_companies', ['job_id'])
    _tenant('job_companies')


def downgrade() -> None:
    op.drop_table('job_companies')
    op.drop_table('company_facts')
