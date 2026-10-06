"""codigo_co_obligatorio: every store needs its ERP C.O. code

Revision ID: c6e1f8a2d953
Revises: b5d9e3a7c418
Create Date: 2026-10-06 10:00:00.000000

`sucursal.codigo_co` becomes NOT NULL: the C.O. identifies the store, and
the service layer already requires it on create, upload and edit. The
owner loaded the codes of every store, so no row should be NULL.

The upgrade never invents a code: when a store still has none it stops
with a Spanish message naming the stores, and nothing changes (the whole
migration runs in one transaction).

Downgrade: the column is nullable again. No data changes.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c6e1f8a2d953'
down_revision: Union[str, None] = 'b5d9e3a7c418'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SIN_CODIGO = sa.text(
    "SELECT nombre FROM sucursal WHERE codigo_co IS NULL ORDER BY nombre"
)


def _mensaje_sin_codigo(nombres: Sequence[str]) -> str:
    sujeto = "sucursal" if len(nombres) == 1 else "sucursales"
    return (
        f"Hay {len(nombres)} {sujeto} sin Código C.O. "
        f"({', '.join(nombres)}); cárguelo antes de migrar."
    )


def upgrade() -> None:
    nombres = list(op.get_bind().execute(_SIN_CODIGO).scalars().all())
    if nombres:
        raise RuntimeError(_mensaje_sin_codigo(nombres))
    op.alter_column(
        'sucursal', 'codigo_co',
        existing_type=sa.String(10), nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        'sucursal', 'codigo_co',
        existing_type=sa.String(10), nullable=True,
    )
