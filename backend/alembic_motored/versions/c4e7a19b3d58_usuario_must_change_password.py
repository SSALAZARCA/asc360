"""usuario must_change_password

Revision ID: c4e7a19b3d58
Revises: b8d2f4a61c93
Create Date: 2026-09-30 17:00:00.000000

Adds `usuario.must_change_password` (NOT NULL, server default false). An admin
create or reset sets it true; while set, the backend only lets the user call
POST /auth/password. Existing users stay false.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c4e7a19b3d58'
down_revision: Union[str, None] = 'b8d2f4a61c93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "usuario",
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("usuario", "must_change_password")
