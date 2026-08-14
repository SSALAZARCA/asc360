"""
tests/orders/test_reception_email_dispatch_wiring.py -- RED/GREEN for
`create_service_order`'s `BackgroundTasks` wiring
(`sdd/reception-email-notification` Phase 6, design ADR 2/ADR 5/ADR 6).

`background_tasks: BackgroundTasks = None` mirrors the exact
default-`None` precedent already used at `imports.py:1418`
(`run_detection_bg`) so every pre-existing direct-call test for this
endpoint -- which never passes `background_tasks` -- keeps returning 201
unaffected. A REAL `fastapi.BackgroundTasks()` instance is used here
(not a mock) so the assertions inspect the actual scheduled
`BackgroundTask.func/args/kwargs` the way FastAPI itself would run it
after the response.

Per BR4, the two PDF-regeneration call sites (`orders.py:2011`, `:2168`)
and `historical_order_service.py:590` must never schedule this task --
asserted here by construction: none of those code paths take a
`background_tasks` parameter at all, so there is no way for them to call
`.add_task(dispatch_reception_email, ...)`.
"""
import uuid

import pytest
from fastapi import BackgroundTasks

from app.api.v1 import orders as orders_module
from app.models.order import ServiceOrder, ServiceOrderReception, OrderHistory, ServiceType
from app.models.tenant import Tenant
from app.models.user import Role, User
from app.models.vehicle import Vehicle
from app.schemas.order import OrderCreate, ReceptionBase
from app.services.reception_email_dispatch import dispatch_reception_email


class _ClaimQueryResult:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class FakeCreateOrderSessionWithClient:
    """Same call shape as `tests/orders/test_create_order_otp_toggle.py`'s
    `FakeCreateOrderSession`, extended to also resolve a `User` (client)
    row for `db.get(User, order_in.client_id)` -- that toggle-test fake
    always returns `None` there (no client in its scenarios), which this
    endpoint's email-scheduling branch specifically needs to exercise."""

    def __init__(self, vehicle: Vehicle, tenant: Tenant, client=None, claim_row=None):
        self._vehicle = vehicle
        self._tenant = tenant
        self._client = client
        self._claim_row = claim_row
        self.added: list = []
        self.commits = 0

    async def get(self, model, pk):
        if model is Vehicle:
            return self._vehicle
        if model is Tenant:
            return self._tenant
        if model is User:
            return self._client
        return None  # SystemConfig("require_otp") -> defaults to OTP required

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

    async def commit(self):
        self.commits += 1

    async def execute(self, stmt):
        if len(stmt.column_descriptions) == 2:
            return _ClaimQueryResult(self._claim_row)

        order = next(o for o in self.added if isinstance(o, ServiceOrder))
        order.reception = next((o for o in self.added if isinstance(o, ServiceOrderReception)), None)
        order.vehicle = self._vehicle
        order.work_logs = []
        order.parts = []

        class _Result:
            def scalar_one(self_inner):
                return order

        return _Result()

    def added_of(self, cls):
        return [o for o in self.added if isinstance(o, cls)]


async def _fake_pdf(order_data, reception_data, vehicle_data, client_data, tenant_data):
    return "https://minio.test/fake.pdf"


@pytest.fixture
def vehicle_and_tenant():
    vehicle = Vehicle(id=uuid.uuid4(), plate="ABC12D", brand="UM", model="TEST")
    tenant = Tenant(id=uuid.uuid4(), name="Taller Test", subdomain="test", tenant_type="service_center")
    return vehicle, tenant


def _order_payload(vehicle_id, tenant_id, client_id=None) -> OrderCreate:
    return OrderCreate(
        tenant_id=tenant_id,
        vehicle_id=vehicle_id,
        client_id=client_id,
        service_type=ServiceType.regular,
        reception=ReceptionBase(mileage_km=1000),
    )


class TestScheduledWhenEmailPresent:
    async def test_task_scheduled_with_correct_kwargs(self, monkeypatch, vehicle_and_tenant):
        vehicle, tenant = vehicle_and_tenant
        monkeypatch.setattr(orders_module, "generate_and_upload_reception_pdf", _fake_pdf)

        client_id = uuid.uuid4()
        client = User(
            id=client_id, name="Juan Pérez", role=Role.client, email="juan@example.com", phone="3000000000",
        )
        session = FakeCreateOrderSessionWithClient(vehicle, tenant, client=client)
        order_in = _order_payload(vehicle.id, tenant.id, client_id=client_id)
        bg = BackgroundTasks()

        result = await orders_module.create_service_order(
            order_in, db=session, x_sonia_secret="test-bot-secret", current_user=None, background_tasks=bg,
        )

        assert len(bg.tasks) == 1
        task = bg.tasks[0]
        assert task.func is dispatch_reception_email
        assert task.kwargs["plate"] == "ABC12D"
        assert task.kwargs["tenant_id"] == tenant.id
        assert task.kwargs["recipient"] == "juan@example.com"
        assert task.kwargs["client_name"] == "Juan Pérez"
        assert task.kwargs["pdf_url"] == "https://minio.test/fake.pdf"
        assert task.kwargs["order_id"] == str(result.id)


class TestNotScheduledWhenEmailMissing:
    async def test_no_task_scheduled_when_client_email_is_empty(self, monkeypatch, vehicle_and_tenant):
        vehicle, tenant = vehicle_and_tenant
        monkeypatch.setattr(orders_module, "generate_and_upload_reception_pdf", _fake_pdf)

        client_id = uuid.uuid4()
        client = User(id=client_id, name="Juan Pérez", role=Role.client, email=None, phone="3000000000")
        session = FakeCreateOrderSessionWithClient(vehicle, tenant, client=client)
        order_in = _order_payload(vehicle.id, tenant.id, client_id=client_id)
        bg = BackgroundTasks()

        await orders_module.create_service_order(
            order_in, db=session, x_sonia_secret="test-bot-secret", current_user=None, background_tasks=bg,
        )

        assert bg.tasks == []

    async def test_no_task_scheduled_when_there_is_no_client(self, monkeypatch, vehicle_and_tenant):
        vehicle, tenant = vehicle_and_tenant
        monkeypatch.setattr(orders_module, "generate_and_upload_reception_pdf", _fake_pdf)

        session = FakeCreateOrderSessionWithClient(vehicle, tenant, client=None)
        order_in = _order_payload(vehicle.id, tenant.id, client_id=None)
        bg = BackgroundTasks()

        await orders_module.create_service_order(
            order_in, db=session, x_sonia_secret="test-bot-secret", current_user=None, background_tasks=bg,
        )

        assert bg.tasks == []


class TestBackgroundTasksNoneStillWorks:
    async def test_default_none_background_tasks_returns_normally(self, monkeypatch, vehicle_and_tenant):
        """Direct-call test compatibility: the ~10 pre-existing tests that
        call `create_service_order` without a `background_tasks` argument
        must keep working -- the parameter defaults to `None`, mirroring
        `imports.py:1418`."""
        vehicle, tenant = vehicle_and_tenant
        monkeypatch.setattr(orders_module, "generate_and_upload_reception_pdf", _fake_pdf)

        client_id = uuid.uuid4()
        client = User(id=client_id, name="Juan Pérez", role=Role.client, email="juan@example.com")
        session = FakeCreateOrderSessionWithClient(vehicle, tenant, client=client)
        order_in = _order_payload(vehicle.id, tenant.id, client_id=client_id)

        # No `background_tasks` kwarg passed at all.
        result = await orders_module.create_service_order(
            order_in, db=session, x_sonia_secret="test-bot-secret", current_user=None,
        )

        assert result is not None
