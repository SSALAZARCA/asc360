"""factura proveedor linea valor unitario

Revision ID: e3a7c1d94b52
Revises: d58b2c9e4a17
Create Date: 2026-10-09 15:00:00.000000

Feature motored-ingresos-responsable-plantilla, T1. Adds the nullable
`factura_proveedor_linea.valor_unitario` (source column "Vlr. Unitario"),
needed by the ERP "Entradas x Compra" template. NULL for lines loaded before
this migration or from files without that column.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e3a7c1d94b52'
down_revision: Union[str, None] = 'd58b2c9e4a17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "factura_proveedor_linea",
        sa.Column("valor_unitario", sa.Numeric(14, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("factura_proveedor_linea", "valor_unitario")
