"""
tests/test_parts_manual_section_items.py -- `GET /parts/section/{section_id}/items`
(new endpoint for the Distribuidor parts-search screen).

Reuses the exact auth pattern of the sibling single-item endpoint,
`GET /parts/section/{section_id}/item/{order_num}` (`get_part_by_number`):
`X-Sonia-Secret` OR a JWT (`get_optional_user`) is required, 403 otherwise --
no role restriction beyond "authenticated or bot". Same 3-way join
(`PartsManualItem` + `PartsManualSection` + `PartsReference`), same
`PartItemResult` response shape, but lists ALL items in a section instead of
looking up exactly one by `order_num`.

Router-level HTTP tests via `TestClient` + `app.dependency_overrides`,
matching `tests/orders/test_active_orders_for_tenant_auth.py`'s convention
for a dual-auth (`get_optional_user` + `X-Sonia-Secret`) endpoint. The fake
session returns a canned row list regardless of the compiled `WHERE`
clause -- to prove the `section_id` filter is genuinely applied (not just
trusted from a canned fixture), the "different section excluded" test
compiles the emitted SQL with `literal_binds` and asserts the exact
`section_id` predicate is present, matching
`tests/distributor_deliveries/test_list_deliveries.py`'s convention.

Distributor Parts Search (PR1, design ADR 2/5/6/7): the endpoint now also
resolves a live-computed `precio_publico` (never persisted, never `$0`),
LEFT-JOINs `PartsReference` so a numbered item with no catalog reference
still occupies its slot, and natural-sorts `order_num` in Python (A1, A2,
A10 -- not the lexicographic A1, A10, A2 a SQL `ORDER BY` would produce).
`get_pricing_factors` is patched directly (`app.api.v1.parts_manual.
get_pricing_factors`) in every test that exercises the full endpoint, so
`FakeSectionItemsSession.execute()` calls stay strictly ordered: call #1 is
always the item join, call #2 (when items exist) is always the batched
`PartCatalog` lookup (ADR 5) -- this is what makes the "queried exactly
once" assertions meaningful rather than accidental.
"""
import uuid
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db
from app.api.deps import get_optional_user, CurrentUser
from app.config import settings
from app.models.parts_manual import PartsManualItem, PartsManualSection, PartsReference
from app.services.pricing_service import compute_prices

SONIA_SECRET = settings.SONIA_BOT_SECRET  # matches backend/conftest.py's env default

# Fixed, arbitrary pricing factors used across every price-resolving test --
# tests compute their expected value by calling the REAL `compute_prices`
# with these same factors, so the assertion proves "the endpoint correctly
# assembles and calls the shared price path" rather than duplicating its math.
FAKE_FACTORS = {
    "import_factor": 1.42,
    "provider_margin": 0.35,
    "distributor_margin": 0.35,
    "iva_rate": 0.19,
    "trm": 3800.0,
}


def _patch_pricing_factors():
    """Patches `get_pricing_factors` at its point of use so every
    price-resolving test controls factors deterministically and can assert
    the "exactly once per request" call count (design ADR 2/5) without
    depending on a real `SystemConfig` row via the fake DB session."""
    return patch(
        "app.api.v1.parts_manual.get_pricing_factors",
        new=AsyncMock(return_value=FAKE_FACTORS),
    )


def make_current_user(role: str = "parts_dealer") -> CurrentUser:
    return CurrentUser(user_id=str(uuid.uuid4()), role=role, tenant_id=None, name="T")


class NoTouchSession:
    """Fake DB session that fails the test if the route touches it at all --
    mirrors `tests/distributor_deliveries/conftest.py`'s `NoTouchSession`."""

    async def execute(self, *args, **kwargs):
        raise AssertionError("route touched db.execute() before auth short-circuited")


class _AllResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _ScalarsResult:
    """Fake result for `select(PartCatalog).where(part_code.in_(...))`
    (design ADR 5's batched manual-price lookup) -- `.scalars()` returns an
    iterable of canned catalog rows, matching how the real endpoint consumes
    a SQLAlchemy `Result`."""

    def __init__(self, items):
        self._items = items

    def scalars(self):
        return list(self._items)


class FakeSectionItemsSession:
    """Returns a canned row list for whatever `SELECT` comes in, regardless
    of its `WHERE`/`ORDER BY` clauses -- exactly like `FakeDeliverySession`
    and `FakeActiveTenantSession`. Records every executed statement so tests
    can separately compile the SQL to prove the real filter/order clauses
    are present.

    Distributor Parts Search (PR1): the endpoint now issues a SECOND
    `db.execute()` for the batched `PartCatalog` manual-price lookup (ADR 5)
    whenever the item query returns at least one row. `get_pricing_factors`
    is patched directly in every test (see `_patch_pricing_factors`), so it
    never touches this fake session -- call #1 is always the item join,
    call #2 (if any) is always the `PartCatalog` lookup. `catalog_rows`
    defaults to empty (no manual price override for any part)."""

    def __init__(self, rows=None, catalog_rows=None):
        self._rows = rows or []
        self._catalog_rows = catalog_rows or []
        self.executed_statements: list = []

    async def execute(self, stmt):
        self.executed_statements.append(stmt)
        if len(self.executed_statements) == 1:
            return _AllResult(self._rows)
        return _ScalarsResult(self._catalog_rows)


def _make_section(section_id=None, section_code="B1", section_name="FRAME", model_code="RENEGADE200") -> PartsManualSection:
    return PartsManualSection(
        id=section_id or uuid.uuid4(),
        model_code=model_code,
        section_code=section_code,
        section_name=section_name,
        diagram_url=None,
    )


def _make_reference(
    factory_part_number="UM-001",
    um_part_number="UM-001-CO",
    description="Tornillo",
    unit="PZA",
    avg_fob_cost=None,
    preliminary_fob=None,
    description_es_manual=None,
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


def _make_item(section, ref, order_num="1", item_id=None) -> PartsManualItem:
    item = PartsManualItem(
        id=item_id or uuid.uuid4(),
        section_id=section.id,
        order_num=order_num,
        factory_part_number=ref.factory_part_number,
    )
    item.section = section
    item.reference = ref
    return item


def _override_db(fake_db):
    async def _get_db():
        yield fake_db
    app.dependency_overrides[get_db] = _get_db


def _override_user(current_user):
    async def _get_optional_user():
        return current_user
    app.dependency_overrides[get_optional_user] = _get_optional_user


def _teardown():
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_optional_user, None)


def _get(section_id, headers=None):
    with TestClient(app) as client:
        return client.get(f"/api/v1/parts/section/{section_id}/items", headers=headers or {})


def _compiled_sql(stmt) -> str:
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


def test_missing_authorization_and_missing_sonia_secret_returns_403():
    section_id = uuid.uuid4()
    _override_db(NoTouchSession())
    _override_user(None)

    try:
        resp = _get(section_id)
        assert resp.status_code == 403
    finally:
        _teardown()


def test_sonia_bot_secret_with_no_jwt_returns_data_not_403():
    section = _make_section()
    ref = _make_reference()
    item = _make_item(section, ref, order_num="1")
    _override_db(FakeSectionItemsSession(rows=[(item, section, ref)]))
    _override_user(None)  # no JWT, exactly like Sonia's real call

    try:
        with _patch_pricing_factors():
            resp = _get(section.id, headers={"x-sonia-secret": SONIA_SECRET})
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["factory_part_number"] == "UM-001"
    finally:
        _teardown()


def test_authenticated_jwt_returns_all_items_in_order_num_order_with_correct_fields():
    section = _make_section(section_code="B3", section_name="ENGINE")
    ref1 = _make_reference(
        factory_part_number="UM-100", um_part_number="UM-100-CO", description="Piston", unit="PZA",
        avg_fob_cost=10.0, description_es_manual="Pistón",
    )
    ref2 = _make_reference(
        factory_part_number="UM-200", um_part_number="UM-200-CO", description="Anillo", unit="KIT",
        preliminary_fob=5.0,  # no avg_fob_cost -- price derived from the PI, so preliminar=True
    )
    item1 = _make_item(section, ref1, order_num="1")
    item2 = _make_item(section, ref2, order_num="2")
    fake_db = FakeSectionItemsSession(rows=[(item1, section, ref1), (item2, section, ref2)])
    _override_db(fake_db)
    _override_user(make_current_user(role="parts_dealer"))

    expected_price_1 = compute_prices(10.0, FAKE_FACTORS)["precio_publico"]
    expected_price_2 = compute_prices(5.0, FAKE_FACTORS)["precio_publico"]

    try:
        with _patch_pricing_factors():
            resp = _get(section.id)
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2
        assert [b["order_num"] for b in body] == ["1", "2"]

        first = body[0]
        assert first["id"] == str(item1.id)
        assert first["section_id"] == str(section.id)
        assert first["section_code"] == "B3"
        assert first["section_name"] == "ENGINE"
        assert first["factory_part_number"] == "UM-100"
        assert first["um_part_number"] == "UM-100-CO"
        assert first["description"] == "Piston"
        assert first["description_es"] == "Pistón"
        assert first["unit"] == "PZA"
        assert first["precio_publico"] == expected_price_1
        assert first["precio_es_preliminar"] is False

        second = body[1]
        assert second["factory_part_number"] == "UM-200"
        assert second["um_part_number"] == "UM-200-CO"
        assert second["description"] == "Anillo"
        assert second["unit"] == "KIT"
        assert second["precio_publico"] == expected_price_2
        assert second["precio_es_preliminar"] is True
    finally:
        _teardown()


def test_item_without_parts_reference_row_still_appears_with_null_fields():
    """LEFT JOIN (design ADR 6): a numbered position whose `factory_part_number`
    has no matching `PartsReference` row must still occupy its slot in the
    list, with description/codes/price rendered as `null` -- never omitted,
    never a placeholder string, never `$0` (ADR 3/6/8). Constructed directly
    via the fake session because the real FK (`fk_parts_items_reference`,
    `ondelete='RESTRICT'`) makes this state unreachable through the real API
    today -- the LEFT JOIN is a defended invariant, not a live bug fix."""
    section = _make_section(section_code="B4", section_name="WHEELS")
    orphan_item = PartsManualItem(
        id=uuid.uuid4(),
        section_id=section.id,
        order_num="1",
        factory_part_number="UM-ORPHAN",
    )
    ref = _make_reference(factory_part_number="UM-002", avg_fob_cost=8.0)
    normal_item = _make_item(section, ref, order_num="2")

    # Row tuple shape matches `select(PartsManualItem, PartsManualSection,
    # PartsReference)` with an outer join -- `ref` is None for the orphan.
    fake_db = FakeSectionItemsSession(rows=[
        (orphan_item, section, None),
        (normal_item, section, ref),
    ])
    _override_db(fake_db)
    _override_user(make_current_user())

    try:
        with _patch_pricing_factors():
            resp = _get(section.id)
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2

        orphan = body[0]
        assert orphan["order_num"] == "1"
        assert orphan["factory_part_number"] == "UM-ORPHAN"
        assert orphan["description"] is None
        assert orphan["um_part_number"] is None
        assert orphan["description_es"] is None
        assert orphan["unit"] is None
        assert orphan["precio_publico"] is None
        assert orphan["precio_es_preliminar"] is False

        populated = body[1]
        assert populated["order_num"] == "2"
        assert populated["factory_part_number"] == "UM-002"
        assert populated["precio_publico"] == compute_prices(8.0, FAKE_FACTORS)["precio_publico"]
    finally:
        _teardown()


def test_order_num_is_natural_sorted_not_lexicographic():
    """Design ADR 7: `order_num` is `String(20)` holding values like A1/A10/B2,
    so a plain lexicographic sort (what SQL `ORDER BY` would give) yields
    A1, A10, A2 -- wrong for a legend read in diagram order. Rows are
    inserted in SCRAMBLED order to prove the production code, not the fixture,
    performs the sort."""
    section = _make_section()
    scrambled_order_nums = ["A10", "B2", "A1", "B10", "A2", "B1"]
    rows = []
    for n in scrambled_order_nums:
        ref = _make_reference(factory_part_number=f"UM-{n}")
        item = _make_item(section, ref, order_num=n)
        rows.append((item, section, ref))

    fake_db = FakeSectionItemsSession(rows=rows)
    _override_db(fake_db)
    _override_user(make_current_user())

    try:
        with _patch_pricing_factors():
            resp = _get(section.id)
        assert resp.status_code == 200
        body = resp.json()
        assert [b["order_num"] for b in body] == ["A1", "A2", "A10", "B1", "B2", "B10"]
    finally:
        _teardown()


def test_pricing_factors_and_part_catalog_fetched_exactly_once_per_request():
    """Hard constraint carried over from obs 184 (design ADR 2/5): computing
    price for a whole section must fetch pricing factors, and query the
    manual-price `PartCatalog` table, EXACTLY ONCE regardless of row count --
    never once per row. Asserted by call count, not by inspection."""
    section = _make_section()
    rows = []
    for i in range(1, 6):  # 5 rows -- if pricing were per-row this would be 5x
        ref = _make_reference(factory_part_number=f"UM-{i:03d}", avg_fob_cost=float(i))
        item = _make_item(section, ref, order_num=str(i))
        rows.append((item, section, ref))

    fake_db = FakeSectionItemsSession(rows=rows)
    _override_db(fake_db)
    _override_user(make_current_user())

    try:
        with patch(
            "app.api.v1.parts_manual.get_pricing_factors",
            new=AsyncMock(return_value=FAKE_FACTORS),
        ) as mock_factors:
            resp = _get(section.id)
        assert resp.status_code == 200
        assert len(resp.json()) == 5
        mock_factors.assert_awaited_once()

        # Exactly 2 `db.execute()` calls total: the item join (#1) and the
        # ONE batched `PartCatalog` manual-price lookup (#2, ADR 5) -- never
        # a third call, never one per row.
        assert len(fake_db.executed_statements) == 2
        catalog_sql = str(fake_db.executed_statements[1])
        assert "part_catalog" in catalog_sql.lower()
    finally:
        _teardown()


def test_section_with_zero_items_returns_empty_list_not_404():
    section_id = uuid.uuid4()
    _override_db(FakeSectionItemsSession(rows=[]))
    _override_user(make_current_user())

    try:
        with _patch_pricing_factors():
            resp = _get(section_id)
        assert resp.status_code == 200
        assert resp.json() == []
    finally:
        _teardown()


def test_nonexistent_section_id_returns_empty_list_not_404():
    """A `section_id` that doesn't exist in the DB produces zero matching
    rows from the join -- same code path, same empty-list response, as a
    real-but-empty section. This is a listing endpoint, not a
    single-resource lookup, so it never 404s."""
    nonexistent_section_id = uuid.uuid4()
    _override_db(FakeSectionItemsSession(rows=[]))
    _override_user(make_current_user())

    try:
        with _patch_pricing_factors():
            resp = _get(nonexistent_section_id)
        assert resp.status_code == 200
        assert resp.json() == []
    finally:
        _teardown()


def test_where_clause_filters_by_section_id_and_excludes_other_sections():
    """Proves the filter is real at the SQL level -- a canned-row fixture
    alone can't distinguish "correctly filtered by section_id" from "returns
    everything regardless of section_id", since `FakeSectionItemsSession`
    ignores its own `WHERE` clause when handing back rows. Compiling the
    emitted statement (matching `tests/distributor_deliveries/
    test_list_deliveries.py`'s convention) proves the real query would
    exclude a different section's items."""
    target_section_id = uuid.uuid4()
    fake_db = FakeSectionItemsSession(rows=[])
    _override_db(fake_db)
    _override_user(make_current_user())

    try:
        with _patch_pricing_factors():
            resp = _get(target_section_id)
        assert resp.status_code == 200

        stmt = fake_db.executed_statements[0]
        # `stmt.compile(literal_binds=True)` can't render a raw postgres
        # `UUID` type without the postgres dialect, so instead assert the
        # (unbound) WHERE-clause column reference and, separately, the
        # actual bound parameter value -- same effect as literal binds,
        # matching `tests/vehicles/test_get_by_plate_visibility.py`'s
        # `TestGetByPlateCoercesStringTenantIdToUuid` convention.
        sql = str(stmt)
        assert "parts_manual_items.section_id =" in sql
        # No `order_num` equality filter -- this is the plural list
        # endpoint, not the singular by-exact-code lookup.
        assert "parts_manual_items.order_num =" not in sql
        # Design ADR 7: sorting moved to Python (`_natural_order_key`) so a
        # numbered legend like A1/A2/A10 doesn't come back lexicographic.
        # The SQL `ORDER BY` clause on `order_num` is gone by design --
        # asserting its ABSENCE here is the regression that would catch a
        # future revert of ADR 7.
        assert "ORDER BY parts_manual_items.order_num" not in sql

        bound_values = list(stmt.compile().params.values())
        assert str(target_section_id) in bound_values
    finally:
        _teardown()


def test_singular_and_plural_section_routes_coexist_without_shadowing():
    """`/section/{section_id}/item/{order_num}` (singular, by exact code)
    and `/section/{section_id}/items` (plural, full listing) must both
    resolve to their own distinct route -- proven here by hitting the
    plural route and confirming it is NOT swallowed by the singular route's
    `{order_num}` path param (which would 404 on a body-shape mismatch or
    422 on a missing param, never a clean 200 with a list)."""
    section = _make_section()
    ref = _make_reference()
    item = _make_item(section, ref, order_num="7")
    _override_db(FakeSectionItemsSession(rows=[(item, section, ref)]))
    _override_user(make_current_user())

    try:
        with _patch_pricing_factors():
            plural_resp = _get(section.id)
        assert plural_resp.status_code == 200
        assert isinstance(plural_resp.json(), list)

        # Drop the `get_optional_user` override so the singular request
        # below hits its OWN 403 auth guard before ever touching
        # `FakeSectionItemsSession` (which only implements `.all()`, not
        # `get_part_by_number`'s `.first()`) -- this call only needs to
        # prove the singular route is matched and independently reachable,
        # not to duplicate the auth-behavior tests above.
        app.dependency_overrides.pop(get_optional_user, None)
        with TestClient(app) as client:
            singular_resp = client.get(f"/api/v1/parts/section/{section.id}/item/7")
        assert singular_resp.status_code == 403
    finally:
        _teardown()
