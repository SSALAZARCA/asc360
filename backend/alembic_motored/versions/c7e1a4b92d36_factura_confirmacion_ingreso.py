"""factura_confirmacion_ingreso: asesor confirmations of pending invoice ingresos

Revision ID: c7e1a4b92d36
Revises: b5d9e3a7c142
Create Date: 2026-10-08 18:00:00.000000

odd/tasks/motored-ingresos-pendientes.md, P1. One shared state per invoice
document and principal store, plus an append-only history. Purely additive;
downgrade drops both tables.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c7e1a4b92d36'
down_revision: Union[str, None] = 'b5d9e3a7c142'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'factura_confirmacion_ingreso',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('prefijo_rh', sa.String(2), nullable=False),
        sa.Column('numero_rh', sa.BigInteger(), nullable=False),
        sa.Column('sucursal_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('estado', sa.String(16), nullable=False),
        sa.Column('actualizado_por_usuario_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('actualizado_por_nombre', sa.String(200), nullable=False),
        sa.Column('actualizado_por_cedula', sa.String(20), nullable=True),
        sa.Column('actualizado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("estado IN ('LLEGO', 'NO_HA_LLEGADO')", name='ck_factura_confirmacion_ingreso_estado'),
        sa.ForeignKeyConstraint(['sucursal_id'], ['sucursal.id']),
        sa.ForeignKeyConstraint(['actualizado_por_usuario_id'], ['usuario.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('prefijo_rh', 'numero_rh', 'sucursal_id', name='uq_factura_confirmacion_ingreso_doc_sucursal'),
    )
    op.create_table(
        'factura_confirmacion_ingreso_historial',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('prefijo_rh', sa.String(2), nullable=False),
        sa.Column('numero_rh', sa.BigInteger(), nullable=False),
        sa.Column('sucursal_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('estado', sa.String(16), nullable=False),
        sa.Column('por_usuario_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('por_nombre', sa.String(200), nullable=False),
        sa.Column('por_cedula', sa.String(20), nullable=True),
        sa.Column('canal', sa.String(8), nullable=False),
        sa.Column('creado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("estado IN ('LLEGO', 'NO_HA_LLEGADO')", name='ck_factura_confirmacion_ingreso_historial_estado'),
        sa.CheckConstraint("canal IN ('web', 'link')", name='ck_factura_confirmacion_ingreso_historial_canal'),
        sa.ForeignKeyConstraint(['sucursal_id'], ['sucursal.id']),
        sa.ForeignKeyConstraint(['por_usuario_id'], ['usuario.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_factura_confirmacion_ingreso_historial_doc',
        'factura_confirmacion_ingreso_historial',
        ['prefijo_rh', 'numero_rh', 'sucursal_id'])


def downgrade() -> None:
    op.drop_index(
        'ix_factura_confirmacion_ingreso_historial_doc',
        table_name='factura_confirmacion_ingreso_historial')
    op.drop_table('factura_confirmacion_ingreso_historial')
    op.drop_table('factura_confirmacion_ingreso')
