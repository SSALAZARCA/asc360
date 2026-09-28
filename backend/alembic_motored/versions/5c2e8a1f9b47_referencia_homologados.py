"""referencia homologados

Revision ID: 5c2e8a1f9b47
Revises: 43191272c816
Create Date: 2026-09-28 12:00:00.000000

Referencia 9-column layout (owner request 2026-09-28): adds
`referencia.homologados` ("Homologados otras marcas"), a multi-value list of
equivalent part codes from other brands. NOT NULL with an empty-array server
default, so existing rows get `{}` and "no homologados" has one single
representation.

`precio_venta` is intentionally NOT dropped: it left the business layout
(template, bulk parser, UI) but the column and its data are kept.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '5c2e8a1f9b47'
down_revision: Union[str, None] = '43191272c816'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # `env.py` runs every migration inside `context.begin_transaction()`, so
    # SET LOCAL is scoped to this transaction: if the ACCESS EXCLUSIVE lock
    # on `referencia` can't be taken within 5s (busy table), fail fast
    # instead of queueing behind long readers and blocking every request.
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.add_column(
        'referencia',
        sa.Column(
            'homologados',
            postgresql.ARRAY(sa.String(length=100)),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )


def downgrade() -> None:
    op.drop_column('referencia', 'homologados')
