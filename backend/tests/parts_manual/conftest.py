"""
Shared fixtures for `tests/parts_manual/` -- follows the project's
established fake-`CurrentUser`/fake-session convention (see
`tests/distributor_deliveries/conftest.py`).

Distributor Parts Search PR2 (design ADR 1/2): `get_part_by_number` (the
SINGLE-item endpoint `/tg/parts` actually calls) gains the same
`_resolve_public_price` path PR1 already gave `get_all_items_for_section`
(the plural list endpoint). This package's tests exist to pin two things at
once: (1) the two handlers can never drift apart on price for the same part,
and (2) no role gates the price field -- the reversed decision from
`sdd/distributor-parts-search/proposal-decisions` (obs 186 rev. 2).
"""
import uuid
from typing import Optional

from app.api.deps import CurrentUser
from app.models.parts_manual import PartsManualItem, PartsManualSection, PartsReference

# Fixed, arbitrary pricing factors -- matches
# `tests/test_parts_manual_section_items.py`'s `FAKE_FACTORS` so both
# endpoints are exercised against the identical inputs when tests compare
# them directly.
FAKE_FACTORS = {
    "import_factor": 1.42,
    "provider_margin": 0.35,
    "distributor_margin": 0.35,
    "iva_rate": 0.19,
    "trm": 3800.0,
}


def make_current_user(role: str = "parts_dealer") -> CurrentUser:
    return CurrentUser(user_id=str(uuid.uuid4()), role=role, tenant_id=None, name="T")


def make_technician() -> CurrentUser:
    return make_current_user(role="technician")


def make_jefe_taller() -> CurrentUser:
    return make_current_user(role="jefe_taller")


def make_parts_dealer() -> CurrentUser:
    return make_current_user(role="parts_dealer")


def make_superadmin() -> CurrentUser:
    return make_current_user(role="superadmin")


def make_section(
    section_id: Optional[uuid.UUID] = None,
    section_code: str = "B1",
    section_name: str = "FRAME",
    model_code: str = "RENEGADE200",
) -> PartsManualSection:
    return PartsManualSection(
        id=section_id or uuid.uuid4(),
        model_code=model_code,
        section_code=section_code,
        section_name=section_name,
        diagram_url=None,
    )


def make_reference(
    factory_part_number: str = "UM-001",
    um_part_number: str = "UM-001-CO",
    description: str = "Tornillo",
    unit: str = "PZA",
    avg_fob_cost: Optional[float] = None,
    preliminary_fob: Optional[float] = None,
    description_es_manual: Optional[str] = None,
) -> PartsReference:
    return PartsReference(
        factory_part_number=factory_part_number,
        um_part_number=um_part_number,
        description=description,
        unit=unit,
        avg_fob_cost=avg_fob_cost,
        preliminary_fob=preliminary_fob,
        description_es_manual=description_es_manual,
    )


def make_item(
    section: PartsManualSection,
    ref: PartsReference,
    order_num: str = "1",
    item_id: Optional[uuid.UUID] = None,
) -> PartsManualItem:
    item = PartsManualItem(
        id=item_id or uuid.uuid4(),
        section_id=section.id,
        order_num=order_num,
        factory_part_number=ref.factory_part_number,
    )
    item.section = section
    item.reference = ref
    return item


class NoTouchSession:
    """Fake DB session that fails the test if the route touches it at all --
    mirrors `tests/distributor_deliveries/conftest.py`'s `NoTouchSession`."""

    async def execute(self, *args, **kwargs):
        raise AssertionError("route touched db.execute() before auth short-circuited")


class _FirstResult:
    """Fake result for a `.first()` call -- `get_part_by_number`'s single-row
    INNER JOIN query."""

    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _ScalarsResult:
    """Fake result for `select(PartCatalog).where(part_code.in_(...))`
    (design ADR 5's batched manual-price lookup) -- `.scalars()` returns an
    iterable of canned catalog rows."""

    def __init__(self, items):
        self._items = items

    def scalars(self):
        return list(self._items)


class _AllResult:
    """Fake result for a `.all()` call -- `get_all_items_for_section`'s
    multi-row LEFT JOIN query."""

    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class FakeItemByNumberSession:
    """Fake session for `get_part_by_number` (singular, INNER JOIN, single
    row via `.first()`). Mirrors `FakeSectionItemsSession` in
    `tests/test_parts_manual_section_items.py`: call #1 is always the
    item/section/reference join, call #2 (only reached when a row was
    found -- a 404 short-circuits before it) is the batched `PartCatalog`
    manual-price lookup PR2 adds to this handler too."""

    def __init__(self, row=None, catalog_rows=None):
        self._row = row
        self._catalog_rows = catalog_rows or []
        self.executed_statements: list = []

    async def execute(self, stmt):
        self.executed_statements.append(stmt)
        if len(self.executed_statements) == 1:
            return _FirstResult(self._row)
        return _ScalarsResult(self._catalog_rows)


class FakeSectionItemsSession:
    """Fake session for `get_all_items_for_section` (plural, LEFT JOIN, all
    rows via `.all()`). Identical shape to
    `tests/test_parts_manual_section_items.py`'s session of the same name --
    duplicated locally (not imported) so this package stays self-contained,
    matching the project's established per-module fixture convention.

    Call #3 is the batched `_resolve_inventory_status` coverage lookup
    (also via `.all()`) -- defaults to no rows, so every part resolves to
    'sin_stock' unless a test passes `coverage_rows` explicitly."""

    def __init__(self, rows=None, catalog_rows=None, coverage_rows=None):
        self._rows = rows or []
        self._catalog_rows = catalog_rows or []
        self._coverage_rows = coverage_rows or []
        self.executed_statements: list = []

    async def execute(self, stmt):
        self.executed_statements.append(stmt)
        idx = len(self.executed_statements)
        if idx == 1:
            return _AllResult(self._rows)
        if idx == 2:
            return _ScalarsResult(self._catalog_rows)
        return _AllResult(self._coverage_rows)
