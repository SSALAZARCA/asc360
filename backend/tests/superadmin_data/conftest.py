"""
Shared fixtures for Phase 2 (Vehicle quick-fix) tests on
`app/api/v1/superadmin_data.py`.

Follows the project's established fake-`AsyncSession` convention (see
`tests/orders/conftest.py`, `tests/imports/conftest.py`): real ORM instances
constructed directly (no live DB), a minimal fake session exposing only the
surface the routes under test actually call.
"""
import uuid
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
    return Vehicle(
        id=vehicle_id or uuid.uuid4(),
        tenant_id=tenant_id or uuid.uuid4(),
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
