"""evidence: proof that a company uses a technology (and the pages rejected as proof)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-21 13:00:00
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('evidence',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('org_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('job_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('company', sa.String(length=300), nullable=False),
        sa.Column('website', sa.Text(), nullable=False),
        sa.Column('product', sa.String(length=200), nullable=False),
        sa.Column('quote', sa.Text(), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('evidence_date', sa.String(length=10), nullable=False),
        sa.Column('source_type', sa.String(length=60), nullable=False),
        sa.Column('relationship', sa.String(length=40), nullable=False),
        sa.Column('judged_by', sa.String(length=120), nullable=False),
        sa.Column('strength', sa.Float(), nullable=False),
        sa.Column('verdict', sa.String(length=20), nullable=False),
        sa.Column('kept', sa.Boolean(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['job_id'], ['crawl_jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_evidence_org_id', 'evidence', ['org_id'])
    op.create_index('ix_evidence_job_id', 'evidence', ['job_id'])
    # The same tenant isolation as the other tenant tables (see 0001).
    op.execute("ALTER TABLE evidence ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE evidence FORCE ROW LEVEL SECURITY")
    op.execute(
        """CREATE POLICY tenant_isolation ON evidence
            USING (current_setting('app.bypass_rls', true) = 'on'
                   OR org_id::text = current_setting('app.org_id', true))
            WITH CHECK (current_setting('app.bypass_rls', true) = 'on'
                   OR org_id::text = current_setting('app.org_id', true))"""
    )


def downgrade() -> None:
    op.drop_table('evidence')
