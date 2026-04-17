"""add empadronamiento columns and vehicle_models table

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-04-10

Agrega 6 columnas de empadronamiento a shipment_moto_units y crea
la tabla vehicle_models con las especificaciones técnicas por modelo.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    # ------------------------------------------------------------------ #
    # shipment_moto_units — columnas de empadronamiento
    # ------------------------------------------------------------------ #
    op.add_column('shipment_moto_units', sa.Column('no_acep', sa.String(100), nullable=True))
    op.add_column('shipment_moto_units', sa.Column('f_acep', sa.Date(), nullable=True))
    op.add_column('shipment_moto_units', sa.Column('no_lev', sa.String(100), nullable=True))
    op.add_column('shipment_moto_units', sa.Column('f_lev', sa.Date(), nullable=True))
    op.add_column('shipment_moto_units', sa.Column('certificado_generado', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('shipment_moto_units', sa.Column('certificado_fecha', sa.DateTime(), nullable=True))

    # ------------------------------------------------------------------ #
    # vehicle_models
    # ------------------------------------------------------------------ #
    op.create_table(
        'vehicle_models',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('model_name', sa.String(255), nullable=False, unique=True),
        sa.Column('brand', sa.String(100), nullable=True, server_default='UM'),
        sa.Column('cilindrada', sa.String(100), nullable=True),
        sa.Column('potencia', sa.String(100), nullable=True),
        sa.Column('peso', sa.String(100), nullable=True),
        sa.Column('vueltas_aire', sa.String(100), nullable=True),
        sa.Column('posicion_cortina', sa.String(100), nullable=True),
        sa.Column('sistemas_control', sa.String(500), nullable=True),
        sa.Column('fuel_system', sa.String(50), nullable=True, server_default='CARBURADOR'),
        sa.Column('model_year', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_vehicle_models_model_name', 'vehicle_models', ['model_name'])
    op.create_index('ix_vehicle_models_brand', 'vehicle_models', ['brand'])


def downgrade():
    op.drop_index('ix_vehicle_models_brand', table_name='vehicle_models')
    op.drop_index('ix_vehicle_models_model_name', table_name='vehicle_models')
    op.drop_table('vehicle_models')

    op.drop_column('shipment_moto_units', 'certificado_fecha')
    op.drop_column('shipment_moto_units', 'certificado_generado')
    op.drop_column('shipment_moto_units', 'f_lev')
    op.drop_column('shipment_moto_units', 'no_lev')
    op.drop_column('shipment_moto_units', 'f_acep')
    op.drop_column('shipment_moto_units', 'no_acep')
