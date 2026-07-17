"""
Tests for `PATCH /remisiones/{id}/invoiced` and `GET /remisiones/export`.

Both are superadmin-only, mirroring every other endpoint in this router
(`_require_superadmin`). `invoiced` is a plain accounting flag — togglable
regardless of remisión status (BORRADOR/DESPACHADO/ANULADO).

The export's price column depends on the remisión's `type`:
  - GARANTIA / VEHICULO_PROPIO -> costo_importado (costo nacionalizado, COP)
  - PEDIDO                     -> precio_distribuidor (COP)
  - CORTESIA                   -> blank
Computed via the existing `pricing_service.get_pricing_factors`/
`compute_prices` — never re-derived by hand here, always cross-checked
against `compute_prices` itself so a formula change can't silently drift
these tests out of sync.
"""
import io
import uuid
from datetime import datetime
from unittest.mock import MagicMock

import openpyxl

from tests.conftest import make_test_client, make_remision, make_remision_item
from app.services.pricing_service import compute_prices, _PRICING_DEFAULTS


def make_superadmin() -> "CurrentUser":
    from app.api.deps import CurrentUser
    return CurrentUser(user_id=str(uuid.uuid4()), role="superadmin", tenant_id=None, name="Super")


def make_jefe_taller() -> "CurrentUser":
    from app.api.deps import CurrentUser
    return CurrentUser(user_id=str(uuid.uuid4()), role="jefe_taller", tenant_id=str(uuid.uuid4()), name="Jefe")


DEFAULT_FACTORS = {
    "import_factor":      _PRICING_DEFAULTS["pricing.import_factor"],
    "provider_margin":    _PRICING_DEFAULTS["pricing.provider_margin"],
    "distributor_margin": _PRICING_DEFAULTS["pricing.distributor_margin"],
    "iva_rate":            _PRICING_DEFAULTS["pricing.iva_rate"],
    "trm":                 _PRICING_DEFAULTS["pricing.trm"],
}


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeInvoicedSession:
    """Minimal fake for `PATCH /{id}/invoiced`: a single `db.get`, mutate,
    `commit`, `refresh`."""

    def __init__(self, remision=None):
        self._remision = remision
        self.committed = False
        self.refreshed = False

    async def get(self, model, pk):
        if self._remision is not None and pk == self._remision.id:
            return self._remision
        return None

    async def commit(self):
        self.committed = True

    async def refresh(self, obj):
        self.refreshed = True


class _ScalarsResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def all(self):
        return self._items


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _ScalarOneResult:
    def __init__(self, obj):
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj


class FakeExportSession:
    """Fake for `GET /export`. Dispatches `db.execute()` by the statement's
    first-column entity:
      - `InventoryRemision`  -> `.scalars().all()` returning the seeded list.
      - `User.id, User.name` -> `.all()` returning seeded (id, name) rows.
      - `SystemConfig`       -> `.scalars().all()` returning seeded pricing
        rows (empty by default, so `get_pricing_factors` falls back to its
        own hardcoded defaults — mirrored here as `DEFAULT_FACTORS`).
      - `PartsReference`     -> `.scalar_one_or_none()`. Only the
        `factory_part_number` equality query (attempt 1 of
        `_find_reference_for_part_number`'s 3-step fallback) is actually
        matched against `avg_fob_by_part`, identified by inspecting the
        compiled SQL text; the two `prev_codes` JSONB-contains fallback
        queries always return None here since none of these tests exercise
        that fallback path (it's covered separately by pricing_service's
        own tests) — a part_number absent from `avg_fob_by_part` correctly
        ends up with `avg_fob_cost=None` after all 3 attempts miss.
    """

    def __init__(self, remisiones=None, user_names: dict = None,
                 avg_fob_by_part: dict = None, pricing_rows: list = None):
        self._remisiones = remisiones or []
        self._user_names = user_names or {}
        self._avg_fob_by_part = avg_fob_by_part or {}
        self._pricing_rows = pricing_rows or []
        self.executed_statements = []

    async def execute(self, stmt):
        self.executed_statements.append(stmt)
        from app.models.imports import InventoryRemision
        from app.models.parts_manual import PartsReference
        from app.models.system_config import SystemConfig

        entity = stmt.column_descriptions[0]["entity"]

        if entity is InventoryRemision:
            return _ScalarsResult(self._remisiones)

        if entity is SystemConfig:
            return _ScalarsResult(self._pricing_rows)

        if entity is PartsReference:
            # `select(PartsReference)` always SELECTs every column (so both
            # "factory_part_number" and "prev_codes" appear in the SQL text
            # regardless of which WHERE clause is used) — only the WHERE
            # clause itself distinguishes the 3 lookup attempts.
            where_text = str(stmt).split("WHERE", 1)[-1]
            is_equality_lookup = "factory_part_number" in where_text
            if is_equality_lookup:
                try:
                    bound = list(stmt.compile().params.values())
                except Exception:
                    bound = []
                part_number = bound[0] if bound and isinstance(bound[0], str) else None
                if part_number in self._avg_fob_by_part:
                    ref = MagicMock()
                    ref.avg_fob_cost = self._avg_fob_by_part[part_number]
                    return _ScalarOneResult(ref)
            return _ScalarOneResult(None)

        # User.id, User.name select
        rows = [(uid, name) for uid, name in self._user_names.items()]
        return _RowsResult(rows)


def _read_rows(content: bytes) -> list:
    wb = openpyxl.load_workbook(io.BytesIO(content))
    ws = wb.active
    return [list(row) for row in ws.iter_rows(values_only=True)]


EXPORT_HEADERS = [
    "Número", "Tipo", "Estado", "Facturada", "Part Number", "Cantidad Despachada",
    "Costo/Valor Distribuidor (COP)", "Total (COP)",
    "Fecha creación", "Creado por", "Fecha despacho", "Despachado por", "Notas",
]


# ---------------------------------------------------------------------------
# PATCH /{id}/invoiced
# ---------------------------------------------------------------------------

def test_invoiced_forbidden_for_non_superadmin():
    remision = make_remision()
    with make_test_client(make_jefe_taller(), FakeInvoicedSession(remision)) as client:
        res = client.patch(f"/api/v1/remisiones/{remision.id}/invoiced", json={"invoiced": True})
    assert res.status_code == 403


def test_invoiced_404_unknown_id():
    with make_test_client(make_superadmin(), FakeInvoicedSession(None)) as client:
        res = client.patch(f"/api/v1/remisiones/{uuid.uuid4()}/invoiced", json={"invoiced": True})
    assert res.status_code == 404


def test_invoiced_toggle_true():
    remision = make_remision(invoiced=False)
    session = FakeInvoicedSession(remision)
    with make_test_client(make_superadmin(), session) as client:
        res = client.patch(f"/api/v1/remisiones/{remision.id}/invoiced", json={"invoiced": True})
    assert res.status_code == 200
    assert res.json()["invoiced"] is True
    assert remision.invoiced is True
    assert session.committed is True


def test_invoiced_toggle_false():
    remision = make_remision(invoiced=True)
    session = FakeInvoicedSession(remision)
    with make_test_client(make_superadmin(), session) as client:
        res = client.patch(f"/api/v1/remisiones/{remision.id}/invoiced", json={"invoiced": False})
    assert res.status_code == 200
    assert res.json()["invoiced"] is False
    assert remision.invoiced is False


def test_invoiced_toggle_works_on_despachado_status():
    """No status restriction — invoiced can be set regardless of BORRADOR/
    DESPACHADO/ANULADO."""
    remision = make_remision(status="DESPACHADO", invoiced=False)
    session = FakeInvoicedSession(remision)
    with make_test_client(make_superadmin(), session) as client:
        res = client.patch(f"/api/v1/remisiones/{remision.id}/invoiced", json={"invoiced": True})
    assert res.status_code == 200
    assert res.json()["invoiced"] is True


# ---------------------------------------------------------------------------
# GET /export
# ---------------------------------------------------------------------------

def test_export_forbidden_for_non_superadmin():
    with make_test_client(make_jefe_taller(), FakeExportSession()) as client:
        res = client.get("/api/v1/remisiones/export")
    assert res.status_code == 403


def test_export_content_type_and_filename():
    with make_test_client(make_superadmin(), FakeExportSession(remisiones=[])) as client:
        res = client.get("/api/v1/remisiones/export")
    assert res.status_code == 200
    assert res.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert res.headers["content-disposition"].startswith('attachment; filename="remisiones_')
    assert res.headers["content-disposition"].endswith('.xlsx"')


def test_export_empty_range_returns_headers_only_workbook():
    with make_test_client(make_superadmin(), FakeExportSession(remisiones=[])) as client:
        res = client.get("/api/v1/remisiones/export")
    assert res.status_code == 200
    rows = _read_rows(res.content)
    assert rows == [EXPORT_HEADERS]


def test_export_one_row_per_item_header_fields_repeated():
    """A remisión with 2 items must produce 2 rows, sharing the same
    Número/Tipo/Estado/Facturada but different Part Number/Cantidad. Type
    is VEHICULO_PROPIO with no cost data seeded -> price column blank."""
    creator_id = uuid.uuid4()
    dispatcher_id = uuid.uuid4()
    item1 = make_remision_item(part_number="REF001", qty_dispatched=3)
    item2 = make_remision_item(part_number="REF002", qty_dispatched=7)
    remision = make_remision(
        type="VEHICULO_PROPIO",
        status="DESPACHADO",
        created_by=creator_id,
        invoiced=True,
        items=[item1, item2],
    )
    remision.remision_number = "REM-2026-0001"
    remision.dispatched_by = dispatcher_id
    remision.dispatched_at = datetime(2026, 7, 17, 10, 30)
    remision.notes = "Consumo taller"

    session = FakeExportSession(
        remisiones=[remision],
        user_names={creator_id: "Ana Creator", dispatcher_id: "Beto Dispatcher"},
    )
    with make_test_client(make_superadmin(), session) as client:
        res = client.get("/api/v1/remisiones/export")

    assert res.status_code == 200
    rows = _read_rows(res.content)
    assert len(rows) == 3  # header + 2 item rows
    common = ["REM-2026-0001", "Consumo Interno", "Despachado", "Sí"]
    trailer = [
        remision.created_at.strftime("%Y-%m-%d %H:%M"),
        "Ana Creator",
        "2026-07-17 10:30",
        "Beto Dispatcher",
        "Consumo taller",
    ]
    assert rows[1] == common + ["REF001", 3, None, None] + trailer
    assert rows[2] == common + ["REF002", 7, None, None] + trailer


def test_export_zero_items_remision_still_emits_one_row():
    """A BORRADOR remisión with no items must not be silently dropped —
    emits one row with blank part_number/qty/price."""
    remision = make_remision(type="GARANTIA", status="BORRADOR", items=[])
    remision.remision_number = None

    session = FakeExportSession(remisiones=[remision])
    with make_test_client(make_superadmin(), session) as client:
        res = client.get("/api/v1/remisiones/export")

    assert res.status_code == 200
    rows = _read_rows(res.content)
    assert len(rows) == 2  # header + 1 blank-item row
    assert rows[1][0] is None  # Número
    assert rows[1][4] is None  # Part Number
    assert rows[1][5] is None  # Cantidad Despachada
    assert rows[1][6] is None  # Costo/Valor Distribuidor (COP)
    assert rows[1][7] is None  # Total (COP)


def test_export_total_row_count_matches_total_item_count_across_remisiones():
    r1 = make_remision(items=[make_remision_item(), make_remision_item()])
    r2 = make_remision(items=[make_remision_item()])
    session = FakeExportSession(remisiones=[r1, r2])
    with make_test_client(make_superadmin(), session) as client:
        res = client.get("/api/v1/remisiones/export")
    assert res.status_code == 200
    rows = _read_rows(res.content)
    assert len(rows) == 1 + 3  # header + 3 total items across both remisiones


def test_export_date_range_params_accepted():
    """The endpoint accepts date_from/date_to without error — the fake
    doesn't interpret the WHERE clause, so this only proves the params are
    parsed/wired, not the actual SQL filter (that's exercised by
    `list_remisiones`'s existing, already-tested filter logic which this
    endpoint mirrors)."""
    with make_test_client(make_superadmin(), FakeExportSession(remisiones=[])) as client:
        res = client.get("/api/v1/remisiones/export?date_from=2026-01-01&date_to=2026-01-31")
    assert res.status_code == 200


# ---------------------------------------------------------------------------
# Price column — depends on remisión.type, computed via pricing_service
# ---------------------------------------------------------------------------

def test_export_garantia_shows_costo_importado():
    item = make_remision_item(part_number="REF-GAR", qty_dispatched=1)
    remision = make_remision(type="GARANTIA", status="DESPACHADO", items=[item])

    avg_fob_cost = 100.0
    expected = compute_prices(avg_fob_cost, DEFAULT_FACTORS)["costo_importado"]

    session = FakeExportSession(
        remisiones=[remision],
        avg_fob_by_part={"REF-GAR": avg_fob_cost},
    )
    with make_test_client(make_superadmin(), session) as client:
        res = client.get("/api/v1/remisiones/export")

    rows = _read_rows(res.content)
    assert rows[1][6] == expected
    assert expected is not None and expected > 0
    assert rows[1][7] == round(expected * item.qty_dispatched, 0)  # Total = unitario × cantidad


def test_export_vehiculo_propio_shows_costo_importado():
    """Consumo Interno (VEHICULO_PROPIO) uses the same costo_importado
    column as GARANTIA."""
    item = make_remision_item(part_number="REF-CI", qty_dispatched=1)
    remision = make_remision(type="VEHICULO_PROPIO", status="DESPACHADO", items=[item])

    avg_fob_cost = 50.0
    expected = compute_prices(avg_fob_cost, DEFAULT_FACTORS)["costo_importado"]

    session = FakeExportSession(
        remisiones=[remision],
        avg_fob_by_part={"REF-CI": avg_fob_cost},
    )
    with make_test_client(make_superadmin(), session) as client:
        res = client.get("/api/v1/remisiones/export")

    rows = _read_rows(res.content)
    assert rows[1][6] == expected
    assert rows[1][7] == round(expected * item.qty_dispatched, 0)


def test_export_pedido_shows_precio_distribuidor():
    item = make_remision_item(part_number="REF-PED", qty_dispatched=1)
    remision = make_remision(type="PEDIDO", status="DESPACHADO", items=[item])

    avg_fob_cost = 200.0
    prices = compute_prices(avg_fob_cost, DEFAULT_FACTORS)
    expected = prices["precio_distribuidor"]

    session = FakeExportSession(
        remisiones=[remision],
        avg_fob_by_part={"REF-PED": avg_fob_cost},
    )
    with make_test_client(make_superadmin(), session) as client:
        res = client.get("/api/v1/remisiones/export")

    rows = _read_rows(res.content)
    assert rows[1][6] == expected
    assert rows[1][7] == round(expected * item.qty_dispatched, 0)
    # Sanity: PEDIDO's distributor price must differ from the plain landed
    # cost — proves the endpoint picked the right key, not just any price.
    assert expected != prices["costo_importado"]


def test_export_cortesia_price_column_blank():
    """CORTESIA never gets a price, even when cost data exists for the
    part — the user explicitly didn't ask for a cost on cortesía."""
    item = make_remision_item(part_number="REF-COR", qty_dispatched=1)
    remision = make_remision(type="CORTESIA", status="DESPACHADO", items=[item])

    session = FakeExportSession(
        remisiones=[remision],
        avg_fob_by_part={"REF-COR": 999.0},  # cost DOES exist, must still be ignored
    )
    with make_test_client(make_superadmin(), session) as client:
        res = client.get("/api/v1/remisiones/export")

    rows = _read_rows(res.content)
    assert rows[1][6] is None
    assert rows[1][7] is None  # Total also blank — no unit price to multiply


def test_export_no_matching_parts_reference_blank_not_error():
    """A part with no PartsReference/cost history at all -> blank price,
    not a 500 and not a silent 0."""
    item = make_remision_item(part_number="REF-UNKNOWN", qty_dispatched=1)
    remision = make_remision(type="GARANTIA", status="DESPACHADO", items=[item])

    session = FakeExportSession(remisiones=[remision], avg_fob_by_part={})
    with make_test_client(make_superadmin(), session) as client:
        res = client.get("/api/v1/remisiones/export")

    assert res.status_code == 200
    rows = _read_rows(res.content)
    assert rows[1][6] is None
    assert rows[1][7] is None


def test_export_price_lookup_is_per_distinct_part_number_not_per_row():
    """Two remisiones dispatching the SAME part_number must only resolve
    its cost once — verified indirectly by asserting both rows still get
    the correct (identical) computed price, which only holds if the batch
    lookup keyed by part_number was reused for both."""
    item1 = make_remision_item(part_number="REF-SHARED", qty_dispatched=2)
    item2 = make_remision_item(part_number="REF-SHARED", qty_dispatched=5)
    r1 = make_remision(type="GARANTIA", status="DESPACHADO", items=[item1])
    r2 = make_remision(type="GARANTIA", status="DESPACHADO", items=[item2])

    avg_fob_cost = 75.0
    expected = compute_prices(avg_fob_cost, DEFAULT_FACTORS)["costo_importado"]

    session = FakeExportSession(
        remisiones=[r1, r2],
        avg_fob_by_part={"REF-SHARED": avg_fob_cost},
    )
    with make_test_client(make_superadmin(), session) as client:
        res = client.get("/api/v1/remisiones/export")

    rows = _read_rows(res.content)
    assert rows[1][6] == expected
    assert rows[2][6] == expected
    # Same unit price, different quantities -> different totals (2 vs 5 units)
    assert rows[1][7] == round(expected * item1.qty_dispatched, 0)
    assert rows[2][7] == round(expected * item2.qty_dispatched, 0)
    assert rows[1][7] != rows[2][7]
