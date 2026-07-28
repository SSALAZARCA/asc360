"""
tests/vehicles/test_get_by_vin_visibility.py -- `vehicle_repository.
get_by_vin` (sdd/vehicle-tenant-checkin-release PR2, Design File Change
#4): `tenant_id: UUID` (required, no superadmin escape, and a direct
`Vehicle.tenant_id` comparison unusable since PR1) -> `tenant_id:
Optional[UUID] = None` + `visible_to_tenant`.

Verified zero real callers today (`rg get_by_vin` -> only its own
definition) -- rewritten for consistency with `get_by_plate`, but this
surface is otherwise unexercised in production.
"""
import inspect
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


class TestGetByVinTenantIdIsOptional:
    def test_tenant_id_defaults_to_none(self):
        sig = inspect.signature(vehicle_repository.get_by_vin)
        assert sig.parameters["tenant_id"].default is None


class TestGetByVinUsesVisibleToTenant:
    async def test_tenant_scoped_lookup_compiles_the_claim_predicate(self):
        tenant_id = uuid.uuid4()
        db = FakeVehicleLookupSession()

        await vehicle_repository.get_by_vin(db, "VIN0001", tenant_id)

        sql = _compiled_sql(db.executed_statements[0])
        assert "NOT (EXISTS" in sql
        assert tenant_id.hex in sql.replace("-", "")

    async def test_none_tenant_id_is_unfiltered_network_wide(self):
        db = FakeVehicleLookupSession()

        await vehicle_repository.get_by_vin(db, "VIN0001", None)

        sql = _compiled_sql(db.executed_statements[0])
        assert "service_orders" not in sql

    async def test_omitting_tenant_id_defaults_to_unfiltered(self):
        db = FakeVehicleLookupSession()

        await vehicle_repository.get_by_vin(db, "VIN0001")

        sql = _compiled_sql(db.executed_statements[0])
        assert "service_orders" not in sql
