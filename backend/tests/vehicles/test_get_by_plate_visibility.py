"""
tests/vehicles/test_get_by_plate_visibility.py -- `vehicle_repository.
get_by_plate` (sdd/vehicle-tenant-checkin-release PR2, Design File
Change #3): `if tenant_id: stmt.where(Vehicle.tenant_id == tenant_id)`
(unusable since PR1 unmapped that column) -> unconditional
`stmt.where(visible_to_tenant(tenant_id))`, with a raw header string
coerced to `UUID` first.

Compiled-SQL assertions, no live DB, matching `test_visible_to_tenant.py`'s
convention. The fake session returns `None` from `.scalars().first()` so
the post-lookup enrichment block (client/mileage/active_order/history) is
never exercised here -- out of scope for this file.
"""
import uuid

from app.repositories.vehicle_repository import vehicle_repository


class _ScalarsNone:
    def scalars(self):
        return self

    def first(self):
        return None


class FakeVehicleLookupSession:
    def __init__(self):
        self.executed_statements = []

    async def execute(self, stmt):
        self.executed_statements.append(stmt)
        return _ScalarsNone()


def _compiled_sql(stmt) -> str:
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


class TestGetByPlateUsesVisibleToTenantUnconditionally:
    async def test_tenant_scoped_lookup_compiles_the_claim_predicate(self):
        tenant_id = uuid.uuid4()
        db = FakeVehicleLookupSession()

        await vehicle_repository.get_by_plate(db, "ABC123", tenant_id)

        sql = _compiled_sql(db.executed_statements[0])
        assert "NOT (EXISTS" in sql
        assert "service_orders.tenant_id !=" in sql
        assert tenant_id.hex in sql.replace("-", "")

    async def test_none_tenant_id_is_unfiltered_network_wide(self):
        """Superadmin (`tenant_id=None`) must stay byte-for-byte
        unfiltered -- `visible_to_tenant(None)` is the `true()` singleton,
        so no `service_orders` predicate leaks in at all."""
        db = FakeVehicleLookupSession()

        await vehicle_repository.get_by_plate(db, "ABC123", None)

        sql = _compiled_sql(db.executed_statements[0])
        assert "service_orders" not in sql


class TestGetByPlateCoercesStringTenantIdToUuid:
    async def test_string_tenant_id_is_bound_as_a_real_uuid(self):
        tenant_id = uuid.uuid4()
        db = FakeVehicleLookupSession()

        await vehicle_repository.get_by_plate(db, "ABC123", str(tenant_id))

        stmt = db.executed_statements[0]
        compiled = stmt.compile()
        bound_values = list(compiled.params.values())
        assert any(isinstance(v, uuid.UUID) and v == tenant_id for v in bound_values)
        assert not any(v == str(tenant_id) and isinstance(v, str) for v in bound_values)
