"""kpi_inventario_par + kpi_costo_mes_referencia: summaries for the Inventario tab

Revision ID: c4e8a2d6f931
Revises: b2f6d9a4c718
Create Date: 2026-10-10 09:00:00.000000

odd/tasks/motored-kpis-inventario.md. `kpi_inventario_par` holds stock and value per
(closing cut, store, referencia) and `kpi_costo_mes_referencia` the cost of sales per
(month, store, referencia). `kpi_inventario_corte` (already there) now keeps every
closing cut instead of only the latest. Both new tables are empty after the upgrade,
so the summaries are flagged dirty: the readers answer live until the background
rebuild fills them. Downgrade drops the tables.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c4e8a2d6f931'
down_revision: Union[str, None] = 'b2f6d9a4c718'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _sucursal_fk() -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(['sucursal_id'], ['sucursal.id'], ondelete='CASCADE')


def _crear_par() -> None:
    op.create_table(
        'kpi_inventario_par',
        sa.Column('fecha_corte', sa.Date(), nullable=False),
        sa.Column('sucursal_id', sa.UUID(), nullable=False),
        sa.Column('referencia_id', sa.UUID(), nullable=False),
        sa.Column('existencia', sa.Numeric(20, 2), nullable=False),
        sa.Column('valor', sa.Numeric(24, 4), nullable=False),
        _sucursal_fk(),
        sa.PrimaryKeyConstraint('fecha_corte', 'sucursal_id', 'referencia_id'),
    )


def _crear_costo_mes() -> None:
    op.create_table(
        'kpi_costo_mes_referencia',
        sa.Column('anio_mes', sa.Date(), nullable=False),
        sa.Column('sucursal_id', sa.UUID(), nullable=False),
        sa.Column('referencia_id', sa.UUID(), nullable=False),
        sa.Column('costo', sa.Numeric(24, 6), nullable=False),
        _sucursal_fk(),
        sa.ForeignKeyConstraint(['referencia_id'], ['referencia.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('anio_mes', 'sucursal_id', 'referencia_id'),
        sa.CheckConstraint('EXTRACT(DAY FROM anio_mes) = 1', name='ck_kpi_costo_mes_referencia_dia_1'),
    )


def upgrade() -> None:
    _crear_par()
    _crear_costo_mes()
    op.execute('UPDATE kpi_resumen_estado SET sucio = true')


def downgrade() -> None:
    op.drop_table('kpi_costo_mes_referencia')
    op.drop_table('kpi_inventario_par')
