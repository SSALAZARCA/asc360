"""
tests/parts_manual/test_item_by_number_price.py -- `GET /parts/section/{section_id}/item/{order_num}`
(`get_part_by_number`), the SINGLE-item endpoint `/tg/parts` and the Sonia
bot actually call.

Distributor Parts Search PR2 (design ADR 1): PR1 gave `_resolve_public_price`
+ the batched `PartCatalog` lookup + `description_es` to the PLURAL list
endpoint (`get_all_items_for_section`) only. `/tg/parts` never calls that
endpoint -- its only parts request is this singular one. This file pins two
things:

1. **Anti-drift** (task 2.1): `get_part_by_number` and
   `get_all_items_for_section` must return the IDENTICAL `precio_publico`
   for the SAME part, because both now go through the same shared
   `_resolve_public_price` path. Asserted by comparing the two endpoints'
   responses field-by-field for one part -- not just "both non-null".
2. **Role parity** (task 2.2): `technician`, `jefe_taller`, `parts_dealer`,
   `superadmin`, and a Sonia-secret call (no JWT) all get `200` with
   `precio_publico` present. This pins the REVERSED decision (obs 186 rev.
   2) -- price is never gated by role -- so a future "hide price from
   Técnicos" change fails this test loudly instead of silently re-forking
   the endpoint.

`get_part_by_number` keeps its INNER JOIN + 404 on an unknown `order_num`
(design ADR 6) -- this file also regression-pins both of those, unchanged.
"""
import uuid
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db
from app.api.deps import get_optional_user
from app.config import settings
from app.services.pricing_service import compute_prices

from tests.parts_manual.conftest import (
    FAKE_FACTORS,
    FakeItemByNumberSession,
    FakeSectionItemsSession,
    NoTouchSession,
    make_current_user,
    make_item,
    make_jefe_taller,
    make_parts_dealer,
    make_reference,
    make_section,
    make_superadmin,
    make_technician,
)

SONIA_SECRET = settings.SONIA_BOT_SECRET  # matches backend/conftest.py's env default


def _patch_pricing_factors():
    """Patches `get_pricing_factors` at its point of use -- matching
    `tests/test_parts_manual_section_items.py`'s `_patch_pricing_factors` --
    so every price-resolving test controls factors deterministically."""
    return patch(
        "app.api.v1.parts_manual.get_pricing_factors",
        new=AsyncMock(return_value=FAKE_FACTORS),
    )


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


def _get_item_by_number(section_id, order_num, headers=None):
    with TestClient(app) as client:
        return client.get(
            f"/api/v1/parts/section/{section_id}/item/{order_num}",
            headers=headers or {},
        )


def _get_all_items(section_id, headers=None):
    with TestClient(app) as client:
        return client.get(
            f"/api/v1/parts/section/{section_id}/items",
            headers=headers or {},
        )


# ── Auth / regression: unchanged 403 and 404 behavior ──────────────────────

def test_missing_authorization_and_missing_sonia_secret_returns_403():
    section_id = uuid.uuid4()
    _override_db(NoTouchSession())
    _override_user(None)

    try:
        resp = _get_item_by_number(section_id, "1")
        assert resp.status_code == 403
    finally:
        _teardown()


def test_unknown_order_num_still_returns_404():
    """Design ADR 6: `get_part_by_number` keeps its INNER JOIN + 404 --
    unlike the plural list endpoint, this is a single-resource lookup, so
    "no matching row" is genuinely a not-found, not an empty list."""
    section_id = uuid.uuid4()
    fake_db = FakeItemByNumberSession(row=None)
    _override_db(fake_db)
    _override_user(make_current_user())

    try:
        resp = _get_item_by_number(section_id, "999")
        assert resp.status_code == 404
        # No pricing/catalog lookup ever happens for a 404 -- the handler
        # returns before reaching the price-resolution path.
        assert len(fake_db.executed_statements) == 1
    finally:
        _teardown()


def test_still_inner_joins_parts_reference_not_left_join():
    """Design ADR 6: `get_all_items_for_section` moved to LEFT JOIN (PR1),
    but `get_part_by_number` must NOT -- it stays an INNER JOIN, so a
    numbered position with no catalog reference genuinely 404s here rather
    than returning a row full of nulls."""
    section_id = uuid.uuid4()
    fake_db = FakeItemByNumberSession(row=None)
    _override_db(fake_db)
    _override_user(make_current_user())

    try:
        _get_item_by_number(section_id, "1")
        stmt = fake_db.executed_statements[0]
        # `stmt.compile(literal_binds=True)` can't render a raw postgres
        # `UUID` type without the postgres dialect (matching
        # `tests/test_parts_manual_section_items.py`'s convention) -- plain
        # `str(stmt)` is enough to inspect the JOIN clause.
        sql = str(stmt)
        assert "parts_references" in sql
        assert "LEFT OUTER JOIN parts_references" not in sql
        assert "JOIN parts_references" in sql
    finally:
        _teardown()


# ── New fields: price + description_es ─────────────────────────────────────

def test_returns_price_and_description_es_when_data_present():
    section = make_section(section_code="B5", section_name="MOTOR")
    ref = make_reference(
        factory_part_number="UM-500",
        um_part_number="UM-500-CO",
        description="Piston",
        unit="PZA",
        avg_fob_cost=12.0,
        description_es_manual="Pistón",
    )
    item = make_item(section, ref, order_num="3")
    fake_db = FakeItemByNumberSession(row=(item, section, ref))
    _override_db(fake_db)
    _override_user(make_current_user(role="parts_dealer"))

    expected_price = compute_prices(12.0, FAKE_FACTORS)["precio_publico"]

    try:
        with _patch_pricing_factors():
            resp = _get_item_by_number(section.id, "3")
        assert resp.status_code == 200
        body = resp.json()
        assert body["factory_part_number"] == "UM-500"
        assert body["description"] == "Piston"
        assert body["description_es"] == "Pistón"
        assert body["precio_publico"] == expected_price
        assert body["precio_es_preliminar"] is False

        # Exactly 2 db.execute() calls: the item join (#1) and the ONE
        # batched PartCatalog lookup (#2, ADR 5) -- collapsed to a single
        # code here, never a per-row loop.
        assert len(fake_db.executed_statements) == 2
    finally:
        _teardown()


def test_returns_null_price_and_description_es_when_data_absent():
    section = make_section(section_code="B6", section_name="CHASIS")
    ref = make_reference(
        factory_part_number="UM-600",
        avg_fob_cost=None,
        preliminary_fob=None,
        description_es_manual=None,
    )
    item = make_item(section, ref, order_num="4")
    fake_db = FakeItemByNumberSession(row=(item, section, ref))
    _override_db(fake_db)
    _override_user(make_current_user())

    try:
        with _patch_pricing_factors():
            resp = _get_item_by_number(section.id, "4")
        assert resp.status_code == 200
        body = resp.json()
        assert body["description_es"] is None
        assert body["precio_publico"] is None
        assert body["precio_es_preliminar"] is False
    finally:
        _teardown()


def test_precio_es_preliminar_true_when_price_derived_from_preliminary_fob():
    section = make_section()
    ref = make_reference(factory_part_number="UM-700", avg_fob_cost=None, preliminary_fob=6.0)
    item = make_item(section, ref, order_num="5")
    fake_db = FakeItemByNumberSession(row=(item, section, ref))
    _override_db(fake_db)
    _override_user(make_current_user())

    try:
        with _patch_pricing_factors():
            resp = _get_item_by_number(section.id, "5")
        assert resp.status_code == 200
        body = resp.json()
        assert body["precio_publico"] == compute_prices(6.0, FAKE_FACTORS)["precio_publico"]
        assert body["precio_es_preliminar"] is True
    finally:
        _teardown()


# ── Anti-drift: the two endpoints must never disagree (task 2.1) ──────────

def test_price_matches_the_list_endpoint_for_the_identical_part():
    """The core anti-drift guarantee (design ADR 2, obs 186's verbatim
    "los precios cambian continuamente y deben cambiar en todos lados"):
    the SAME `factory_part_number`, looked up via the singular endpoint
    (what `/tg/parts` calls) and separately via the plural list endpoint
    (what the Distribuidor screen calls), must return the IDENTICAL
    `precio_publico` -- because both go through the one shared
    `_resolve_public_price` function, not two independently-written
    formulas that happen to agree today."""
    section = make_section(section_code="B7", section_name="SUSPENSION")
    ref = make_reference(
        factory_part_number="UM-800",
        um_part_number="UM-800-CO",
        description="Amortiguador",
        unit="PZA",
        avg_fob_cost=25.5,
        description_es_manual="Amortiguador trasero",
    )
    item = make_item(section, ref, order_num="6")

    # Singular endpoint (get_part_by_number).
    singular_db = FakeItemByNumberSession(row=(item, section, ref))
    _override_db(singular_db)
    _override_user(make_current_user())
    try:
        with _patch_pricing_factors():
            singular_resp = _get_item_by_number(section.id, "6")
    finally:
        _teardown()
    assert singular_resp.status_code == 200
    singular_body = singular_resp.json()

    # Plural endpoint (get_all_items_for_section) -- same part, own request.
    plural_db = FakeSectionItemsSession(rows=[(item, section, ref)])
    _override_db(plural_db)
    _override_user(make_current_user())
    try:
        with _patch_pricing_factors():
            plural_resp = _get_all_items(section.id)
    finally:
        _teardown()
    assert plural_resp.status_code == 200
    plural_body = plural_resp.json()[0]

    # Both must be a real, non-null, non-zero computed value -- proves this
    # isn't two nulls trivially "agreeing".
    assert singular_body["precio_publico"] is not None
    assert singular_body["precio_publico"] != 0

    # Field-by-field comparison of every shared field, pinning that both
    # handlers produced the same PartItemResult shape for the same part.
    assert singular_body["factory_part_number"] == plural_body["factory_part_number"]
    assert singular_body["precio_publico"] == plural_body["precio_publico"]
    assert singular_body["precio_es_preliminar"] == plural_body["precio_es_preliminar"]
    assert singular_body["description_es"] == plural_body["description_es"]

    # And both equal the value the shared price path itself produces --
    # proves neither handler quietly reimplemented the formula.
    expected_price = compute_prices(25.5, FAKE_FACTORS)["precio_publico"]
    assert singular_body["precio_publico"] == expected_price


# ── Role parity: no role gates the price field (task 2.2) ─────────────────

def test_price_visible_to_every_role_and_to_sonia_secret():
    """Pins the reversed decision (obs 186 rev. 2): `technician`,
    `jefe_taller`, `parts_dealer`, `superadmin`, and an `x-sonia-secret` call
    (no JWT at all) must ALL get `200` with `precio_publico` present. No
    role -- and no auth mechanism -- gates this field. A future accidental
    reintroduction of role-based price gating must fail this test loudly."""
    section = make_section(section_code="B8", section_name="FRENOS")
    ref = make_reference(factory_part_number="UM-900", avg_fob_cost=9.0)
    item = make_item(section, ref, order_num="7")
    expected_price = compute_prices(9.0, FAKE_FACTORS)["precio_publico"]

    callers = [
        ("technician", make_technician(), None),
        ("jefe_taller", make_jefe_taller(), None),
        ("parts_dealer", make_parts_dealer(), None),
        ("superadmin", make_superadmin(), None),
        ("sonia_bot", None, {"x-sonia-secret": SONIA_SECRET}),
    ]

    for label, current_user, headers in callers:
        fake_db = FakeItemByNumberSession(row=(item, section, ref))
        _override_db(fake_db)
        _override_user(current_user)
        try:
            with _patch_pricing_factors():
                resp = _get_item_by_number(section.id, "7", headers=headers)
            assert resp.status_code == 200, f"{label} did not get 200"
            body = resp.json()
            assert body["precio_publico"] is not None, f"{label} got no price"
            assert body["precio_publico"] == expected_price, f"{label} price mismatch"
        finally:
            _teardown()
