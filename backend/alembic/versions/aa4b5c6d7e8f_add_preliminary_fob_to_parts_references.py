"""add preliminary_fob to parts_references

Revision ID: aa4b5c6d7e8f
Revises: ff1a2b3c4d5e
Create Date: 2026-06-02
"""
from alembic import op
import sqlalchemy as sa

revision = 'aa4b5c6d7e8f'
down_revision = 'ff1a2b3c4d5e'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('parts_references',
        sa.Column('preliminary_fob', sa.Numeric(12, 4), nullable=True))


def downgrade():
    op.drop_column('parts_references', 'preliminary_fob')
