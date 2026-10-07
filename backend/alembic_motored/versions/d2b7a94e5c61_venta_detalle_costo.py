"""venta_detalle_costo: the ERP sale cost per sales line

Revision ID: d2b7a94e5c61
Revises: c6e1f8a2d953
Create Date: 2026-10-07 09:00:00.000000

Adds the nullable `venta_detalle.costo` NUMERIC(18,2): the line total of the
optional VENTAS column "Costo promedio total", stored as-is (negatives
kept). Existing rows stay NULL (their files carried no cost), so nothing
reads differently until a month is reloaded with the raw ERP file.

Downgrade: drops the column; the stored costs are lost.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd2b7a94e5c61'
down_revision: Union[str, None] = 'c6e1f8a2d953'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "venta_detalle",
        sa.Column("costo", sa.Numeric(18, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("venta_detalle", "costo")
