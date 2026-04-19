"""add otp flow

Revision ID: n4i5j6k7l8m9
Revises: m3h4i5j6k7l8
Branch Labels: None
Depends On: None
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'n4i5j6k7l8m9'
down_revision = 'm3h4i5j6k7l8'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Agregar pending_signature al enum servicestatus
    with op.get_context().autocommit_block():
        op.execute(sa.text("ALTER TYPE servicestatus ADD VALUE IF NOT EXISTS 'pending_signature'"))

    # 2. Agregar columnas de aceptación OTP a service_order_receptions
    op.add_column('service_order_receptions',
        sa.Column('accepted_at', sa.DateTime(), nullable=True))
    op.add_column('service_order_receptions',
        sa.Column('accepted_phone', sa.String(length=20), nullable=True))

    # 3. Crear tabla order_otps
    op.create_table(
        'order_otps',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('order_id', UUID(as_uuid=True),
                  sa.ForeignKey('service_orders.id'), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=False),
        sa.Column('code', sa.String(length=6), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('used_at', sa.DateTime(), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
    )


def downgrade():
    op.drop_table('order_otps')
    op.drop_column('service_order_receptions', 'accepted_phone')
    op.drop_column('service_order_receptions', 'accepted_at')
