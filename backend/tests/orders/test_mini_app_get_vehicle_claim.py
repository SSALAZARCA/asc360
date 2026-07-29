"""
tests/orders/test_mini_app_get_vehicle_claim.py -- `GET
/orders/mini-app/vehicle/{plate}` (sdd/vehicle-tenant-checkin-release PR2,
Design File Change #6/#7): the old direct `Vehicle.tenant_id` filter is
unusable since PR1 unmapped that column -- replaced by
`visible_to_tenant`. The response also drops the `tenant_id` key, adds
`claimed_by_tenant_id`/`claimed_by_tenant_name` via `get_open_claim`, and
extends `active_order` with `tenant_name`/`tenant_city` so the frontend
(PR4) can eventually name the holding taller.

No live DB: a fake session dispatches by `len(stmt.column_descriptions)`
-- the vehicle lookup selects one entity (`Vehicle`), `get_open_claim`
selects two (`ServiceOrder`, `Tenant`), so the two `execute()` calls this
endpoint issues are unambiguous by shape alone.
"""
import uuid
from datetime import datetime
from types import SimpleNamespace

from app.api.v1 import orders as orders_module
from app.api.deps import CurrentUser
from app.models.order import ServiceStatus


def make_current_user(role: str = "jefe_taller", tenant_id=None) -> CurrentUser:
    return CurrentUser(
        user_id=str(uuid.uuid4()), role=role,
        tenant_id=str(tenant_id) if tenant_id else None, name="T",
    )


def make_vehicle(vehicle_id=None, service_orders=None, client_id=None, client=None) -> SimpleNamespace:
    return SimpleNamespace(
        id=vehicle_id or uuid.uuid4(), plate="ABC123", brand="UM", model="X",
        year=2024, color="Rojo", vin="V1",
        service_orders=service_orders if service_orders is not None else [],
        # sdd/distributor-vehicle-delivery PR5 (ADR 14): default to
        # unlinked so every EXISTING caller of this factory (that doesn't
        # care about the client link) keeps working unchanged.
        client_id=client_id, client=client,
    )


def make_order(status=ServiceStatus.in_progress, created_at=None, tenant=None):
    return SimpleNamespace(status=status, created_at=created_at or datetime.utcnow(), tenant=tenant)


class _VehicleScalars:
    def __init__(self, vehicle):
        self._vehicle = vehicle

    def scalars(self):
        return self

    def first(self):
        return self._vehicle


class _ClaimResult:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class FakeMiniAppSession:
    """Dispatch by entity count: 1 == the `Vehicle` lookup, 2 ==
    `get_open_claim`'s `(ServiceOrder, Tenant)` join."""

    def __init__(self, vehicle=None, claim_row=None):
        self._vehicle = vehicle
        self._claim_row = claim_row
        self.executed_statements: list = []

    async def execute(self, stmt):
        self.executed_statements.append(stmt)
        if len(stmt.column_descriptions) == 2:
            return _ClaimResult(self._claim_row)
        return _VehicleScalars(self._vehicle)


def _compiled_sql(stmt) -> str:
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


class TestVisibleToTenantWiring:
    async def test_tenant_scoped_lookup_compiles_the_claim_predicate(self):
        tenant_id = uuid.uuid4()
        db = FakeMiniAppSession(vehicle=make_vehicle())

        result = await orders_module.mini_app_get_vehicle(
            plate="ABC123", db=db, current_user=make_current_user(tenant_id=tenant_id),
        )

        sql = _compiled_sql(db.executed_statements[0])
        assert "NOT (EXISTS" in sql
        assert tenant_id.hex in sql.replace("-", "")
        assert "tenant_id" not in result

    async def test_superadmin_lookup_is_unfiltered(self):
        db = FakeMiniAppSession(vehicle=make_vehicle())

        await orders_module.mini_app_get_vehicle(
            plate="ABC123", db=db, current_user=make_current_user(role="superadmin"),
        )

        sql = _compiled_sql(db.executed_statements[0])
        assert "NOT (EXISTS" not in sql
        assert "service_orders" not in sql


class TestResponseShapeCarriesClaimNotTenantId:
    async def test_response_has_claimed_by_fields_not_tenant_id(self):
        claim_tenant = SimpleNamespace(id=uuid.uuid4(), name="Taller B", ciudad="Bogotá")
        claim_order = SimpleNamespace(id=uuid.uuid4(), status=ServiceStatus.in_progress, created_at=datetime.utcnow())
        db = FakeMiniAppSession(vehicle=make_vehicle(), claim_row=(claim_order, claim_tenant))

        result = await orders_module.mini_app_get_vehicle(
            plate="ABC123", db=db, current_user=make_current_user(role="superadmin"),
        )

        assert "tenant_id" not in result
        assert result["claimed_by_tenant_id"] == str(claim_tenant.id)
        assert result["claimed_by_tenant_name"] == "Taller B"

    async def test_unclaimed_vehicle_has_none_claim_fields(self):
        db = FakeMiniAppSession(vehicle=make_vehicle(), claim_row=None)

        result = await orders_module.mini_app_get_vehicle(
            plate="ABC123", db=db, current_user=make_current_user(role="superadmin"),
        )

        assert result["claimed_by_tenant_id"] is None
        assert result["claimed_by_tenant_name"] is None

    async def test_active_order_carries_status_tenant_name_and_city(self):
        tenant = SimpleNamespace(name="Taller B", ciudad="Bogotá")
        order = make_order(status=ServiceStatus.in_progress, tenant=tenant)
        db = FakeMiniAppSession(vehicle=make_vehicle(service_orders=[order]))

        result = await orders_module.mini_app_get_vehicle(
            plate="ABC123", db=db, current_user=make_current_user(role="superadmin"),
        )

        assert result["active_order"] == {
            "status": "in_progress", "tenant_name": "Taller B", "tenant_city": "Bogotá",
        }

    async def test_no_active_order_is_none(self):
        delivered = make_order(status=ServiceStatus.delivered)
        db = FakeMiniAppSession(vehicle=make_vehicle(service_orders=[delivered]))

        result = await orders_module.mini_app_get_vehicle(
            plate="ABC123", db=db, current_user=make_current_user(role="superadmin"),
        )
        assert result["active_order"] is None
