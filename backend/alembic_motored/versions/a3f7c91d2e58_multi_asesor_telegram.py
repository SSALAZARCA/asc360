"""multi asesor telegram

Revision ID: a3f7c91d2e58
Revises: 5c2e8a1f9b47
Create Date: 2026-09-29 12:00:00.000000

Several advisors can share one Telegram account (one phone per store):

- Drops `uq_usuario_telegram_id`; `telegram_id` keeps a plain lookup index.
- `uq_usuario_telegram_phone_activo`: the same person (same Telegram AND same
  phone) cannot hold two non-rejected registrations.
- `uq_usuario_telegram_admin`: an ADMIN keeps one Telegram to itself among
  admins, so `/admin/vincular`'s IntegrityError backstop still guards the
  race between two link codes for the same Telegram.

Downgrade restores the unique constraint and FAILS if two usuarios already
share a Telegram; unlink or delete the extra rows first.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f7c91d2e58'
down_revision: Union[str, None] = '5c2e8a1f9b47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # `env.py` runs every migration inside one transaction, so SET LOCAL is
    # scoped to it: fail fast instead of queueing behind long readers.
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.drop_constraint('uq_usuario_telegram_id', 'usuario', type_='unique')
    op.create_index('ix_usuario_telegram_id', 'usuario', ['telegram_id'], unique=False)
    op.create_index(
        'uq_usuario_telegram_phone_activo',
        'usuario',
        ['telegram_id', 'phone'],
        unique=True,
        postgresql_where=sa.text("status <> 'rejected'"),
    )
    op.create_index(
        'uq_usuario_telegram_admin',
        'usuario',
        ['telegram_id'],
        unique=True,
        postgresql_where=sa.text("role = 'ADMIN'"),
    )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.drop_index('uq_usuario_telegram_admin', table_name='usuario')
    op.drop_index('uq_usuario_telegram_phone_activo', table_name='usuario')
    op.drop_index('ix_usuario_telegram_id', table_name='usuario')
    op.create_unique_constraint('uq_usuario_telegram_id', 'usuario', ['telegram_id'])
