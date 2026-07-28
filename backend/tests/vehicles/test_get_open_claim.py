"""
RED/GREEN tests for `vehicle_repository.get_open_claim`
(`sdd/vehicle-tenant-checkin-release`, PR 1: migration + models +
repository claim primitives).

`get_open_claim` resolves *who* currently holds a vehicle -- the most
recent ServiceOrder in a non-releasing status, joined to its Tenant. It is
NOT tenant-scoped (answers "who has it", not "can tenant T see it" -- that
is `visible_to_tenant`'s job).

Uses `FakeClaimSession` (`tests/vehicles/conftest.py`), mirroring
`tests/orders/conftest.py`'s fake-session-with-statement-inspection
convention -- no live DB.
"""
import uuid
from datetime import datetime
from types import SimpleNamespace

from app.models.order import ServiceStatus
from app.repositories.vehicle_repository import VehicleClaim, get_open_claim

from tests.vehicles.conftest import FakeClaimSession


def make_order_row(
    order_id=None, status=ServiceStatus.in_progress, created_at=None
):
    return SimpleNamespace(
        id=order_id or uuid.uuid4(),
        status=status,
        created_at=created_at or datetime.utcnow(),
    )


def make_tenant_row(tenant_id=None, name="Taller A", ciudad="Bogotá"):
    return SimpleNamespace(id=tenant_id or uuid.uuid4(), name=name, ciudad=ciudad)


class TestGetOpenClaimFound:
    async def test_returns_a_vehicle_claim_built_from_the_joined_row(self):
        order = make_order_row(status=ServiceStatus.in_progress)
        tenant = make_tenant_row(name="Taller A", ciudad="Bogotá")
        fake_db = FakeClaimSession(row=(order, tenant))

        claim = await get_open_claim(fake_db, uuid.uuid4())

        assert isinstance(claim, VehicleClaim)
        assert claim.tenant_id == tenant.id
        assert claim.tenant_name == "Taller A"
        assert claim.tenant_city == "Bogotá"
        assert claim.order_id == order.id
        assert claim.status == "in_progress"
        assert claim.since == order.created_at


class TestGetOpenClaimNotFound:
    async def test_returns_none_when_no_open_order_exists(self):
        fake_db = FakeClaimSession(row=None)

        claim = await get_open_claim(fake_db, uuid.uuid4())

        assert claim is None


class TestGetOpenClaimCompiledSQL:
    async def test_where_excludes_releasing_statuses_and_filters_by_vehicle_id(self):
        vehicle_id = uuid.uuid4()
        fake_db = FakeClaimSession(row=None)

        await get_open_claim(fake_db, vehicle_id)

        assert len(fake_db.executed_statements) == 1
        sql = str(
            fake_db.executed_statements[0].compile(
                compile_kwargs={"literal_binds": True}
            )
        )
        assert "service_orders.vehicle_id" in sql
        assert vehicle_id.hex in sql.replace("-", "")
        assert "service_orders.status NOT IN" in sql
        assert "'delivered'" in sql
        assert "'cancelled'" in sql
        assert "'completed'" not in sql
        assert "ORDER BY" in sql
        assert "service_orders.created_at DESC" in sql
        assert "LIMIT" in sql
        assert "tenants" in sql  # joined to Tenant

    async def test_exclude_order_id_adds_an_extra_predicate(self):
        vehicle_id = uuid.uuid4()
        order_id = uuid.uuid4()
        fake_db = FakeClaimSession(row=None)

        await get_open_claim(fake_db, vehicle_id, exclude_order_id=order_id)

        sql = str(
            fake_db.executed_statements[0].compile(
                compile_kwargs={"literal_binds": True}
            )
        )
        assert "service_orders.id !=" in sql
        assert order_id.hex in sql.replace("-", "")

    async def test_no_exclude_order_id_omits_the_extra_predicate(self):
        vehicle_id = uuid.uuid4()
        fake_db = FakeClaimSession(row=None)

        await get_open_claim(fake_db, vehicle_id)

        sql = str(
            fake_db.executed_statements[0].compile(
                compile_kwargs={"literal_binds": True}
            )
        )
        assert "service_orders.id !=" not in sql
