"""traslado_linea + traslado_confirmacion (+ historial): pending store transfers

Revision ID: b2f6d9a4c718
Revises: a8d4f1c6b923
Create Date: 2026-10-09 20:00:00.000000

odd/tasks/motored-traslados-pendientes.md, T1. `traslado_linea` holds the
lines of every applied TRASLADOS load (a full snapshot per load). The
`carga_archivo.tipo` column is a varchar, so the new type needs no enum
change. `traslado_confirmacion` is the one shared state per transfer
(`nro_documento`, `bodega_salida`), plus an append-only history. Purely
additive; downgrade drops the three tables.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b2f6d9a4c718'
down_revision: Union[str, None] = 'a8d4f1c6b923'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ESTADO = "estado IN ('RECIBIDO', 'NO_HA_LLEGADO')"


def _crear_lineas() -> None:
    op.create_table(
        'traslado_linea',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('carga_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('nro_documento', sa.String(40), nullable=False),
        sa.Column('fecha', sa.Date(), nullable=False),
        sa.Column('bodega_salida', sa.String(20), nullable=False),
        sa.Column('descripcion_bodega_salida', sa.String(120), nullable=True),
        sa.Column('sucursal_salida_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('bodega_entrada', sa.String(20), nullable=False),
        sa.Column('sucursal_entrada_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('referencia_codigo', sa.String(60), nullable=False),
        sa.Column('referencia_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('descripcion', sa.String(200), nullable=True),
        sa.Column('unidad', sa.String(20), nullable=True),
        sa.Column('cantidad', sa.Numeric(14, 2), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['carga_id'], ['carga_archivo.id']),
        sa.ForeignKeyConstraint(['sucursal_salida_id'], ['sucursal.id']),
        sa.ForeignKeyConstraint(['sucursal_entrada_id'], ['sucursal.id']),
        sa.ForeignKeyConstraint(['referencia_id'], ['referencia.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_traslado_linea_carga_id', 'traslado_linea', ['carga_id'])
    op.create_index(
        'ix_traslado_linea_sucursal_entrada_id', 'traslado_linea',
        ['sucursal_entrada_id'])
    op.create_index(
        'ix_traslado_linea_documento_bodega', 'traslado_linea',
        ['nro_documento', 'bodega_salida'])


def _crear_confirmaciones() -> None:
    op.create_table(
        'traslado_confirmacion',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('nro_documento', sa.String(40), nullable=False),
        sa.Column('bodega_salida', sa.String(20), nullable=False),
        sa.Column('estado', sa.String(16), nullable=False),
        sa.Column('actualizado_por_usuario_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('actualizado_por_nombre', sa.String(200), nullable=False),
        sa.Column('actualizado_por_cedula', sa.String(20), nullable=True),
        sa.Column('actualizado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(_ESTADO, name='ck_traslado_confirmacion_estado'),
        sa.ForeignKeyConstraint(['actualizado_por_usuario_id'], ['usuario.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('nro_documento', 'bodega_salida', name='uq_traslado_confirmacion_documento_bodega'),
    )
    op.create_table(
        'traslado_confirmacion_historial',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('nro_documento', sa.String(40), nullable=False),
        sa.Column('bodega_salida', sa.String(20), nullable=False),
        sa.Column('estado', sa.String(16), nullable=False),
        sa.Column('por_usuario_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('por_nombre', sa.String(200), nullable=False),
        sa.Column('por_cedula', sa.String(20), nullable=True),
        sa.Column('canal', sa.String(8), nullable=False),
        sa.Column('creado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(_ESTADO, name='ck_traslado_confirmacion_historial_estado'),
        sa.CheckConstraint("canal IN ('web', 'link')", name='ck_traslado_confirmacion_historial_canal'),
        sa.ForeignKeyConstraint(['por_usuario_id'], ['usuario.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_traslado_confirmacion_historial_doc',
        'traslado_confirmacion_historial', ['nro_documento', 'bodega_salida'])


def upgrade() -> None:
    _crear_lineas()
    _crear_confirmaciones()


def downgrade() -> None:
    op.drop_index(
        'ix_traslado_confirmacion_historial_doc',
        table_name='traslado_confirmacion_historial')
    op.drop_table('traslado_confirmacion_historial')
    op.drop_table('traslado_confirmacion')
    op.drop_index('ix_traslado_linea_documento_bodega', table_name='traslado_linea')
    op.drop_index('ix_traslado_linea_sucursal_entrada_id', table_name='traslado_linea')
    op.drop_index('ix_traslado_linea_carga_id', table_name='traslado_linea')
    op.drop_table('traslado_linea')
