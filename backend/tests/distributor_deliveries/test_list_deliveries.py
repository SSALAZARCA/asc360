"""
tests/distributor_deliveries/test_list_deliveries.py — `GET
/distributor/deliveries` (follow-up feature, migration `c9d0e1f2a3b4`).

Service-level tests compile the emitted SQL (`_compiled_sql`, matching
`tests/vehicles/test_get_by_plate_visibility.py`'s convention) to prove the
tenant filter is actually applied at the SQL level -- `FakeDeliverySession`
ignores `.where()` clauses when returning its canned row list, so a
response-shape-only assertion could not tell filtered code from unfiltered
code apart. Router-level test proves the 403 guard fires before any DB read
(mirrors `test_auth.py`).
"""
import uuid
from datetime import date

from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db
from app.api.deps import get_current_user
from app.services import distributor_delivery_service as svc

from tests.distributor_deliveries.conftest import (
    FakeDeliverySession,
    NoTouchSession,
    make_client_user,
    make_delivery_vehicle,
    make_distribuidor,
    make_jefe_taller,
    make_superadmin,
    make_tenant,
)


def _compiled_sql(stmt) -> str:
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


class TestDistribuidorSeesOnlyTheirOwnTenant:
    async def test_where_clause_scopes_by_registered_by_tenant_id(self):
        tenant_id = uuid.uuid4()
        fake_db = FakeDeliverySession()
        actor = make_distribuidor(tenant_id=tenant_id)

        await svc.list_deliveries(fake_db, actor)

        sql = _compiled_sql(fake_db.executed_statements[0])
        assert "vehicles.delivery_date IS NOT NULL" in sql
        assert "vehicles.registered_by_tenant_id =" in sql
        assert tenant_id.hex in sql.replace("-", "")

    async def test_returns_mapped_rows_without_cross_tenant_name(self):
        tenant_id = uuid.uuid4()
        client = make_client_user(name="Juan Perez")
        vehicle = make_delivery_vehicle(
            plate="ABC123",
            delivery_date=date(2026, 7, 20),
            client=client,
            registered_by_tenant_id=tenant_id,
        )
        fake_db = FakeDeliverySession(vehicles=[vehicle])
        actor = make_distribuidor(tenant_id=tenant_id)

        result = await svc.list_deliveries(fake_db, actor)

        assert len(result) == 1
        assert result[0].plate == "ABC123"
        assert result[0].client_name == "Juan Perez"
        assert result[0].delivery_date == date(2026, 7, 20)
        # A Distribuidor's own filtered view never needs/exposes the
        # Distribuidora name -- they only ever see their own tenant anyway.
        assert result[0].registered_by_tenant_name is None

    async def test_vehicle_with_no_client_link_has_null_client_name(self):
        tenant_id = uuid.uuid4()
        vehicle = make_delivery_vehicle(
            plate="NOCLIENT1", delivery_date=date(2026, 7, 5), registered_by_tenant_id=tenant_id
        )
        fake_db = FakeDeliverySession(vehicles=[vehicle])
        actor = make_distribuidor(tenant_id=tenant_id)

        result = await svc.list_deliveries(fake_db, actor)

        assert result[0].client_name is None

    async def test_returns_client_identification_for_search(self):
        tenant_id = uuid.uuid4()
        client = make_client_user(name="Juan Perez", identification="900555111")
        vehicle = make_delivery_vehicle(
            plate="ABC123", delivery_date=date(2026, 7, 20), client=client,
            registered_by_tenant_id=tenant_id,
        )
        fake_db = FakeDeliverySession(vehicles=[vehicle])
        actor = make_distribuidor(tenant_id=tenant_id)

        result = await svc.list_deliveries(fake_db, actor)

        assert result[0].client_identification == "900555111"

    async def test_vehicle_with_no_client_link_has_null_client_identification(self):
        tenant_id = uuid.uuid4()
        vehicle = make_delivery_vehicle(
            plate="NOCLIENT2", delivery_date=date(2026, 7, 6), registered_by_tenant_id=tenant_id
        )
        fake_db = FakeDeliverySession(vehicles=[vehicle])
        actor = make_distribuidor(tenant_id=tenant_id)

        result = await svc.list_deliveries(fake_db, actor)

        assert result[0].client_identification is None


class TestDeliveryActUrlExposedOnListRows:
    """Follow-up fix (2026-07-30): `Vehicle.delivery_act_url` is a plain,
    directly-fetchable static MinIO URL -- no signing/proxy needed -- so
    exposing it on the list lets the Distribuidor download what was
    uploaded."""

    async def test_row_with_a_delivery_act_shows_its_url(self):
        tenant_id = uuid.uuid4()
        vehicle = make_delivery_vehicle(
            plate="WITHACT1", delivery_date=date(2026, 7, 5), registered_by_tenant_id=tenant_id
        )
        vehicle.delivery_act_url = "https://minio.local/acta.jpg"
        fake_db = FakeDeliverySession(vehicles=[vehicle])
        actor = make_distribuidor(tenant_id=tenant_id)

        result = await svc.list_deliveries(fake_db, actor)

        assert result[0].delivery_act_url == "https://minio.local/acta.jpg"

    async def test_row_with_no_delivery_act_shows_null(self):
        tenant_id = uuid.uuid4()
        vehicle = make_delivery_vehicle(
            plate="NOACT1", delivery_date=date(2026, 7, 5), registered_by_tenant_id=tenant_id
        )
        fake_db = FakeDeliverySession(vehicles=[vehicle])
        actor = make_distribuidor(tenant_id=tenant_id)

        result = await svc.list_deliveries(fake_db, actor)

        assert result[0].delivery_act_url is None


class TestDistribuidorWithNoTenantAssignedGetsEmptyListAndZeroReads:
    async def test_no_tenant_assigned_returns_empty_list_without_touching_db(self):
        """Distribuidor with `tenant_id=None` must never see anyone else's
        (or nobody's) data -- an unguarded `Column == None` would compile
        to `IS NULL` and leak every NULL-tenant row, so this MUST short
        circuit with zero DB reads (`NoTouchSession` raises if the service
        ever calls `.execute()`/`.get()`)."""
        actor = make_distribuidor(tenant_id=None)
        fake_db = NoTouchSession()

        result = await svc.list_deliveries(fake_db, actor)

        assert result == []


class TestSuperadminSeesAllTenantsWithDistribuidoraName:
    async def test_no_tenant_filter_applied_in_the_query(self):
        fake_db = FakeDeliverySession()
        actor = make_superadmin()

        await svc.list_deliveries(fake_db, actor)

        sql = _compiled_sql(fake_db.executed_statements[0])
        assert "vehicles.delivery_date IS NOT NULL" in sql
        assert "registered_by_tenant_id =" not in sql

    async def test_returns_rows_from_multiple_tenants_with_distribuidora_name(self):
        tenant_a = make_tenant(name="Distribuidora A")
        tenant_b = make_tenant(name="Distribuidora B")
        vehicle_a = make_delivery_vehicle(
            plate="AAA111",
            delivery_date=date(2026, 7, 10),
            registered_by_tenant_id=tenant_a.id,
            registered_by_tenant=tenant_a,
        )
        vehicle_b = make_delivery_vehicle(
            plate="BBB222",
            delivery_date=date(2026, 7, 20),
            registered_by_tenant_id=tenant_b.id,
            registered_by_tenant=tenant_b,
        )
        fake_db = FakeDeliverySession(vehicles=[vehicle_a, vehicle_b])
        actor = make_superadmin()

        result = await svc.list_deliveries(fake_db, actor)

        names = {item.plate: item.registered_by_tenant_name for item in result}
        assert names == {"AAA111": "Distribuidora A", "BBB222": "Distribuidora B"}

    async def test_superadmin_backfill_row_with_no_tenant_has_null_name(self):
        vehicle = make_delivery_vehicle(plate="BACKFILL1", delivery_date=date(2026, 7, 1))
        fake_db = FakeDeliverySession(vehicles=[vehicle])
        actor = make_superadmin()

        result = await svc.list_deliveries(fake_db, actor)

        assert result[0].registered_by_tenant_name is None


class TestOrderingAndDeliveryDateFilterAlwaysPresent:
    async def test_ordered_by_delivery_date_descending_and_filters_null_dates(self):
        fake_db = FakeDeliverySession()
        actor = make_superadmin()

        await svc.list_deliveries(fake_db, actor)

        sql = _compiled_sql(fake_db.executed_statements[0])
        assert "ORDER BY vehicles.delivery_date DESC" in sql
        assert "vehicles.delivery_date IS NOT NULL" in sql


class TestNonDistribuidorNonSuperadminGets403BeforeAnyDbRead:
    def test_jefe_taller_gets_403_with_no_db_touch(self):
        async def _get_db():
            yield NoTouchSession()

        app.dependency_overrides[get_db] = _get_db

        async def _get_current_user():
            return make_jefe_taller()

        app.dependency_overrides[get_current_user] = _get_current_user

        try:
            with TestClient(app) as client:
                res = client.get("/api/v1/distributor/deliveries")
            assert res.status_code == 403
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_current_user, None)
