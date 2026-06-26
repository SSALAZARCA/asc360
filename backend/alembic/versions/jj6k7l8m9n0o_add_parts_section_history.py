"""add parts_manual_section_history for audit trail

Revision ID: jj6k7l8m9n0o
Revises: ii5j6k7l8m9n
Create Date: 2026-06-26 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = 'jj6k7l8m9n0o'
down_revision = 'ii5j6k7l8m9n'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'parts_manual_section_history',
        sa.Column('id',           UUID(as_uuid=True), primary_key=True),
        sa.Column('model_code',   sa.String(100), nullable=False),
        sa.Column('section_code', sa.String(20),  nullable=False),
        sa.Column('section_name', sa.String(255), nullable=False),
        sa.Column('diagram_url',  sa.String(500), nullable=True),
        sa.Column('parts_count',  sa.Integer,     nullable=False),
        sa.Column('snapshot',     JSONB(),         nullable=False, server_default='[]'),
        sa.Column('replaced_at',  sa.DateTime,    nullable=False),
        sa.Column('replaced_by',  UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        'ix_pms_history_model_code',
        'parts_manual_section_history',
        ['model_code'],
    )


def downgrade():
    op.drop_index('ix_pms_history_model_code', table_name='parts_manual_section_history')
    op.drop_table('parts_manual_section_history')
