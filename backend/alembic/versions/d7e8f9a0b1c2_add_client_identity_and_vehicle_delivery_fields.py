"""add client identity fields to users and delivery fields to vehicles

Revision ID: d7e8f9a0b1c2
Revises: c6d7e8f9a0b1
Create Date: 2026-07-28

`sdd/distributor-vehicle-delivery` PR1. Additive, nullable-only migration:

- `users`: +`identification` (cédula, indexed, NOT unique -- pre-change data
  may already hold the same person twice across talleres, see design
  Decision 8), +`birth_date`, +`city`, +`department`, +`address`.
- `vehicles`: +`delivery_date` (DATE, day-precision warranty lower bound),
  +`engine_number`, +`delivery_act_url` (MinIO URL for the signed delivery
  act photo), +`client_id` (nullable FK to `users.id`, indexed, ADR 12 --
  added to this SAME migration rather than a follow-up one).

No backfill, no default, no NOT NULL, no change to any existing column --
`ADD COLUMN ... NULL` is catalog-only in modern Postgres (no table rewrite,
no long lock). Nothing reads or writes these columns yet; PR1 is safe to
ship alone.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'd7e8f9a0b1c2'
down_revision = 'c6d7e8f9a0b1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('identification', sa.String(50), nullable=True))
    op.add_column('users', sa.Column('birth_date', sa.Date(), nullable=True))
    op.add_column('users', sa.Column('city', sa.String(120), nullable=True))
    op.add_column('users', sa.Column('department', sa.String(120), nullable=True))
    op.add_column('users', sa.Column('address', sa.String(255), nullable=True))
    op.create_index('ix_users_identification', 'users', ['identification'])

    op.add_column('vehicles', sa.Column('delivery_date', sa.Date(), nullable=True))
    op.add_column('vehicles', sa.Column('engine_number', sa.String(100), nullable=True))
    op.add_column('vehicles', sa.Column('delivery_act_url', sa.String(500), nullable=True))
    op.add_column(
        'vehicles',
        sa.Column(
            'client_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id'),
            nullable=True,
        ),
    )
    op.create_index('ix_vehicles_client_id', 'vehicles', ['client_id'])


def downgrade() -> None:
    op.drop_index('ix_vehicles_client_id', table_name='vehicles')
    op.drop_column('vehicles', 'client_id')
    op.drop_column('vehicles', 'delivery_act_url')
    op.drop_column('vehicles', 'engine_number')
    op.drop_column('vehicles', 'delivery_date')

    op.drop_index('ix_users_identification', table_name='users')
    op.drop_column('users', 'address')
    op.drop_column('users', 'department')
    op.drop_column('users', 'city')
    op.drop_column('users', 'birth_date')
    op.drop_column('users', 'identification')
