"""remove model_year from vehicle_models

Revision ID: j0e1f2a3b4c5
Revises: i9d0e1f2a3b4
Create Date: 2026-04-18

El año modelo es un dato por unidad de moto (shipment_moto_units.model_year),
no una especificación del catálogo de modelos.
"""
from alembic import op

revision = 'j0e1f2a3b4c5'
down_revision = 'i9d0e1f2a3b4'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column('vehicle_models', 'model_year')


def downgrade():
    import sqlalchemy as sa
    op.add_column('vehicle_models', sa.Column('model_year', sa.Integer(), nullable=True))
