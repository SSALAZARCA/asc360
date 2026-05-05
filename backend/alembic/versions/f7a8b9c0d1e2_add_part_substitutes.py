"""add part_substitutes table

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-05-05
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = 'f7a8b9c0d1e2'
down_revision = 'e6f7a8b9c0d1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'part_substitutes',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('factory_part_number', sa.String(100), nullable=False),
        sa.Column('substitute_part_code', sa.String(100), nullable=False),
        sa.Column('brand', sa.String(100), nullable=False),
        sa.Column('model', sa.String(255), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['factory_part_number'], ['parts_references.factory_part_number'], ondelete='CASCADE'),
        sa.UniqueConstraint('factory_part_number', 'position', name='uq_part_substitute_position'),
    )
    op.create_index('ix_part_substitutes_fpn', 'part_substitutes', ['factory_part_number'])


def downgrade() -> None:
    op.drop_index('ix_part_substitutes_fpn', table_name='part_substitutes')
    op.drop_table('part_substitutes')
