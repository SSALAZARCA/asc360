"""
Shared fixtures for Phase 2 (Vehicle quick-fix), Phase 3 (Order quick-fix —
dates), and Phase 4 (Order quick-fix — mileage_km/service_type + lifecycle
sync) tests on `app/api/v1/superadmin_data.py`.

Follows the project's established fake-`AsyncSession` convention (see
`tests/orders/conftest.py`, `tests/imports/conftest.py`): real ORM instances
constructed directly (no live DB), a minimal fake session exposing only the
surface the routes under test actually call.
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.exc import IntegrityError


def make_vehicle(
    vehicle_id: Optional[uuid.UUID] = None,
    plate: str = "ABC123",
    vin: Optional[str] = "VIN0001",
    brand: str = "UM",
    model: str = "DSR",
    color: Optional[str] = "Rojo",
    year: Optional[int] = 2024,
    mileage: Optional[int] = 1000,
    tenant_id: Optional[uuid.UUID] = None,
) -> "Vehicle":
    from app.models.vehicle import Vehicle
    # `tenant_id` is accepted but NOT forwarded to `Vehicle(...)` --
    # sdd/vehicle-tenant-checkin-release PR2 unmapped that column from the
    # ORM (a vehicle's tenant is now a derived claim).
    return Vehicle(
        id=vehicle_id or uuid.uuid4(),
        plate=plate,
        vin=vin,
        brand=brand,
        model=model,
        color=color,
        year=year,
        mileage=mileage,
    )


class _ScalarsResult:
    def __init__(self, items: list):
        self._items = items

    def first(self):
        return self._items[0] if self._items else None

    def all(self):
        return list(self._items)


class _ExecuteResult:
    def __init__(self, items: list):
        self._items = items

    def scalars(self):
        return _ScalarsResult(self._items)


class FakeVehicleSession:
    """
    Minimal fake `AsyncSession` for the Vehicle quick-fix routes.

    - `search_result`: rows returned by the single `db.execute(select(Vehicle)
      ...)` call the GET route issues (empty list = miss -> 404).
    - `get_object`: the `Vehicle` returned by `db.get(Vehicle, vehicle_id)` in
      the PUT route (`None` = miss -> 404).
    - `raise_integrity_error`: if `True`, the FIRST `commit()` raises
      `IntegrityError` (simulates the `vehicles.plate` unique-constraint
      violation) -- the route must catch it, roll back, and return 409.
      `rollback()` discards any pending `add()`s from that failed attempt,
      mirroring a real `AsyncSession.rollback()` expunging uncommitted new
      objects.
    """

    def __init__(
        self,
        search_result: Optional[list] = None,
        get_object=None,
        raise_integrity_error: bool = False,
    ):
        self._search_result = search_result or []
        self._get_object = get_object
        self._raise_integrity_error = raise_integrity_error
        self.added: list = []
        self.committed = False
        self.rolled_back = False
        self.refreshed: list = []

    async def execute(self, stmt):
        return _ExecuteResult(self._search_result)

    async def get(self, model_cls, obj_id):
        if self._get_object is not None and self._get_object.id == obj_id:
            return self._get_object
        return None

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        if self._raise_integrity_error:
            self._raise_integrity_error = False
            raise IntegrityError(
                "UPDATE vehicles", {}, Exception("duplicate key value violates unique constraint")
            )
        self.committed = True

    async def rollback(self):
        self.rolled_back = True
        self.added = []

    async def refresh(self, obj, attribute_names=None):
        self.refreshed.append(obj)


def make_order(
    order_id: Optional[uuid.UUID] = None,
    tenant_id: Optional[uuid.UUID] = None,
    vehicle: Optional["Vehicle"] = None,
    status=None,
    service_type=None,
    created_at: Optional[datetime] = None,
    delivered_at: Optional[datetime] = None,
) -> "ServiceOrder":
    from app.models.order import ServiceOrder, ServiceStatus, ServiceType
    order = ServiceOrder(
        id=order_id or uuid.uuid4(),
        tenant_id=tenant_id or uuid.uuid4(),
        vehicle_id=(vehicle.id if vehicle is not None else uuid.uuid4()),
        status=status or ServiceStatus.received,
        service_type=service_type or ServiceType.regular,
        created_at=created_at or datetime(2026, 7, 1),
        delivered_at=delivered_at,
    )
    if vehicle is not None:
        order.vehicle = vehicle
    return order


def make_reception(
    order_id: Optional[uuid.UUID] = None,
    reception_id: Optional[uuid.UUID] = None,
    mileage_km=None,
) -> "ServiceOrderReception":
    from decimal import Decimal
    from app.models.order import ServiceOrderReception
    return ServiceOrderReception(
        id=reception_id or uuid.uuid4(),
        order_id=order_id or uuid.uuid4(),
        mileage_km=Decimal(str(mileage_km)) if mileage_km is not None else Decimal("1000"),
        created_at=datetime(2026, 7, 1),
    )


def make_lifecycle_event(
    vehicle_id: Optional[uuid.UUID] = None,
    event_id: Optional[uuid.UUID] = None,
    event_type=None,
    km_at_event=None,
    summary: str = "",
    linked_order_id: Optional[uuid.UUID] = None,
) -> "VehicleLifecycleEvent":
    from app.models.vehicle_lifecycle import VehicleLifecycleEvent, LifecycleEventType
    return VehicleLifecycleEvent(
        id=event_id or uuid.uuid4(),
        vehicle_id=vehicle_id or uuid.uuid4(),
        event_type=event_type or LifecycleEventType.RECEPCION,
        event_date=datetime(2026, 7, 1),
        km_at_event=km_at_event,
        summary=summary,
        linked_order_id=linked_order_id,
        is_automatic="auto",
    )


class FakeOrderSession:
    """
    Minimal fake `AsyncSession` for the Order quick-fix routes (Phase 3
    dates + Phase 4 mileage_km/service_type + lifecycle sync).

    - `search_result`: rows returned by the `db.execute(select(ServiceOrder)
      ...)` call the GET route issues (empty list = miss -> 404).
    - `get_object`: the `ServiceOrder` returned by `db.get(ServiceOrder,
      order_id)` in the PUT route (`None` = miss -> 404).
    - `reception`: the `ServiceOrderReception` returned by the PUT route's
      `select(ServiceOrderReception).where(order_id == ...)` query — only
      issued when `mileage_km`/`service_type` is actually being corrected.
      `None` (default) mirrors an order the PUT route never needed to
      fetch a reception for (pure date edits).
    - `lifecycle_events`: rows returned by the PUT route's
      `select(VehicleLifecycleEvent).where(linked_order_id == ...)` query,
      same gating as `reception`.
    - `raise_integrity_error`: same contract as `FakeVehicleSession` — kept
      for parity even though the Order PUT has no unique-constraint
      conflict path today.
    - `vehicle` (sdd/distributor-vehicle-delivery PR2): the `Vehicle`
      returned by the PUT route's NEW `db.get(Vehicle, order.vehicle_id)`
      read (warranty lower-bound check) when its `id` matches the
      requested `obj_id`. `None` (default) means every existing test that
      doesn't pass it keeps getting `None` back for that call — the
      warranty helper then no-ops, so day-1 behaviour is unaffected.

    Dispatch for `execute()` is by the statement's target entity (mirrors
    `tests.orders.conftest.FakeAsyncSession`), NOT by call order, since the
    production route may issue the reception query, the lifecycle-events
    query, or neither, depending on which fields are being corrected.
    `get()` dispatches by `model_cls` (`ServiceOrder` vs `Vehicle`), not by
    id-matching alone, since an order and its vehicle each carry their own
    unrelated `id`.
    """

    def __init__(
        self,
        search_result: Optional[list] = None,
        get_object=None,
        raise_integrity_error: bool = False,
        reception: Optional["ServiceOrderReception"] = None,
        lifecycle_events: Optional[list] = None,
        vehicle: Optional["Vehicle"] = None,
    ):
        self._search_result = search_result or []
        self._get_object = get_object
        self._raise_integrity_error = raise_integrity_error
        self._reception = reception
        self._lifecycle_events = lifecycle_events or []
        self._vehicle = vehicle
        self.added: list = []
        self.deleted: list = []
        self.committed = False
        self.rolled_back = False
        self.refreshed: list = []

    async def execute(self, stmt):
        from app.models.order import ServiceOrderReception
        from app.models.vehicle_lifecycle import VehicleLifecycleEvent

        entity = stmt.column_descriptions[0]["entity"]
        if entity is ServiceOrderReception:
            return _ExecuteResult([self._reception] if self._reception is not None else [])
        if entity is VehicleLifecycleEvent:
            return _ExecuteResult(list(self._lifecycle_events))
        return _ExecuteResult(self._search_result)

    async def get(self, model_cls, obj_id):
        from app.models.vehicle import Vehicle

        if model_cls is Vehicle:
            if self._vehicle is not None and self._vehicle.id == obj_id:
                return self._vehicle
            return None
        if self._get_object is not None and self._get_object.id == obj_id:
            return self._get_object
        return None

    def add(self, obj):
        self.added.append(obj)

    async def delete(self, obj):
        self.deleted.append(obj)

    async def commit(self):
        if self._raise_integrity_error:
            self._raise_integrity_error = False
            raise IntegrityError(
                "UPDATE service_orders", {}, Exception("integrity error")
            )
        self.committed = True

    async def rollback(self):
        self.rolled_back = True
        self.added = []

    async def refresh(self, obj, attribute_names=None):
        self.refreshed.append(obj)
