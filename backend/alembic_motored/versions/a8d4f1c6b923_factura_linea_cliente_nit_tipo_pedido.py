"""factura proveedor linea cliente_nit tipo_pedido

Revision ID: a8d4f1c6b923
Revises: f6b2d8a35c71
Create Date: 2026-10-09 18:00:00.000000

Adds the nullable `factura_proveedor_linea.cliente_nit` (source column
"Número Identificación") and `tipo_pedido` (source column "Tipo de Pedido").
`tipo_pedido` leaves the warranty invoices (GARANTIA25) out of the ingreso
process; both are NULL for lines loaded before this migration until the file
is uploaded again.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a8d4f1c6b923'
down_revision: Union[str, None] = 'f6b2d8a35c71'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "factura_proveedor_linea",
        sa.Column("cliente_nit", sa.String(20), nullable=True))
    op.add_column(
        "factura_proveedor_linea",
        sa.Column("tipo_pedido", sa.String(30), nullable=True))


def downgrade() -> None:
    op.drop_column("factura_proveedor_linea", "tipo_pedido")
    op.drop_column("factura_proveedor_linea", "cliente_nit")
