"""sucursal_codigo_co: ERP store code (centro de operación)

Revision ID: b5d9e3a7c418
Revises: a8c4e2f61d07
Create Date: 2026-10-04 23:30:00.000000

Adds the nullable `sucursal.codigo_co` (one region letter plus two digits,
e.g. E05, stored trimmed and upper-cased by the service layer). A different
C.O. is a different store, so the code is UNIQUE; NULL is allowed on many
rows (every existing store until the owner loads the codes).

The UNIQUE constraint is DEFERRABLE INITIALLY DEFERRED: one Sucursales
upload may swap the codes of two stores, and the rows are flushed one by
one, so the check must run at COMMIT on the final state.

Downgrade: drops the column with its constraint. The codes are lost (they
live nowhere else).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b5d9e3a7c418'
down_revision: Union[str, None] = 'a8c4e2f61d07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UNIQUE = 'uq_sucursal_codigo_co'


def upgrade() -> None:
    op.add_column(
        'sucursal', sa.Column('codigo_co', sa.String(10), nullable=True)
    )
    op.create_unique_constraint(
        _UNIQUE, 'sucursal', ['codigo_co'],
        deferrable=True, initially='DEFERRED',
    )


def downgrade() -> None:
    op.drop_constraint(_UNIQUE, 'sucursal', type_='unique')
    op.drop_column('sucursal', 'codigo_co')
