"""
RED/GREEN tests for `vehicle_repository.visible_to_tenant` /
`claimed_by_other_tenant` / `RELEASING_STATUSES`
(`sdd/vehicle-tenant-checkin-release`, PR 1: migration + models +
repository claim primitives).

Mechanises two guarantees from the design:
  - Superadmin (`tenant_id=None`) gets an UNFILTERED predicate -- the exact
    `sqlalchemy.true()` singleton -- so wiring `visible_to_tenant` into
    `get_by_plate` (PR 2) cannot silently narrow superadmin's network-wide
    view. This is the "superadmin byte-for-byte identical" success
    criterion, mechanised rather than hopefully true.
  - The claim set is `{delivered, cancelled}`, a DELIBERATE FOURTH
    closed-set, distinct from this file's own display `CLOSED =
    {"completed", "delivered"}` (`get_by_plate`) and `orders.py`'s
    `{"completed", "delivered", "cancelled"}`. `completed` work is
    finished but the bike is still physically in the shop until
    `delivered`, so it must still hold the claim -- a future "helpful"
    unification with either existing set would silently release bikes
    early.
"""
import uuid

from sqlalchemy import select, true

from app.models.order import ServiceStatus
from app.models.vehicle import Vehicle
from app.repositories.vehicle_repository import (
    RELEASING_STATUSES,
    claimed_by_other_tenant,
    visible_to_tenant,
)


class TestReleasingStatusesIsADeliberateFourthClosedSet:
    def test_claim_set_is_exactly_delivered_and_cancelled(self):
        assert set(RELEASING_STATUSES) == {ServiceStatus.delivered, ServiceStatus.cancelled}

    def test_completed_does_not_release_the_claim(self):
        """Regression guard: unifying this with `get_by_plate`'s display
        `CLOSED = {"completed", "delivered"}` set would silently release a
        vehicle that is still physically in the shop."""
        assert ServiceStatus.completed not in RELEASING_STATUSES

    def test_cancelled_releases_the_claim(self):
        assert ServiceStatus.cancelled in RELEASING_STATUSES

    def test_delivered_releases_the_claim(self):
        assert ServiceStatus.delivered in RELEASING_STATUSES


class TestVisibleToTenantSuperadminIsUnfiltered:
    def test_none_tenant_id_compiles_to_the_true_singleton(self):
        """`visible_to_tenant(None)` must return the exact same object as
        `sqlalchemy.true()` -- not a semantically-equivalent-but-different
        always-true expression. `true()` is a singleton
        (`sqlalchemy.sql.elements.True_`), so `is` identity is the precise,
        mechanised assertion the design calls for."""
        assert visible_to_tenant(None) is true()


class TestClaimedByOtherTenantCompiledSQL:
    """Compiled-SQL assertions on the correlated EXISTS -- no live DB,
    matching this project's `tests/orders/conftest.py`/
    `test_active_order_by_plate.py` convention of asserting on
    `str(stmt.compile())`."""

    def test_where_excludes_releasing_statuses_and_the_requesting_tenant(self):
        tenant_id = uuid.uuid4()
        stmt = select(Vehicle).where(claimed_by_other_tenant(tenant_id))
        sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))

        assert "EXISTS" in sql
        assert "service_orders.vehicle_id = vehicles.id" in sql
        assert "service_orders.status NOT IN" in sql
        assert "'delivered'" in sql
        assert "'cancelled'" in sql
        assert "'completed'" not in sql
        assert "service_orders.tenant_id !=" in sql
        assert tenant_id.hex in sql.replace("-", "")

    def test_correlates_on_vehicle_id_not_a_cross_join(self):
        """The inner EXISTS subquery's own FROM must be `service_orders`
        only -- `vehicles` must be auto-correlated OUT of it via the outer
        `select(Vehicle)`, otherwise this degrades into a full cross join
        scan instead of a correlated per-row check."""
        tenant_id = uuid.uuid4()
        stmt = select(Vehicle).where(claimed_by_other_tenant(tenant_id))
        sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))

        inner_from = sql.split("WHERE EXISTS (SELECT service_orders.id ")[1]
        assert "FROM service_orders" in inner_from
        assert "FROM service_orders, vehicles" not in inner_from
        assert "FROM vehicles" not in inner_from.split("WHERE")[0]

    def test_exclude_order_id_adds_an_extra_predicate(self):
        tenant_id = uuid.uuid4()
        order_id = uuid.uuid4()
        stmt = select(Vehicle).where(
            claimed_by_other_tenant(tenant_id, exclude_order_id=order_id)
        )
        sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))

        assert "service_orders.id !=" in sql
        assert order_id.hex in sql.replace("-", "")

    def test_no_exclude_order_id_omits_the_extra_predicate(self):
        tenant_id = uuid.uuid4()
        stmt = select(Vehicle).where(claimed_by_other_tenant(tenant_id))
        sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))

        assert "service_orders.id !=" not in sql


class TestVisibleToTenantScopedCompiledSQL:
    def test_tenant_provided_is_the_negation_of_claimed_by_other_tenant(self):
        """`visible_to_tenant(B)` must be the logical NOT of
        `claimed_by_other_tenant(B)` -- one predicate expresses BOTH
        'unclaimed' and 'claimed by B' as 'not claimed by anyone else'."""
        tenant_id = uuid.uuid4()
        stmt = select(Vehicle).where(visible_to_tenant(tenant_id))
        sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))

        assert "NOT (EXISTS" in sql
        assert "service_orders.tenant_id !=" in sql
        assert tenant_id.hex in sql.replace("-", "")

    def test_matches_an_unclaimed_vehicle_and_a_b_claimed_vehicle_by_construction(self):
        """`~claimed_by_other_tenant(B)` is true whenever there is NO open
        order for the vehicle owned by anyone other than B -- which is
        exactly the union of 'unclaimed' and 'claimed by B'. Asserted here
        via De Morgan's on the predicate's own structure (no live DB in
        this harness); the Taller A -> Taller B round-trip integration
        test (PR 3, order-creation wiring) exercises this behaviorally
        against real order rows.
        """
        tenant_id = uuid.uuid4()
        negated = str(
            select(Vehicle)
            .where(visible_to_tenant(tenant_id))
            .compile(compile_kwargs={"literal_binds": True})
        )
        positive = str(
            select(Vehicle)
            .where(claimed_by_other_tenant(tenant_id))
            .compile(compile_kwargs={"literal_binds": True})
        )
        assert negated == positive.replace(
            "WHERE EXISTS", "WHERE NOT (EXISTS"
        ) + ")"
