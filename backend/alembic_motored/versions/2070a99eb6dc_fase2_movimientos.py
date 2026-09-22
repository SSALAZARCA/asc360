"""fase2 movimientos

Revision ID: 2070a99eb6dc
Revises: 6d6d2902ce9b
Create Date: 2026-09-21 21:10:00.000000

Phase 3 "Movement Schema + Shared Infra" (sdd/motored-pedidos-ingesta,
Fase 2 "Ingesta"). Creates the 6 movement tables from design §Schema:
`venta_mensual`, `inventario_snapshot`, `backorder_linea`,
`factura_proveedor_linea`, `ingreso_factura`, `demanda_perdida`, plus their
§9.3 indexes. Hand-written (no live Postgres available to autogenerate
against in this batch) mirroring the exact column/index list from the
design doc, and mirroring `fase2_staging`'s one-helper-per-table shape
(gga-driven precedent from that migration) so the review stays scannable
table-by-table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '2070a99eb6dc'
down_revision: Union[str, None] = '6d6d2902ce9b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_venta_mensual() -> None:
    op.create_table(
        'venta_mensual',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('sucursal_id', sa.UUID(), nullable=False),
        sa.Column('referencia_id', sa.UUID(), nullable=False),
        sa.Column('anio', sa.Integer(), nullable=False),
        sa.Column('mes', sa.Integer(), nullable=False),
        sa.Column('origen', sa.String(length=12), nullable=False),
        sa.Column('unidades', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('es_mes_parcial', sa.Boolean(), nullable=False),
        sa.Column('dias_transcurridos', sa.Integer(), nullable=True),
        sa.Column('carga_id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['carga_id'], ['carga_archivo.id']),
        sa.ForeignKeyConstraint(['referencia_id'], ['referencia.id']),
        sa.ForeignKeyConstraint(['sucursal_id'], ['sucursal.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'sucursal_id', 'referencia_id', 'anio', 'mes', 'origen',
            name='uq_venta_mensual_sucursal_referencia_anio_mes_origen',
        ),
    )
    op.create_index(
        'ix_venta_mensual_referencia_id_anio_mes',
        'venta_mensual', ['referencia_id', 'anio', 'mes'], unique=False,
    )


def _create_inventario_snapshot() -> None:
    op.create_table(
        'inventario_snapshot',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('fecha_corte', sa.Date(), nullable=False),
        sa.Column('sucursal_id', sa.UUID(), nullable=False),
        sa.Column('referencia_id', sa.UUID(), nullable=False),
        sa.Column('existencias', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('carga_id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['carga_id'], ['carga_archivo.id']),
        sa.ForeignKeyConstraint(['referencia_id'], ['referencia.id']),
        sa.ForeignKeyConstraint(['sucursal_id'], ['sucursal.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'fecha_corte', 'sucursal_id', 'referencia_id',
            name='uq_inventario_snapshot_fecha_corte_sucursal_referencia',
        ),
    )
    op.create_index(
        'ix_inventario_snapshot_fecha_corte', 'inventario_snapshot', ['fecha_corte'], unique=False,
    )


def _create_backorder_linea() -> None:
    op.create_table(
        'backorder_linea',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('fecha_corte', sa.Date(), nullable=False),
        sa.Column('sucursal_id', sa.UUID(), nullable=False),
        sa.Column('referencia_id', sa.UUID(), nullable=False),
        sa.Column('numero_pedido', sa.String(length=50), nullable=False),
        sa.Column('estado', sa.String(length=32), nullable=False),
        sa.Column('cantidad_pendiente', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('carga_id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['carga_id'], ['carga_archivo.id']),
        sa.ForeignKeyConstraint(['referencia_id'], ['referencia.id']),
        sa.ForeignKeyConstraint(['sucursal_id'], ['sucursal.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'fecha_corte', 'sucursal_id', 'referencia_id', 'numero_pedido',
            name='uq_backorder_linea_fecha_corte_sucursal_referencia_pedido',
        ),
    )


def _create_factura_proveedor_linea() -> None:
    op.create_table(
        'factura_proveedor_linea',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('prefijo_rh', sa.String(length=2), nullable=False),
        sa.Column('numero_rh', sa.BigInteger(), nullable=False),
        sa.Column('fecha_factura', sa.Date(), nullable=False),
        sa.Column('sucursal_id', sa.UUID(), nullable=False),
        sa.Column('referencia_id', sa.UUID(), nullable=False),
        sa.Column('cantidad', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('ingresada', sa.Boolean(), nullable=False),
        sa.Column('transito_vencido', sa.Boolean(), nullable=False),
        sa.Column('ingreso_parcial_sospechoso', sa.Boolean(), nullable=False),
        sa.Column('carga_id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['carga_id'], ['carga_archivo.id']),
        sa.ForeignKeyConstraint(['referencia_id'], ['referencia.id']),
        sa.ForeignKeyConstraint(['sucursal_id'], ['sucursal.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'prefijo_rh', 'numero_rh', 'sucursal_id', 'referencia_id',
            name='uq_factura_proveedor_linea_rh_sucursal_referencia',
        ),
    )
    op.create_index(
        'ix_factura_proveedor_linea_prefijo_rh_numero_rh',
        'factura_proveedor_linea', ['prefijo_rh', 'numero_rh'], unique=False,
    )
    op.create_index(
        'ix_factura_proveedor_linea_ingresada_transito_vencido',
        'factura_proveedor_linea', ['ingresada', 'transito_vencido'], unique=False,
    )


def _create_ingreso_factura() -> None:
    op.create_table(
        'ingreso_factura',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('prefijo_rh', sa.String(length=2), nullable=False),
        sa.Column('numero_rh', sa.BigInteger(), nullable=False),
        sa.Column('fecha_ingreso', sa.Date(), nullable=False),
        sa.Column('sucursal_id', sa.UUID(), nullable=False),
        sa.Column('referencia_id', sa.UUID(), nullable=False),
        sa.Column('cantidad', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('carga_id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['carga_id'], ['carga_archivo.id']),
        sa.ForeignKeyConstraint(['referencia_id'], ['referencia.id']),
        sa.ForeignKeyConstraint(['sucursal_id'], ['sucursal.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'prefijo_rh', 'numero_rh', 'sucursal_id', 'referencia_id',
            name='uq_ingreso_factura_rh_sucursal_referencia',
        ),
    )
    op.create_index(
        'ix_ingreso_factura_prefijo_rh_numero_rh',
        'ingreso_factura', ['prefijo_rh', 'numero_rh'], unique=False,
    )


def _create_demanda_perdida() -> None:
    op.create_table(
        'demanda_perdida',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('fecha', sa.Date(), nullable=False),
        sa.Column('sucursal_id', sa.UUID(), nullable=False),
        sa.Column('referencia_id', sa.UUID(), nullable=False),
        sa.Column('cantidad_solicitada', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('carga_id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['carga_id'], ['carga_archivo.id']),
        sa.ForeignKeyConstraint(['referencia_id'], ['referencia.id']),
        sa.ForeignKeyConstraint(['sucursal_id'], ['sucursal.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'fecha', 'sucursal_id', 'referencia_id',
            name='uq_demanda_perdida_fecha_sucursal_referencia',
        ),
    )


def upgrade() -> None:
    _create_venta_mensual()
    _create_inventario_snapshot()
    _create_backorder_linea()
    _create_factura_proveedor_linea()
    _create_ingreso_factura()
    _create_demanda_perdida()


def downgrade() -> None:
    op.drop_table('demanda_perdida')
    op.drop_index('ix_ingreso_factura_prefijo_rh_numero_rh', table_name='ingreso_factura')
    op.drop_table('ingreso_factura')
    op.drop_index(
        'ix_factura_proveedor_linea_ingresada_transito_vencido',
        table_name='factura_proveedor_linea',
    )
    op.drop_index(
        'ix_factura_proveedor_linea_prefijo_rh_numero_rh',
        table_name='factura_proveedor_linea',
    )
    op.drop_table('factura_proveedor_linea')
    op.drop_table('backorder_linea')
    op.drop_index('ix_inventario_snapshot_fecha_corte', table_name='inventario_snapshot')
    op.drop_table('inventario_snapshot')
    op.drop_index('ix_venta_mensual_referencia_id_anio_mes', table_name='venta_mensual')
    op.drop_table('venta_mensual')
