"""sec_companies: shared copy of SEC EDGAR's listed companies

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-20 08:40:00
"""
import sqlalchemy as sa
from alembic import op

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('sec_companies',
        sa.Column('cik', sa.Integer(), autoincrement=False, nullable=False),
        sa.Column('name', sa.String(length=300), nullable=False),
        sa.Column('ticker', sa.String(length=20), nullable=False),
        sa.Column('exchange', sa.String(length=40), nullable=False),
        sa.Column('rank', sa.Integer(), nullable=False),
        sa.Column('sic', sa.String(length=4), nullable=True),
        sa.Column('sic_description', sa.String(length=200), nullable=False),
        sa.Column('city', sa.String(length=120), nullable=False),
        sa.Column('state', sa.String(length=60), nullable=False),
        sa.Column('foreign', sa.Boolean(), nullable=False),
        sa.Column('website', sa.String(length=500), nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('cik'),
    )
    op.create_index('ix_sec_companies_rank', 'sec_companies', ['rank'])
    op.create_index('ix_sec_companies_sic', 'sec_companies', ['sic'])


def downgrade() -> None:
    op.drop_table('sec_companies')
