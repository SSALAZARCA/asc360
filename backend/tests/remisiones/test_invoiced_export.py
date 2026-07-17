"""
Tests for `PATCH /remisiones/{id}/invoiced` and `GET /remisiones/export`.

Both are superadmin-only, mirroring every other endpoint in this router
(`_require_superadmin`). `invoiced` is a plain accounting flag — togglable
regardless of remisión status (BORRADOR/DESPACHADO/ANULADO).
"""
import io
import uuid
from datetime import datetime

import openpyxl

from tests.conftest import make_test_client, make_remision, make_remision_item


def make_superadmin() -> "CurrentUser":
    from app.api.deps import CurrentUser
    return CurrentUser(user_id=str(uuid.uuid4()), role="superadmin", tenant_id=None, name="Super")


def make_jefe_taller() -> "CurrentUser":
    from app.api.deps import CurrentUser
    return CurrentUser(user_id=str(uuid.uuid4()), role="jefe_taller", tenant_id=str(uuid.uuid4()), name="Jefe")


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


class FakeExportSession:
    """Minimal fake for `GET /export`: one `select(InventoryRemision)` (or
    a `Backorder`-style scalars list) followed by one `select(User.id,
    User.name)` batch lookup — dispatched by the first column's entity."""

    def __init__(self, remisiones=None, user_names: dict = None):
        self._remisiones = remisiones or []
        self._user_names = user_names or {}
        self.executed_statements = []

    async def execute(self, stmt):
        self.executed_statements.append(stmt)
        from app.models.imports import InventoryRemision

        entity = stmt.column_descriptions[0]["entity"]
        if entity is InventoryRemision:
            return _ScalarsResult(self._remisiones)
        rows = [(uid, name) for uid, name in self._user_names.items()]
        return _RowsResult(rows)


def _read_rows(content: bytes) -> list:
    wb = openpyxl.load_workbook(io.BytesIO(content))
    ws = wb.active
    return [list(row) for row in ws.iter_rows(values_only=True)]


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
    assert rows == [[
        "Número", "Tipo", "Estado", "Facturada", "Part Number", "Cantidad Despachada",
        "Fecha creación", "Creado por", "Fecha despacho", "Despachado por", "Notas",
    ]]


def test_export_one_row_per_item_header_fields_repeated():
    """A remisión with 2 items must produce 2 rows, sharing the same
    Número/Tipo/Estado/Facturada but different Part Number/Cantidad."""
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
    assert rows[1] == common + ["REF001", 3] + trailer
    assert rows[2] == common + ["REF002", 7] + trailer


def test_export_zero_items_remision_still_emits_one_row():
    """A BORRADOR remisión with no items must not be silently dropped —
    emits one row with blank part_number/qty."""
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
