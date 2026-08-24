"""
tests/distributor_deliveries/test_export_deliveries.py — `GET
/distributor/deliveries/export`.

Reuses the exact same `_scoped_delivery_vehicles_query` visibility rule as
`list_deliveries` (see `test_list_deliveries.py`'s header note) -- these
tests compile the emitted SQL to prove the tenant filter is actually
applied, `FakeDeliverySession` ignores `.where()` clauses when returning its
canned row list so a response-shape-only assertion could not tell filtered
code from unfiltered code apart.
"""
import io
import uuid
from datetime import date

import openpyxl
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db
from app.api.deps import get_current_user
from app.services import distributor_delivery_service as svc

from tests.distributor_deliveries.conftest import (
    FakeDeliverySession,
    NoTouchSession,
    make_administrativo,
    make_client_user,
    make_delivery_vehicle,
    make_distribuidor,
    make_jefe_taller,
    make_superadmin,
    make_tenant,
)


def _compiled_sql(stmt) -> str:
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


def _rows(buf: io.BytesIO):
    wb = openpyxl.load_workbook(io.BytesIO(buf.getvalue()))
    ws = wb.active
    return list(ws.iter_rows(values_only=True))


class TestDistribuidorSeesOnlyTheirOwnTenant:
    async def test_where_clause_scopes_by_registered_by_tenant_id(self):
        tenant_id = uuid.uuid4()
        fake_db = FakeDeliverySession()
        actor = make_distribuidor(tenant_id=tenant_id)

        await svc.export_deliveries(fake_db, actor)

        sql = _compiled_sql(fake_db.executed_statements[0])
        assert "vehicles.delivery_date IS NOT NULL" in sql
        assert "vehicles.registered_by_tenant_id =" in sql
        assert tenant_id.hex in sql.replace("-", "")


class TestDistribuidorWithNoTenantAssignedGetsEmptyExportWithoutTouchingDb:
    async def test_no_tenant_assigned_returns_headers_only_without_touching_db(self):
        actor = make_distribuidor(tenant_id=None)
        fake_db = NoTouchSession()

        buf = await svc.export_deliveries(fake_db, actor)

        rows = _rows(buf)
        assert len(rows) == 1
        assert rows[0] == tuple(svc.EXPORT_HEADERS)


class TestSuperadminSeesAllTenants:
    async def test_no_tenant_filter_applied_in_the_query(self):
        fake_db = FakeDeliverySession()
        actor = make_superadmin()

        await svc.export_deliveries(fake_db, actor)

        sql = _compiled_sql(fake_db.executed_statements[0])
        assert "registered_by_tenant_id =" not in sql


class TestAdministrativoSeesAllTenants:
    """2026-08-24 business decision: administrativo behaves EXACTLY like
    superadmin here -- network-wide visibility, not tenant-scoped."""

    async def test_no_tenant_filter_applied_in_the_query(self):
        fake_db = FakeDeliverySession()
        actor = make_administrativo()

        await svc.export_deliveries(fake_db, actor)

        sql = _compiled_sql(fake_db.executed_statements[0])
        assert "registered_by_tenant_id =" not in sql


class TestExportRowContent:
    async def test_full_record_maps_every_client_and_vehicle_field(self):
        tenant_id = uuid.uuid4()
        tenant = make_tenant(name="Distribuidora Norte", tenant_id=tenant_id)
        client = make_client_user(
            name="Juan Perez",
            identification="900555111",
            phone="3001112233",
        )
        client.email = "juan@example.com"
        client.birth_date = date(1990, 5, 10)
        client.city = "Bogotá"
        client.department = "Cundinamarca"
        client.address = "Calle 1 # 2-3"
        vehicle = make_delivery_vehicle(
            plate="ABC123",
            vin="1HGCM82633A004352",
            model="DSR",
            color="Rojo",
            year=2026,
            delivery_date=date(2026, 7, 20),
            client=client,
            registered_by_tenant_id=tenant_id,
            registered_by_tenant=tenant,
        )
        vehicle.engine_number = "ENG12345"
        vehicle.delivery_act_url = "https://minio.local/acta.jpg"
        fake_db = FakeDeliverySession(vehicles=[vehicle])
        actor = make_superadmin()

        buf = await svc.export_deliveries(fake_db, actor)

        rows = _rows(buf)
        assert len(rows) == 2
        assert rows[1] == (
            "Juan Perez", "900555111", "1990-05-10", "3001112233", "juan@example.com",
            "Bogotá", "Cundinamarca", "Calle 1 # 2-3",
            "ABC123", "1HGCM82633A004352", "DSR", "Rojo", 2026, "ENG12345",
            "2026-07-20", "Distribuidora Norte", "Sí",
        )

    async def test_vehicle_with_no_client_link_has_blank_client_columns(self):
        tenant_id = uuid.uuid4()
        vehicle = make_delivery_vehicle(
            plate="NOCLIENT1", delivery_date=date(2026, 7, 5), registered_by_tenant_id=tenant_id
        )
        fake_db = FakeDeliverySession(vehicles=[vehicle])
        actor = make_distribuidor(tenant_id=tenant_id)

        buf = await svc.export_deliveries(fake_db, actor)

        rows = _rows(buf)
        # openpyxl round-trips written "" cells as `None` on read -- the
        # cell renders blank in Excel either way, that's the behavior that
        # actually matters, not the exact Python sentinel.
        assert rows[1][0:8] == (None,) * 8

    async def test_distribuidor_export_never_shows_distribuidora_name(self):
        """Mirrors `list_deliveries`'s own rule -- a Distribuidor's filtered
        view never needs/exposes the Distribuidora name column, they only
        ever see their own tenant anyway."""
        tenant_id = uuid.uuid4()
        tenant = make_tenant(name="Distribuidora Norte", tenant_id=tenant_id)
        vehicle = make_delivery_vehicle(
            plate="ABC123", delivery_date=date(2026, 7, 20),
            registered_by_tenant_id=tenant_id, registered_by_tenant=tenant,
        )
        fake_db = FakeDeliverySession(vehicles=[vehicle])
        actor = make_distribuidor(tenant_id=tenant_id)

        buf = await svc.export_deliveries(fake_db, actor)

        rows = _rows(buf)
        assert rows[1][15] is None  # Distribuidora column (openpyxl "" -> None round-trip)


class TestDeliveryActUrlNeverExposedRaw:
    async def test_act_present_shows_si_not_the_url(self):
        tenant_id = uuid.uuid4()
        vehicle = make_delivery_vehicle(
            plate="WITHACT1", delivery_date=date(2026, 7, 5), registered_by_tenant_id=tenant_id
        )
        vehicle.delivery_act_url = "https://minio.local/acta.jpg"
        fake_db = FakeDeliverySession(vehicles=[vehicle])
        actor = make_distribuidor(tenant_id=tenant_id)

        buf = await svc.export_deliveries(fake_db, actor)

        rows = _rows(buf)
        assert rows[1][16] == "Sí"
        for row in rows:
            for cell in row:
                assert cell != "https://minio.local/acta.jpg"

    async def test_act_absent_shows_no(self):
        tenant_id = uuid.uuid4()
        vehicle = make_delivery_vehicle(
            plate="NOACT1", delivery_date=date(2026, 7, 5), registered_by_tenant_id=tenant_id
        )
        fake_db = FakeDeliverySession(vehicles=[vehicle])
        actor = make_distribuidor(tenant_id=tenant_id)

        buf = await svc.export_deliveries(fake_db, actor)

        rows = _rows(buf)
        assert rows[1][16] == "No"


class TestEmptyResultStillProducesValidHeaderedWorkbook:
    async def test_superadmin_with_zero_deliveries_gets_headers_only(self):
        fake_db = FakeDeliverySession(vehicles=[])
        actor = make_superadmin()

        buf = await svc.export_deliveries(fake_db, actor)

        rows = _rows(buf)
        assert rows == [tuple(svc.EXPORT_HEADERS)]


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
                res = client.get("/api/v1/distributor/deliveries/export")
            assert res.status_code == 403
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_current_user, None)


class TestExportRouteRespondsBeforeVehicleIdRoute:
    """The router registers `GET /deliveries/export` BEFORE `GET
    /deliveries/{vehicle_id}` -- if this were reversed, FastAPI would try to
    parse "export" as a UUID path param and 422 instead of running the
    export."""

    def test_export_route_returns_xlsx_not_a_uuid_parse_error(self):
        fake_db = FakeDeliverySession()

        async def _get_db():
            yield fake_db

        app.dependency_overrides[get_db] = _get_db

        async def _get_current_user():
            return make_superadmin()

        app.dependency_overrides[get_current_user] = _get_current_user

        try:
            with TestClient(app) as client:
                res = client.get("/api/v1/distributor/deliveries/export")
            assert res.status_code == 200
            assert res.headers["content-type"] == (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            assert "entregas_registradas_" in res.headers["content-disposition"]
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_current_user, None)
