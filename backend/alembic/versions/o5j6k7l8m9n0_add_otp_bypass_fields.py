"""add otp bypass fields

Revision ID: o5j6k7l8m9n0
Revises: n4i5j6k7l8m9
Branch Labels: None
Depends On: None
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'o5j6k7l8m9n0'
down_revision = 'n4i5j6k7l8m9'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('service_order_receptions',
        sa.Column('bypass_at', sa.DateTime(), nullable=True))
    op.add_column('service_order_receptions',
        sa.Column('bypass_by_id', UUID(as_uuid=True), nullable=True))
    op.add_column('service_order_receptions',
        sa.Column('bypass_by_name', sa.String(length=200), nullable=True))


def downgrade():
    op.drop_column('service_order_receptions', 'bypass_by_name')
    op.drop_column('service_order_receptions', 'bypass_by_id')
    op.drop_column('service_order_receptions', 'bypass_at')
