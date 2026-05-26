"""add rotation_class to parts_references

Revision ID: aa2b3c4d5e6f
Revises: z9a0b1c2d3e4, h9c0d1e2f3g4
Create Date: 2026-05-26
"""
from alembic import op
import sqlalchemy as sa

revision = 'aa2b3c4d5e6f'
down_revision = ('z9a0b1c2d3e4', 'h9c0d1e2f3g4')
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'parts_references',
        sa.Column('rotation_class', sa.String(10), nullable=True),
    )
    op.create_index(
        'ix_parts_references_rotation_class',
        'parts_references',
        ['rotation_class'],
    )


def downgrade():
    op.drop_index('ix_parts_references_rotation_class', table_name='parts_references')
    op.drop_column('parts_references', 'rotation_class')
