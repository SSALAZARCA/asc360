"""usuario password_changed_at

Revision ID: b8d2f4a61c93
Revises: a7c3e91d5b20
Create Date: 2026-09-30 15:00:00.000000

Adds `usuario.password_changed_at` (naive UTC, nullable). Sessions whose token
was issued before this instant are rejected, so an admin reset or an own
password change cuts every other session. Additive and nullable, no backfill:
existing users keep NULL and their tokens stay valid until they expire.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b8d2f4a61c93'
down_revision: Union[str, None] = 'a7c3e91d5b20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("usuario", sa.Column("password_changed_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("usuario", "password_changed_at")
