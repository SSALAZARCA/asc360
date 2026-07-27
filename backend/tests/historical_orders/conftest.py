"""
Shared fixtures for `historical_orders` tests — follows the project's
established fake-`AsyncSession` convention (see `tests/superadmin_data/
conftest.py`, `tests/orders/conftest.py`).

PR1 only needed a minimal double (the router stub guarded then 501ed
before touching the database). PR2 wires the real transactional service
(`historical_order_service.create_historical_order`), which composes
several existing read/write paths on the SAME session:
  - `select(User)`      -- client lookup (`_lookup_or_create_client`)
  - `select(Vehicle)`   -- `vehicle_repository.get_by_plate` (inside
                           `vehicle_service.register_or_update_vehicle`)
  - `select(ShipmentMotoUnit)` -- `vin_master_service.query_vin` (inside
                           `register_or_update_vehicle`'s VIN enrichment)
  - `select(ServiceOrder)` -- the plate+date duplicate check
  - `db.get(Tenant, ...)` -- PDF context lookup

`FakeHistoricalOrderSession` dispatches `execute()` by the statement's
target entity (mirrors `tests.superadmin_data.conftest.FakeOrderSession`),
not by call order, since the production service may or may not issue any
given query depending on the payload (e.g. a phone-less client skips the
User lookup entirely).
"""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser


def make_superadmin() -> CurrentUser:
    return CurrentUser(user_id=str(uuid.uuid4()), role="superadmin", tenant_id=None, name="Super")


def make_jefe_taller() -> CurrentUser:
    return CurrentUser(
        user_id=str(uuid.uuid4()),
        role="jefe_taller",
        tenant_id=str(uuid.uuid4()),
        name="Jefe",
    )


class NoTouchSession:
    """Fake DB session that fails the test if the route touches it at all.

    Only legitimate for guard-rejection paths (403/401) that short-circuit
    before the service is ever called."""

    async def execute(self, *args, **kwargs):
        raise AssertionError("route touched db.execute() before the guard short-circuited")

    async def get(self, *args, **kwargs):
        raise AssertionError("route touched db.get() before the guard short-circuited")

    def add(self, *args, **kwargs):
        raise AssertionError("route touched db.add() before the guard short-circuited")

    async def commit(self, *args, **kwargs):
        raise AssertionError("route touched db.commit() before the guard short-circuited")

    async def rollback(self, *args, **kwargs):
        raise AssertionError("route touched db.rollback() before the guard short-circuited")

    async def delete(self, *args, **kwargs):
        raise AssertionError("route touched db.delete() before the guard short-circuited")


VALID_HISTORICAL_ORDER_PAYLOAD = {
    "tenant_id": str(uuid.uuid4()),
    "vehicle": {"plate": "ABC123", "vin": None, "brand": "UM", "model": "DSR", "year": 2024, "color": "Rojo"},
    "client": {"name": "Juan Perez", "phone": "3001234567"},
    "service_type": "regular",
    "status": "received",
    "mileage_km": "1000",
    "created_at": "2025-01-10T09:00:00",
    "completed_at": None,
    "delivered_at": None,
    "customer_notes": None,
    "diagnosis": None,
    "general_observations": None,
    "technician_id": None,
    "acknowledge_duplicate": False,
}


# ---------------------------------------------------------------------------
# ORM row factories
# ---------------------------------------------------------------------------

def make_tenant(
    tenant_id: Optional[uuid.UUID] = None,
    name: str = "Taller Central",
    nit: str = "900123456-1",
    phone: str = "3000000000",
    ciudad: str = "Bogotá",
):
    from app.models.tenant import Tenant, TenantType
    return Tenant(
        id=tenant_id or uuid.uuid4(),
        name=name,
        subdomain=name.lower().replace(" ", "-"),
        nit=nit,
        phone=phone,
        tenant_type=TenantType.service_center,
        ciudad=ciudad,
        has_sales=False,
        has_parts=False,
        has_service=True,
    )


def make_client_user(
    user_id: Optional[uuid.UUID] = None,
    tenant_id: Optional[uuid.UUID] = None,
    name: str = "Juan Perez",
    phone: Optional[str] = "3001234567",
):
    from app.models.user import User, Role, UserStatus
    return User(
        id=user_id or uuid.uuid4(),
        tenant_id=tenant_id or uuid.uuid4(),
        name=name,
        phone=phone,
        role=Role.client,
        status=UserStatus.active,
        telegram_id=None,
    )


def make_vehicle(
    vehicle_id: Optional[uuid.UUID] = None,
    plate: str = "ABC123",
    vin: Optional[str] = "VIN0001",
    brand: str = "UM",
    model: str = "DSR",
    color: Optional[str] = "Rojo",
    year: Optional[int] = 2024,
    tenant_id: Optional[uuid.UUID] = None,
):
    from app.models.vehicle import Vehicle
    return Vehicle(
        id=vehicle_id or uuid.uuid4(),
        tenant_id=tenant_id or uuid.uuid4(),
        plate=plate,
        vin=vin,
        brand=brand,
        model=model,
        color=color,
        year=year,
        mileage=0,
    )


def make_moto_unit(**overrides):
    """Mirrors `tests/vehicles/test_vin_master_lookup.py`'s helper of the
    same name — a `ShipmentMotoUnit` row real enough for
    `vin_master_service.query_vin` to resolve against."""
    from app.models.imports import ShipmentMotoUnit
    unit = ShipmentMotoUnit(
        id=uuid.uuid4(),
        shipment_order_id=uuid.uuid4(),
        vin_number="9C6JC5820PM123456",
        engine_number="ENG-001",
        model="Renegade 200",
        model_year=2024,
        color="Rojo",
        color_runt="Rojo",
    )
    unit.shipment_order = None
    for k, v in overrides.items():
        setattr(unit, k, v)
    return unit


def make_existing_order(
    order_id: Optional[uuid.UUID] = None,
    vehicle_id: Optional[uuid.UUID] = None,
    created_at: Optional[datetime] = None,
    status=None,
):
    from app.models.order import ServiceOrder, ServiceStatus
    return ServiceOrder(
        id=order_id or uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        vehicle_id=vehicle_id or uuid.uuid4(),
        status=status or ServiceStatus.delivered,
        service_type=None,
        created_at=created_at or datetime(2025, 1, 10, 8, 0),
    )


# ---------------------------------------------------------------------------
# Fake AsyncSession
# ---------------------------------------------------------------------------

class _ScalarsResult:
    def __init__(self, items: list):
        self._items = list(items)

    def first(self):
        return self._items[0] if self._items else None

    def all(self):
        return list(self._items)


class _ExecuteResult:
    def __init__(self, items: list):
        self._items = list(items)

    def scalars(self):
        return _ScalarsResult(self._items)

    def scalar_one_or_none(self):
        return self._items[0] if self._items else None


class FakeHistoricalOrderSession:
    """
    Minimal fake `AsyncSession` for `historical_order_service.
    create_historical_order`.

    - `users`: rows returned for the client lookup `select(User)` query.
    - `vehicles`: rows returned for `vehicle_repository.get_by_plate`'s
      `select(Vehicle)` query (empty -> a new Vehicle is created).
    - `moto_units`: rows returned for `vin_master_service.query_vin`'s
      `select(ShipmentMotoUnit)` query (VIN enrichment).
    - `existing_orders`: rows returned for the duplicate-check
      `select(ServiceOrder)` query.
    - `tenant`: returned by `db.get(Tenant, tenant_id)` for the PDF step.
    - `raise_integrity_error` / `raise_generic_error`: the FIRST `commit()`
      raises the corresponding exception (simulates a DB-level conflict or
      an unexpected failure) -- `rollback()` records it and discards
      pending `add()`s, mirroring a real `AsyncSession.rollback()`.
    """

    def __init__(
        self,
        users: Optional[list] = None,
        vehicles: Optional[list] = None,
        moto_units: Optional[list] = None,
        existing_orders: Optional[list] = None,
        tenant=None,
        raise_integrity_error: bool = False,
        raise_generic_error: bool = False,
    ):
        self._users = list(users or [])
        self._vehicles = list(vehicles or [])
        self._moto_units = list(moto_units or [])
        self._existing_orders = list(existing_orders or [])
        self._tenant = tenant
        self._raise_integrity_error = raise_integrity_error
        self._raise_generic_error = raise_generic_error

        self.added: list = []
        self.committed = False
        self.rolled_back = False

    async def execute(self, stmt):
        from app.models.user import User
        from app.models.vehicle import Vehicle
        from app.models.order import ServiceOrder
        from app.models.imports import ShipmentMotoUnit

        entity = stmt.column_descriptions[0]["entity"]
        if entity is User:
            return _ExecuteResult(self._users)
        if entity is Vehicle:
            return _ExecuteResult(self._vehicles)
        if entity is ShipmentMotoUnit:
            return _ExecuteResult(self._moto_units)
        if entity is ServiceOrder:
            return _ExecuteResult(self._existing_orders)
        return _ExecuteResult([])

    async def get(self, model_cls, obj_id):
        from app.models.tenant import Tenant
        if model_cls is Tenant:
            return self._tenant
        return None

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

    async def refresh(self, obj, attribute_names=None):
        pass

    async def commit(self):
        if self._raise_integrity_error:
            self._raise_integrity_error = False
            raise IntegrityError("INSERT service_orders", {}, Exception("duplicate key value"))
        if self._raise_generic_error:
            self._raise_generic_error = False
            raise RuntimeError("boom — unexpected failure at commit time")
        self.committed = True

    async def rollback(self):
        self.rolled_back = True
