"""add registered_by_tenant_id to vehicles

Revision ID: c9d0e1f2a3b4
Revises: d7e8f9a0b1c2
Create Date: 2026-07-29

`sdd/distributor-vehicle-delivery` follow-up: which Distribuidora (tenant)
registered a given delivery record, so the new `GET /distributor/deliveries`
list can be scoped per-Distribuidora. `vehicles`: +`registered_by_tenant_id`
(nullable FK to `tenants.id`, indexed).

This is UNRELATED to the deliberately-unmapped `vehicles.tenant_id` column
from `c6d7e8f9a0b1`/`sdd/vehicle-tenant-checkin-release` -- that one tracked
a temporary, derived "which taller currently holds this vehicle" claim; this
one is a permanent "which Distribuidora's employee registered this sale"
fact set once at creation and never changed.

Additive, nullable-only migration: `ADD COLUMN ... NULL` is catalog-only in
modern Postgres (no table rewrite, no long lock). Nothing reads or writes
this column until the follow-up service/router change ships alongside it.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'c9d0e1f2a3b4'
down_revision = 'd7e8f9a0b1c2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'vehicles',
        sa.Column(
            'registered_by_tenant_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('tenants.id'),
            nullable=True,
        ),
    )
    op.create_index('ix_vehicles_registered_by_tenant_id', 'vehicles', ['registered_by_tenant_id'])


def downgrade() -> None:
    op.drop_index('ix_vehicles_registered_by_tenant_id', table_name='vehicles')
    op.drop_column('vehicles', 'registered_by_tenant_id')
