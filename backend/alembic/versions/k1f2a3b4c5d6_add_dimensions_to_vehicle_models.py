"""add dimensions and tires to vehicle_models

Revision ID: k1f2a3b4c5d6
Revises: j0e1f2a3b4c5
Create Date: 2026-04-18

Agrega campos informativos de dimensiones, tanque, compresión y llantas
al catálogo de modelos. Todos opcionales, sin impacto en procesos existentes.
"""
from alembic import op
import sqlalchemy as sa

revision = 'k1f2a3b4c5d6'
down_revision = 'j0e1f2a3b4c5'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('vehicle_models', sa.Column('largo_total', sa.String(50), nullable=True))
    op.add_column('vehicle_models', sa.Column('ancho_total', sa.String(50), nullable=True))
    op.add_column('vehicle_models', sa.Column('altura_total', sa.String(50), nullable=True))
    op.add_column('vehicle_models', sa.Column('altura_silla', sa.String(50), nullable=True))
    op.add_column('vehicle_models', sa.Column('distancia_suelo', sa.String(50), nullable=True))
    op.add_column('vehicle_models', sa.Column('distancia_ejes', sa.String(50), nullable=True))
    op.add_column('vehicle_models', sa.Column('tanque_combustible', sa.String(50), nullable=True))
    op.add_column('vehicle_models', sa.Column('relacion_compresion', sa.String(50), nullable=True))
    op.add_column('vehicle_models', sa.Column('llanta_delantera', sa.String(100), nullable=True))
    op.add_column('vehicle_models', sa.Column('llanta_trasera', sa.String(100), nullable=True))


def downgrade():
    op.drop_column('vehicle_models', 'llanta_trasera')
    op.drop_column('vehicle_models', 'llanta_delantera')
    op.drop_column('vehicle_models', 'relacion_compresion')
    op.drop_column('vehicle_models', 'tanque_combustible')
    op.drop_column('vehicle_models', 'distancia_ejes')
    op.drop_column('vehicle_models', 'distancia_suelo')
    op.drop_column('vehicle_models', 'altura_silla')
    op.drop_column('vehicle_models', 'altura_total')
    op.drop_column('vehicle_models', 'ancho_total')
    op.drop_column('vehicle_models', 'largo_total')
