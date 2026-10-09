"""lider inventarios role

Revision ID: b4f9c2e6a813
Revises: d7a3c5e91f20
Create Date: 2026-10-09 12:00:00.000000

Feature motored-conteos-inventario, WU1. Adds the `LIDER_INVENTARIOS`
value to the existing `motored_role` Postgres enum (the inventory-count
leader: runs the counts assigned to them). Its own revision because
PostgreSQL requires `ALTER TYPE ... ADD VALUE` to be committed before the
new value can be used in the same transaction -- same `autocommit_block()`
precedent as `d7a3c5e91f20_coordinador_repuestos_role.py`. `IF NOT EXISTS`
keeps it idempotent.

Downgrade is a documented no-op: PostgreSQL cannot drop a single enum value
without recreating the whole type. `LIDER_INVENTARIOS` remains in the enum,
unused, after a downgrade.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4f9c2e6a813'
down_revision: Union[str, None] = 'd7a3c5e91f20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(sa.text(
            "ALTER TYPE motored_role "
            "ADD VALUE IF NOT EXISTS 'LIDER_INVENTARIOS'"
        ))


def downgrade() -> None:
    # PostgreSQL cannot remove a value from an enum without recreating the
    # type: 'LIDER_INVENTARIOS' stays in the enum, unused.
    pass
