"""
tests/orders/test_create_order_otp_toggle.py — `create_service_order`'s new
`require_otp` branch (network-wide switch, `SystemConfig` key `require_otp`).

Calls `create_service_order` directly as a plain async function (not through
`TestClient`/FastAPI DI) — it takes `db`/`x_sonia_secret`/`current_user` as
plain arguments, so there's no need to fake the whole request/response
pipeline. This also sidesteps `response_model=OrderRead` validation, which
only applies when FastAPI itself serializes the response, not on a direct
call — the returned object's shape doesn't need to satisfy that schema here.

`generate_and_upload_reception_pdf` is monkeypatched (real MinIO/WeasyPrint
work, irrelevant to the branch under test).
"""
import uuid
from datetime import datetime

import pytest

from app.api.v1 import orders as orders_module
from app.models.order import ServiceOrder, ServiceOrderReception, OrderHistory, ServiceStatus, ServiceType
from app.models.system_config import SystemConfig
from app.models.vehicle import Vehicle
from app.models.tenant import Tenant
from app.schemas.order import OrderCreate, ReceptionBase


class FakeCreateOrderSession:
    """Minimal fake covering exactly the calls `create_service_order` makes:
    one `db.get(SystemConfig, "require_otp")` read, `db.get` for
    Vehicle/User/Tenant metadata, `db.add`/`db.flush`/`db.commit` (flush
    assigns a real `id` to added rows lacking one — bare ORM construction
    doesn't trigger the column `default=`, same quirk documented in
    `tests/orders/conftest.py`), and the final re-`select` refetch."""

    def __init__(self, require_otp_value: str | None, vehicle: Vehicle, tenant: Tenant):
        self._require_otp_value = require_otp_value
        self._vehicle = vehicle
        self._tenant = tenant
        self.added: list = []
        self.commits = 0

    async def get(self, model, pk):
        if model is SystemConfig:
            if self._require_otp_value is None:
                return None
            return SystemConfig(key="require_otp", value=self._require_otp_value)
        if model is Vehicle:
            return self._vehicle
        if model is Tenant:
            return self._tenant
        return None  # User (no client_id in these tests)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

    async def commit(self):
        self.commits += 1

    async def execute(self, stmt):
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


def _order_payload(vehicle_id, tenant_id) -> OrderCreate:
    return OrderCreate(
        tenant_id=tenant_id,
        vehicle_id=vehicle_id,
        service_type=ServiceType.regular,
        reception=ReceptionBase(mileage_km=1000),
    )


@pytest.fixture
def vehicle_and_tenant():
    # sdd/vehicle-tenant-checkin-release PR2: `Vehicle` no longer has a
    # `tenant_id` column/attribute (PR1 unmapped it).
    vehicle = Vehicle(id=uuid.uuid4(), plate="ABC12D", brand="UM", model="TEST")
    tenant = Tenant(id=uuid.uuid4(), name="Taller Test", subdomain="test", tenant_type="service_center")
    return vehicle, tenant


@pytest.mark.parametrize("require_otp_value", [None, "true"])
async def test_create_order_otp_required_unchanged_behavior(monkeypatch, vehicle_and_tenant, require_otp_value):
    """Absent row or explicit "true" -> byte-for-byte today's behavior:
    pending_signature, no bypass fields set."""
    vehicle, tenant = vehicle_and_tenant
    monkeypatch.setattr(orders_module, "generate_and_upload_reception_pdf", _fake_pdf)

    session = FakeCreateOrderSession(require_otp_value, vehicle, tenant)
    order_in = _order_payload(vehicle.id, tenant.id)

    await orders_module.create_service_order(
        order_in, db=session, x_sonia_secret="test-bot-secret", current_user=None
    )

    [order] = session.added_of(ServiceOrder)
    [reception] = session.added_of(ServiceOrderReception)
    [history] = session.added_of(OrderHistory)

    assert order.status == ServiceStatus.pending_signature
    assert reception.bypass_at is None
    assert reception.bypass_by_id is None
    assert reception.bypass_by_name is None
    assert history.to_status == ServiceStatus.pending_signature
    assert history.comments is None


async def test_create_order_otp_disabled_skips_straight_to_received(monkeypatch, vehicle_and_tenant):
    vehicle, tenant = vehicle_and_tenant
    monkeypatch.setattr(orders_module, "generate_and_upload_reception_pdf", _fake_pdf)

    session = FakeCreateOrderSession("false", vehicle, tenant)
    order_in = _order_payload(vehicle.id, tenant.id)

    await orders_module.create_service_order(
        order_in, db=session, x_sonia_secret="test-bot-secret", current_user=None
    )

    [order] = session.added_of(ServiceOrder)
    [reception] = session.added_of(ServiceOrderReception)
    [history] = session.added_of(OrderHistory)

    assert order.status == ServiceStatus.received
    assert reception.bypass_at is not None
    assert isinstance(reception.bypass_at, datetime)
    assert reception.bypass_by_id is None
    assert reception.bypass_by_name == "Sistema (OTP desactivado en Configuración)"
    assert history.to_status == ServiceStatus.received
    assert history.comments == "Orden creada sin OTP — desactivado en Configuración"


async def test_create_order_otp_disabled_passes_bypass_stamp_to_initial_pdf(monkeypatch, vehicle_and_tenant):
    """The reception PDF generated at creation time must show the same
    bypass stamp the manual `/otp/bypass` regeneration uses — otherwise the
    document handed to the client at intake looks unsigned."""
    vehicle, tenant = vehicle_and_tenant
    captured = {}

    async def _capture_pdf(order_data, reception_data, vehicle_data, client_data, tenant_data):
        captured.update(order_data)
        return "https://minio.test/fake.pdf"

    monkeypatch.setattr(orders_module, "generate_and_upload_reception_pdf", _capture_pdf)

    session = FakeCreateOrderSession("false", vehicle, tenant)
    order_in = _order_payload(vehicle.id, tenant.id)

    await orders_module.create_service_order(
        order_in, db=session, x_sonia_secret="test-bot-secret", current_user=None
    )

    assert captured.get("bypass_by_name") == "Sistema (OTP desactivado en Configuración)"
    assert "bypass_at" in captured


async def _fake_pdf(order_data, reception_data, vehicle_data, client_data, tenant_data):
    return "https://minio.test/fake.pdf"
