"""add accessories to service_order_receptions

Revision ID: u4v5w6x7y8z9
Revises: t3q4r5s6t7u8
Create Date: 2026-04-25

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'u4v5w6x7y8z9'
down_revision = 't3q4r5s6t7u8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'service_order_receptions',
        sa.Column('accessories', JSONB, nullable=True, server_default='[]')
    )


def downgrade():
    op.drop_column('service_order_receptions', 'accessories')
