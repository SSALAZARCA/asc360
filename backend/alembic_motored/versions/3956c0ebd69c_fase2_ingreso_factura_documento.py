"""fase2 factura ingreso corrige campos reales

Revision ID: 3956c0ebd69c
Revises: 2070a99eb6dc
Create Date: 2026-09-22 00:00:00.000000

Phase 8 "FACTURAS/INGRESOS + Tránsito" (sdd/motored-pedidos-ingesta,
Fase 2 "Ingesta", task 8.1/8.2). Corrects two real design/reality gaps
found while building `facturas.py`/`ingresos.py`/`transito.py` against the
production workbook (`PLANTILLA PEDIDO SEPTIEMBRE.xlsx`, hojas "facturas
pedidos" and "ingreso facturas ultimo 45 dias") and against the SOURCE
spec's original data model (`ESPECIFICACION_MOTORED_PEDIDOS.md` §4.3),
which `2070a99eb6dc` (Phase 3, hand-written with no live Postgres to
autogenerate against) diverged from on exactly these two tables.

**Fix 1 — `ingreso_factura` is DOCUMENT-level, not line-level.** The real
sheet is one row per `Nrodocumento`, with NO `Sucursal`/`Parte` columns at
all -- confirmed with openpyxl. `2070a99eb6dc` gave it the exact same
`(prefijo_rh, numero_rh, sucursal_id, referencia_id)` NOT NULL shape as
`factura_proveedor_linea` (a line-level table), unpopulable from this file
for every single row. The cruce itself (spec §5.6, design's own pseudocode)
never needed those two columns -- it matches purely by `(prefijo_rh,
numero_rh)`. This migration makes both FKs nullable and replaces the old
4-column UNIQUE with `UNIQUE(prefijo_rh, numero_rh)` -- the old one was
already useless for `ON CONFLICT` once those two columns are always `NULL`
(Postgres treats every `NULL` as distinct in a unique constraint, so a
re-applied load would never de-duplicate against it).

**Fix 2 — the tránsito cruce needs MONETARY net values, not `cantidad`.**
Spec §5.6 requires `ingreso_parcial_sospechoso` when the document's net
VALUE differs beyond `tolerancia_ingreso_pct` between the two sides of the
cruce -- confirmed against the real column names (`Vlr. Total Neto` in
facturas pedidos, `Valornetolocal` in ingresos), both plainly monetary, not
a unit count. `2070a99eb6dc`/design §Schema gave BOTH tables only a
`cantidad` field, dropping the source spec's original `valor_unitario`/
`valor_total` (factura side) and `valor_neto` (ingreso side) during the
schema condensation -- leaving no comparable monetary figure on either
side. `cantidad` on `factura_proveedor_linea` keeps its real meaning (unit
count from the `Cantidad` column, needed for the Parte/NC-subtraction rule)
and is NOT touched; this migration only ADDS `valor_total` alongside it.
`valor_unitario` is intentionally NOT restored -- nothing in Phase 8's
cruce needs a per-unit price, only the line's own net total. On
`ingreso_factura`, `cantidad` is RENAMED to `valor_neto`: that table has no
unit-quantity source column in the real file at all (it is a financial
document register, not a parts register), so keeping a field literally
named `cantidad` there was itself part of the same copy-paste-from-sibling
mistake as Fix 1.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3956c0ebd69c'
down_revision: Union[str, None] = '2070a99eb6dc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Fix 1 — ingreso_factura is document-level, not line-level.
    op.drop_index('ix_ingreso_factura_prefijo_rh_numero_rh', table_name='ingreso_factura')
    op.drop_constraint(
        'uq_ingreso_factura_rh_sucursal_referencia', 'ingreso_factura', type_='unique'
    )
    op.alter_column('ingreso_factura', 'sucursal_id', nullable=True)
    op.alter_column('ingreso_factura', 'referencia_id', nullable=True)
    op.create_unique_constraint(
        'uq_ingreso_factura_prefijo_rh_numero_rh', 'ingreso_factura', ['prefijo_rh', 'numero_rh'],
    )

    # Fix 2 — restore the monetary fields the tránsito cruce needs.
    op.alter_column('ingreso_factura', 'cantidad', new_column_name='valor_neto')
    op.add_column(
        'factura_proveedor_linea',
        sa.Column('valor_total', sa.Numeric(precision=14, scale=2), nullable=False),
    )


def downgrade() -> None:
    op.drop_column('factura_proveedor_linea', 'valor_total')
    op.alter_column('ingreso_factura', 'valor_neto', new_column_name='cantidad')

    op.drop_constraint(
        'uq_ingreso_factura_prefijo_rh_numero_rh', 'ingreso_factura', type_='unique'
    )
    op.alter_column('ingreso_factura', 'referencia_id', nullable=False)
    op.alter_column('ingreso_factura', 'sucursal_id', nullable=False)
    op.create_unique_constraint(
        'uq_ingreso_factura_rh_sucursal_referencia',
        'ingreso_factura', ['prefijo_rh', 'numero_rh', 'sucursal_id', 'referencia_id'],
    )
    op.create_index(
        'ix_ingreso_factura_prefijo_rh_numero_rh',
        'ingreso_factura', ['prefijo_rh', 'numero_rh'], unique=False,
    )
