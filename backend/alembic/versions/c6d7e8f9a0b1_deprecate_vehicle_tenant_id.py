"""deprecate vehicles.tenant_id

Revision ID: c6d7e8f9a0b1
Revises: b3c4d5e6f7a8
Create Date: 2026-07-27

`sdd/vehicle-tenant-checkin-release` PR 1. A vehicle's tenant association
becomes a derived, live-computed claim (see
`app/repositories/vehicle_repository.py`'s `visible_to_tenant`/
`get_open_claim`) instead of a stored column -- the "which taller is
servicing this bike right now" fact already lives on
`service_orders.tenant_id`, and a stored `vehicles.tenant_id` can only ever
go stale once a vehicle changes hands between talleres.

`upgrade`: DROP NOT NULL only -- no data movement, no row lock beyond a
catalog update. The column and all historical data stay in Postgres so a
`git revert && git push` rollback (this project's Coolify auto-deploy path)
fully restores behaviour with zero manual DB step; only vehicles inserted
during the deprecation window (once the ORM stops mapping this column)
carry NULL. A follow-up release physically drops the column once one
release cycle has passed clean.

`downgrade`: backfill each vehicle's `tenant_id` from its own most recent
`ServiceOrder.tenant_id` (by `created_at`), then restore NOT NULL only if
zero NULLs remain afterward -- a vehicle with zero ServiceOrder rows (e.g.
inserted, during the deprecation window, with no order ever created) has no
recoverable tenant and is left nullable, logged as an orphan rather than
failing the whole downgrade.
"""
import logging

from alembic import op
import sqlalchemy as sa

logger = logging.getLogger(__name__)

revision = 'c6d7e8f9a0b1'
down_revision = 'b3c4d5e6f7a8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TABLE vehicles ALTER COLUMN tenant_id DROP NOT NULL"))


def downgrade() -> None:
    op.execute(sa.text("""
        WITH latest_order_per_vehicle AS (
            SELECT DISTINCT ON (vehicle_id) vehicle_id, tenant_id
            FROM service_orders
            ORDER BY vehicle_id, created_at DESC
        )
        UPDATE vehicles v
        SET tenant_id = lo.tenant_id
        FROM latest_order_per_vehicle lo
        WHERE v.id = lo.vehicle_id
          AND v.tenant_id IS NULL
    """))

    conn = op.get_bind()
    remaining_nulls = conn.execute(
        sa.text("SELECT COUNT(*) FROM vehicles WHERE tenant_id IS NULL")
    ).scalar()

    if remaining_nulls == 0:
        op.execute(sa.text("ALTER TABLE vehicles ALTER COLUMN tenant_id SET NOT NULL"))
    else:
        logger.warning(
            "%s vehicle(s) have no ServiceOrder to backfill tenant_id from "
            "(orphan vehicles registered during the deprecation window with "
            "no order ever created). Leaving vehicles.tenant_id nullable -- "
            "resolve these rows manually before re-attempting to restore NOT NULL.",
            remaining_nulls,
        )
