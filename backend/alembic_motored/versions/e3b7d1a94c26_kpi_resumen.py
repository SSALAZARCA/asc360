"""kpi_resumen: precomputed KPI summary tables

Revision ID: e3b7d1a94c26
Revises: d7a2f4b8c915
Create Date: 2026-10-04 18:00:00.000000

Six derived tables the KPI's tabs read instead of scanning `venta_detalle`
(see `models/kpi_resumen.py`). Strictly ADDITIVE and tables only: no backfill
here, the rebuild service fills them (until then the live queries are used).

Nullable key parts are made unique with COALESCE(col, '') expression indexes.

Downgrade: drops the six tables (derived data, fully rebuildable).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e3b7d1a94c26'
down_revision: Union[str, None] = 'd7a2f4b8c915'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _sucursal_fk():
    return sa.ForeignKeyConstraint(['sucursal_id'], ['sucursal.id'], ondelete='CASCADE')


def _mes_col():
    return sa.Column('anio_mes', sa.Date(), nullable=False)


def _sucursal_col():
    return sa.Column('sucursal_id', sa.UUID(), nullable=False)


def _create_venta_mes() -> None:
    op.create_table(
        'kpi_venta_mes',
        sa.Column('id', sa.BigInteger(), sa.Identity(), nullable=False),
        _mes_col(), _sucursal_col(),
        sa.Column('vendedor_norm', sa.String(length=255), nullable=False),
        sa.Column('linea_norm', sa.Text(), nullable=True),
        sa.Column('nit_especial', sa.Text(), nullable=True),
        sa.Column('es_mostrador', sa.Boolean(), nullable=False),
        sa.Column('con_costo', sa.Boolean(), nullable=False),
        sa.Column('venta', sa.Numeric(20, 2), nullable=False),
        sa.Column('bruto', sa.Numeric(20, 2), nullable=False),
        sa.Column('descuentos', sa.Numeric(20, 2), nullable=False),
        sa.Column('cantidad', sa.Numeric(20, 2), nullable=False),
        sa.Column('lineas', sa.Integer(), nullable=False),
        sa.Column('costo', sa.Numeric(24, 6), nullable=False),
        sa.Column('costo_estimado', sa.Numeric(24, 6), nullable=False),
        _sucursal_fk(),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint('EXTRACT(DAY FROM anio_mes) = 1', name='ck_kpi_venta_mes_dia_1'),
    )
    op.create_index(
        'uq_kpi_venta_mes_llave', 'kpi_venta_mes',
        ['anio_mes', 'sucursal_id', 'vendedor_norm', sa.text("coalesce(linea_norm, '')"),
         sa.text("coalesce(nit_especial, '')"), 'es_mostrador', 'con_costo'],
        unique=True)


def _create_factura_firma() -> None:
    op.create_table(
        'kpi_factura_firma',
        sa.Column('id', sa.BigInteger(), sa.Identity(), nullable=False),
        _mes_col(), _sucursal_col(),
        sa.Column('vendedor_norm', sa.String(length=255), nullable=False),
        sa.Column('nit_especial', sa.Text(), nullable=True),
        sa.Column('firma', postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column('n_facturas', sa.Integer(), nullable=False),
        _sucursal_fk(),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint('EXTRACT(DAY FROM anio_mes) = 1', name='ck_kpi_factura_firma_dia_1'),
    )
    op.create_index(
        'uq_kpi_factura_firma_llave', 'kpi_factura_firma',
        ['anio_mes', 'sucursal_id', 'vendedor_norm', sa.text("coalesce(nit_especial, '')"), 'firma'],
        unique=True)


def _create_cliente_mes() -> None:
    op.create_table(
        'kpi_cliente_mes',
        sa.Column('id', sa.BigInteger(), sa.Identity(), nullable=False),
        _mes_col(), _sucursal_col(),
        sa.Column('vendedor_norm', sa.String(length=255), nullable=False),
        sa.Column('cliente_norm', sa.Text(), nullable=False),
        sa.Column('linea_norm', sa.Text(), nullable=False),
        sa.Column('venta', sa.Numeric(20, 2), nullable=False),
        _sucursal_fk(),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'anio_mes', 'sucursal_id', 'vendedor_norm', 'cliente_norm', 'linea_norm',
            name='uq_kpi_cliente_mes_llave'),
        sa.CheckConstraint('EXTRACT(DAY FROM anio_mes) = 1', name='ck_kpi_cliente_mes_dia_1'),
    )


def upgrade() -> None:
    _create_venta_mes()
    _create_factura_firma()
    _create_cliente_mes()
    op.create_table(
        'kpi_costo_referencia',
        sa.Column('fecha_corte', sa.Date(), nullable=False),
        sa.Column('referencia_id', sa.UUID(), nullable=False),
        sa.Column('costo_unitario', sa.Numeric(18, 4), nullable=False),
        sa.Column('fuente', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['referencia_id'], ['referencia.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('fecha_corte', 'referencia_id'),
        sa.CheckConstraint("fuente IN ('inventario', 'maestro')", name='ck_kpi_costo_referencia_fuente'),
    )
    op.create_table(
        'kpi_inventario_corte',
        sa.Column('fecha_corte', sa.Date(), nullable=False),
        _sucursal_col(),
        sa.Column('valor', sa.Numeric(24, 4), nullable=False),
        sa.Column('lineas_sin_costo', sa.Integer(), nullable=False),
        sa.Column('lineas_costo_maestro', sa.Integer(), nullable=False),
        _sucursal_fk(),
        sa.PrimaryKeyConstraint('fecha_corte', 'sucursal_id'),
    )
    op.create_table(
        'kpi_resumen_estado',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sucio', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('reconstruyendo', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('actualizado_en', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ultima_reconstruccion_total', sa.DateTime(timezone=True), nullable=True),
        sa.Column('version', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint('id = 1', name='ck_kpi_resumen_estado_fila_unica'),
    )


def downgrade() -> None:
    for tabla in (
        'kpi_resumen_estado', 'kpi_inventario_corte', 'kpi_costo_referencia', 'kpi_cliente_mes',
        'kpi_factura_firma', 'kpi_venta_mes',
    ):
        op.drop_table(tabla)
