"""
Shared fixtures for `distributor_deliveries` tests — follows the project's
established fake-`CurrentUser`/`NoTouchSession` convention (see
`tests/historical_orders/conftest.py`, `tests/superadmin_data/
test_role_guard_regression.py`).

Phase 3 needed only a minimal double: the router stub in
`app/api/v1/distributor_deliveries.py` guarded then 501ed before touching
the database, and the schema/model contract test doesn't touch a session at
all. Phase 4 (this batch) adds `FakeDeliverySession`, mirroring
`FakeHistoricalOrderSession`, alongside the real transactional service.
"""
import json
import uuid
from typing import Optional

from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser


def make_distribuidor(tenant_id: Optional[uuid.UUID] = None) -> CurrentUser:
    return CurrentUser(
        user_id=str(uuid.uuid4()),
        role="parts_dealer",
        tenant_id=str(tenant_id) if tenant_id else None,
        name="Distribuidor",
    )


def make_superadmin() -> CurrentUser:
    return CurrentUser(user_id=str(uuid.uuid4()), role="superadmin", tenant_id=None, name="Super")


def make_administrativo() -> CurrentUser:
    """2026-08-24 business decision: administrativo behaves EXACTLY like
    superadmin in Registro de Motocicletas -- network-wide visibility,
    optional photo, explicit Tienda selector (no tenant of their own,
    mirroring superadmin's `tenant_id=None`)."""
    return CurrentUser(user_id=str(uuid.uuid4()), role="administrativo", tenant_id=None, name="Administrativo")


def make_jefe_taller() -> CurrentUser:
    return CurrentUser(
        user_id=str(uuid.uuid4()),
        role="jefe_taller",
        tenant_id=str(uuid.uuid4()),
        name="Jefe",
    )


class NoTouchSession:
    """Fake DB session that fails the test if the route touches it at all.

    Phase 3's router body is guard-then-501 — no reads/writes are
    legitimate yet. Mirrors `tests/historical_orders/conftest.py`'s
    `NoTouchSession`."""

    async def execute(self, *args, **kwargs):
        raise AssertionError("route touched db.execute() before the guard/stub short-circuited")

    async def get(self, *args, **kwargs):
        raise AssertionError("route touched db.get() before the guard/stub short-circuited")

    def add(self, *args, **kwargs):
        raise AssertionError("route touched db.add() before the guard/stub short-circuited")

    async def commit(self, *args, **kwargs):
        raise AssertionError("route touched db.commit() before the guard/stub short-circuited")

    async def rollback(self, *args, **kwargs):
        raise AssertionError("route touched db.rollback() before the guard/stub short-circuited")

    async def delete(self, *args, **kwargs):
        raise AssertionError("route touched db.delete() before the guard/stub short-circuited")


class FakeUploadFile:
    """Minimal double for `fastapi.UploadFile` — the service only ever reads
    `.filename`, `.content_type`, and awaits `.read()`."""

    def __init__(self, filename: str, content_type: str, content: bytes):
        self.filename = filename
        self.content_type = content_type
        self._content = content

    async def read(self) -> bytes:
        return self._content


def make_valid_photo() -> FakeUploadFile:
    return FakeUploadFile("acta.jpg", "image/jpeg", b"fake-jpeg-bytes")


VALID_DELIVERY_PAYLOAD = {
    "client": {
        "name": "Juan Perez",
        "identification": "123456789",
        "birth_date": "1990-05-10",
        "city": "Bogotá",
        "department": "Cundinamarca",
        "address": "Calle 1 # 2-3",
        "phone": "3001234567",
        "email": "juan@example.com",
    },
    "vehicle": {
        "plate": "ABC123",
        "vin": "1HGCM82633A004352",
        "model": "DSR",
        "color": "Rojo",
        "year": 2026,
        "engine_number": "ENG12345",
    },
    "delivery_date": "2026-07-28",
}

VALID_DELIVERY_PAYLOAD_JSON = json.dumps(VALID_DELIVERY_PAYLOAD)


# ---------------------------------------------------------------------------
# ORM row factories
# ---------------------------------------------------------------------------

def make_client_user(
    user_id: Optional[uuid.UUID] = None,
    tenant_id: Optional[uuid.UUID] = None,
    name: str = "Juan Perez",
    identification: str = "123456789",
    phone: Optional[str] = "3001234567",
):
    from app.models.user import User, Role, UserStatus
    return User(
        id=user_id or uuid.uuid4(),
        tenant_id=tenant_id,
        name=name,
        phone=phone,
        role=Role.client,
        status=UserStatus.active,
        telegram_id=None,
        identification=identification,
    )


def make_delivery_vehicle(
    vehicle_id: Optional[uuid.UUID] = None,
    plate: str = "ABC123",
    vin: Optional[str] = "1HGCM82633A004352",
    brand: str = "UM",
    model: str = "DSR",
    color: Optional[str] = "Rojo",
    year: Optional[int] = 2026,
    delivery_date=None,
    client=None,
    registered_by_tenant_id: Optional[uuid.UUID] = None,
    registered_by_tenant=None,
):
    from app.models.vehicle import Vehicle
    vehicle = Vehicle(
        id=vehicle_id or uuid.uuid4(),
        plate=plate,
        vin=vin,
        brand=brand,
        model=model,
        color=color,
        year=year,
        mileage=0,
        delivery_date=delivery_date,
        registered_by_tenant_id=registered_by_tenant_id,
    )
    # `.client`/`.registered_by_tenant` are relationship attrs -- set
    # directly here to stand in for what a real `selectinload` would have
    # populated, since `FakeDeliverySession` never runs real SQL joins.
    vehicle.client = client
    vehicle.registered_by_tenant = registered_by_tenant
    return vehicle


def make_tenant(
    tenant_id: Optional[uuid.UUID] = None,
    name: str = "Distribuidora Bogotá",
    nit: str = "900123456-1",
    phone: str = "3000000000",
    ciudad: str = "Bogotá",
):
    """Mirrors `tests/historical_orders/conftest.py`'s helper of the same
    name, but defaults `tenant_type` to `distribuidor` -- these tests are
    exclusively about Distribuidora-scoped delivery records."""
    from app.models.tenant import Tenant, TenantType
    return Tenant(
        id=tenant_id or uuid.uuid4(),
        name=name,
        subdomain=name.lower().replace(" ", "-"),
        nit=nit,
        phone=phone,
        tenant_type=TenantType.distribuidor,
        ciudad=ciudad,
    )


def make_moto_unit(**overrides):
    """Mirrors `tests/historical_orders/conftest.py`'s helper of the same
    name — a `ShipmentMotoUnit` row real enough for
    `vin_master_service.query_vin` to resolve against."""
    from app.models.imports import ShipmentMotoUnit
    unit = ShipmentMotoUnit(
        id=uuid.uuid4(),
        shipment_order_id=uuid.uuid4(),
        vin_number="1HGCM82633A004352",
        engine_number="ENG-001",
        model="DSR",
        model_year=2026,
        color="Rojo",
        color_runt="Rojo",
    )
    unit.shipment_order = None
    for k, v in overrides.items():
        setattr(unit, k, v)
    return unit


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


class FakeDeliverySession:
    """
    Minimal fake `AsyncSession` for `distributor_delivery_service.
    create_delivery`.

    - `users`: rows returned for the client lookup-by-identification
      `select(User)` query.
    - `vehicles`: rows returned for `vehicle_repository.get_by_plate`'s
      `select(Vehicle)` query (empty -> a new Vehicle is created), AND the
      source for `db.get(Vehicle, id)` (the act-photo retry endpoint).
    - `moto_units`: rows returned for `vin_master_service.query_vin`'s
      `select(ShipmentMotoUnit)` query (VIN enrichment AND, follow-up fix
      2026-07-30, the now-mandatory VIN-in-master check on create/edit).
      Defaults (when the argument is omitted entirely, i.e. `None`) to a
      single unit matching `VALID_DELIVERY_PAYLOAD`'s VIN
      ("1HGCM82633A004352") -- most tests in this package submit that
      payload as-is and don't care about VIN-master behavior, so they'd
      otherwise all start failing the new mandatory check. Pass an explicit
      `moto_units=[]` to test the "VIN not found" rejection path.
    - `raise_integrity_error` / `raise_generic_error`: the FIRST `commit()`
      raises the corresponding exception -- `rollback()` records it,
      mirroring a real `AsyncSession.rollback()`.
    """

    def __init__(
        self,
        users: Optional[list] = None,
        vehicles: Optional[list] = None,
        moto_units: Optional[list] = None,
        tenants: Optional[list] = None,
        raise_integrity_error: bool = False,
        raise_generic_error: bool = False,
    ):
        self._users = list(users or [])
        self._vehicles = list(vehicles or [])
        self._moto_units = [make_moto_unit()] if moto_units is None else list(moto_units)
        self._tenants = list(tenants or [])
        self._raise_integrity_error = raise_integrity_error
        self._raise_generic_error = raise_generic_error

        self.added: list = []
        self.committed = False
        self.rolled_back = False
        self.executed_statements: list = []

    async def execute(self, stmt):
        from app.models.user import User
        from app.models.vehicle import Vehicle
        from app.models.imports import ShipmentMotoUnit

        self.executed_statements.append(stmt)

        entity = stmt.column_descriptions[0]["entity"]
        if entity is User:
            return _ExecuteResult(self._users)
        if entity is Vehicle:
            return _ExecuteResult(self._vehicles)
        if entity is ShipmentMotoUnit:
            return _ExecuteResult(self._moto_units)
        return _ExecuteResult([])

    async def get(self, model_cls, obj_id):
        from app.models.user import User
        from app.models.vehicle import Vehicle
        from app.models.tenant import Tenant
        if model_cls is Vehicle:
            return next((v for v in self._vehicles if v.id == obj_id), None)
        if model_cls is User:
            return next((u for u in self._users if u.id == obj_id), None)
        if model_cls is Tenant:
            return next((t for t in self._tenants if t.id == obj_id), None)
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
            raise IntegrityError("INSERT vehicles", {}, Exception("duplicate key value"))
        if self._raise_generic_error:
            self._raise_generic_error = False
            raise RuntimeError("boom — unexpected failure at commit time")
        self.committed = True

    async def rollback(self):
        self.rolled_back = True
