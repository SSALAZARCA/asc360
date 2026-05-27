"""add needs_price_review flag to parts_references

Revision ID: bb3c4d5e6f7a
Revises: aa2b3c4d5e6f
Create Date: 2026-05-27
"""
from alembic import op
import sqlalchemy as sa

revision = 'bb3c4d5e6f7a'
down_revision = 'aa2b3c4d5e6f'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'parts_references',
        sa.Column('needs_price_review', sa.Boolean(), nullable=False, server_default='false'),
    )


def downgrade():
    op.drop_column('parts_references', 'needs_price_review')
