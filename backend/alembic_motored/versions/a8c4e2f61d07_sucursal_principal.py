"""sucursal_principal: associated stores roll up into a principal

Revision ID: a8c4e2f61d07
Revises: e3b7d1a94c26
Create Date: 2026-10-04 22:00:00.000000

Adds the nullable self-FK `sucursal.principal_id`. NULL means the store is
its own principal (every existing row), so no backfill is needed. Depth 1
is enforced by the service layer; the CHECK only forbids a self-reference.

ON DELETE RESTRICT: stores are only soft-deleted. A SET NULL would turn an
associated point into a principal silently, giving it its own pedido.

Downgrade: drops the column with its index, FK and CHECK. The associations
are lost (they live nowhere else).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a8c4e2f61d07'
down_revision: Union[str, None] = 'e3b7d1a94c26'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FK = 'fk_sucursal_principal_id'
_CHECK = 'ck_sucursal_principal_no_propia'
_INDEX = 'ix_sucursal_principal_id'


def upgrade() -> None:
    op.add_column(
        'sucursal', sa.Column('principal_id', sa.UUID(), nullable=True)
    )
    op.create_foreign_key(
        _FK, 'sucursal', 'sucursal', ['principal_id'], ['id'],
        ondelete='RESTRICT',
    )
    op.create_check_constraint(_CHECK, 'sucursal', 'principal_id <> id')
    op.create_index(_INDEX, 'sucursal', ['principal_id'])


def downgrade() -> None:
    op.drop_index(_INDEX, table_name='sucursal')
    op.drop_constraint(_CHECK, 'sucursal', type_='check')
    op.drop_constraint(_FK, 'sucursal', type_='foreignkey')
    op.drop_column('sucursal', 'principal_id')
