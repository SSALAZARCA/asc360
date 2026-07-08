"""
Shared fixtures/helpers for `imports_service` packing-list reconciliation tests.

Follows the project's established pattern (see tests/remisiones/conftest.py,
tests/test_parts_manual_catalog.py): import the REAL production code and
exercise it against lightweight fakes for the DB session — no live database,
no HTTP server. Excel fixtures are built with real `openpyxl` (already a hard
dependency of the app) so the parser is exercised against real, valid .xlsx
bytes instead of hand-rolled approximations.
"""
import io
import uuid
from datetime import datetime, timezone
from typing import Optional

import openpyxl


# ---------------------------------------------------------------------------
# Excel fixture builders
# ---------------------------------------------------------------------------

def build_packing_list_xlsx(
    rows: list[dict],
    sheet_name: str = "PACKING LIST",
) -> bytes:
    """
    Builds a minimal, valid Packing List (non-invoice) .xlsx: headers
    `Part #`, `Complete Description`, `Qty(PCS)`, `N.W`, `G.W`, `CBM` on row 1,
    one data row per dict in `rows` (keys: part_number, description, qty,
    nw, gw, cbm — all optional except part_number/qty).

    NOTE: `CBM` is included so `_detect_sheet_type` classifies the sheet as
    `sp_packing_list` (it requires has_part AND has_weight AND has_meas AND
    NOT has_price) — without it, multi-sheet lot-identifier preference in
    `_locate_packing_list_sheet` never engages and silently falls back to
    `wb.active` (see test_prefers_sheet_matching_lot_identifier).
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name
    ws.append(["Part #", "Complete Description", "Qty(PCS)", "N.W", "G.W", "CBM"])
    for r in rows:
        ws.append([
            r.get("part_number"),
            r.get("description"),
            r.get("qty"),
            r.get("nw", 1.0),
            r.get("gw", 1.2),
            r.get("cbm", 0.01),
        ])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_invoice_xlsx(
    rows: list[dict],
    sheet_name: str = "INVOICE",
) -> bytes:
    """
    Builds a minimal, valid Invoice .xlsx: headers `Part #`, `Model`,
    `Complete Description`, `Spanish Description`, `Qty(PCS)`, `Unit Price`,
    `Amount` on row 1, one data row per dict in `rows` (keys: part_number,
    model, description, description_es, qty, unit_price, amount).
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name
    ws.append([
        "Part #", "Model", "Complete Description", "Spanish Description",
        "Qty(PCS)", "Unit Price", "Amount",
    ])
    for r in rows:
        ws.append([
            r.get("part_number"),
            r.get("model"),
            r.get("description"),
            r.get("description_es"),
            r.get("qty"),
            r.get("unit_price"),
            r.get("amount"),
        ])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_malformed_xlsx() -> bytes:
    """An .xlsx with no recognizable Packing List/Invoice headers at all."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Foo", "Bar", "Baz"])
    ws.append(["a", "b", "c"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Lightweight ORM-instance factories (real model classes, not mocks — these
# are plain SQLAlchemy declarative instances, safe to construct without a DB)
# ---------------------------------------------------------------------------

def make_lot(lot_identifier: str = "E0000573-SP") -> "SparePartLot":
    from app.models.imports import SparePartLot
    lot = SparePartLot(
        id=uuid.uuid4(),
        shipment_order_id=uuid.uuid4(),
        lot_identifier=lot_identifier,
    )
    return lot


def make_spare_part_item(
    lot_id,
    part_number: str,
    qty_ordered: int,
    model_applicable: Optional[str] = None,
) -> "SparePartItem":
    from app.models.imports import SparePartItem
    item = SparePartItem(
        id=uuid.uuid4(),
        lot_id=lot_id,
        part_number=part_number,
        qty_ordered=qty_ordered,
        model_applicable=model_applicable,
    )
    return item


def make_backorder(
    spare_part_item_id,
    part_number: str,
    origin_pi: str,
    qty_pending: int,
    resolved: bool = False,
) -> "Backorder":
    from app.models.imports import Backorder
    return Backorder(
        id=uuid.uuid4(),
        spare_part_item_id=spare_part_item_id,
        part_number=part_number,
        origin_pi=origin_pi,
        qty_pending=qty_pending,
        resolved=resolved,
        history=[],
    )


def make_backorder_reconciliation(
    lot_id,
    file_name: str = "remainder.xlsx",
    content_hash: str = "hash",
    status: str = "PENDING",
) -> "BackorderReconciliation":
    from app.models.imports import BackorderReconciliation
    return BackorderReconciliation(
        id=uuid.uuid4(),
        lot_id=lot_id,
        file_name=file_name,
        content_hash=content_hash,
        minio_object_name=f"minio/{file_name}",
        status=status,
        is_invoice=False,
    )


def make_actor(user_id: Optional[str] = None) -> "CurrentUser":
    from app.api.deps import CurrentUser
    return CurrentUser(
        user_id=user_id or str(uuid.uuid4()),
        role="jefe_taller",
        tenant_id=None,
        name="Test User",
    )


# ---------------------------------------------------------------------------
# Fake AsyncSession — simulates just enough of AsyncSession's surface for
# `reconcile_lot_packing_list` to run end-to-end without a live database.
# ---------------------------------------------------------------------------

class _ScalarsResult:
    def __init__(self, items: list):
        self._items = items

    def all(self):
        return list(self._items)


class _ExecuteResult:
    def __init__(self, items: list):
        self._items = items

    def scalars(self):
        return _ScalarsResult(self._items)


class FakeAsyncSession:
    """
    Minimal fake standing in for `AsyncSession`.

    `execute_queue` MUST be provided in the exact order `reconcile_lot_packing_list`
    issues its `select(...)` calls today:
      1. `select(VehicleModel.model_name)`      (via `_load_models_map`)
      2. `select(ReconciliationResult)...`       (old_results for the lot)
      3. `select(PackingList)...`                (old_pls for the lot)
      4. `select(SparePartItem)...`              (lot_items_list)

    This positional coupling is intentional: it is exactly what task 2.1 asks
    for — a regression test that captures TODAY's behavior byte-for-byte, so
    the Phase 2 refactor (moving parsing into a pure helper) can be verified
    to not reorder or alter any DB interaction.
    """

    def __init__(self, execute_queue: list[list], get_objects: Optional[list] = None):
        self._execute_queue = list(execute_queue)
        self.added: list = []
        self.deleted: list = []
        self.flush_count = 0
        # Objects reachable via `db.get(Model, id)` — used by tests exercising
        # functions that fetch rows by primary key instead of `select(...)`
        # (e.g. `confirm_backorder_reconciliation`).
        self._get_objects: list = list(get_objects or [])

    async def execute(self, stmt):
        if not self._execute_queue:
            raise AssertionError(
                "FakeAsyncSession.execute() called more times than expected — "
                "the query order/count changed. Update the test's execute_queue."
            )
        return _ExecuteResult(self._execute_queue.pop(0))

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        self.added.append(obj)

    async def delete(self, obj):
        self.deleted.append(obj)

    async def flush(self):
        self.flush_count += 1

    async def get(self, model_cls, obj_id):
        for obj in self._get_objects + self.added:
            if isinstance(obj, model_cls) and obj.id == obj_id:
                return obj
        return None

    def added_of_type(self, cls) -> list:
        return [o for o in self.added if isinstance(o, cls)]
