"""
Regression test for `GET /imports/spare-parts/export` (`imports.py`).

Bugfix (2026-08-06): the "Repuestos" tab's Excel export (Estado de Pedidos)
listed every imported spare part but never included its `rotation_class`
(Maestro de Partes' export already had it -- this one didn't). Rotation
lives on `PartsReference`, keyed by `factory_part_number`, not on
`SparePartItem` itself, so this requires a second batched lookup joined by
`part_number` -- same "one extra IN-query, not N+1" discipline
`export_catalog_excel` already uses for its own `extra` dict.

`sdd/parts-description-source-of-truth` PR4 (R4, design D11-D14) extended
this SAME batched select to also carry `description_es_manual` -- the
`PartsReference` query fixture below now queues a 3-tuple
`(factory_part_number, rotation_class, description_es_manual)` instead of
a 2-tuple. `DESCRIPCIÓN ES` now reflects the LIVE catalog name (manual
wins over the stale stored value), not the frozen `SparePartItem
.description_es` from import time -- see
`test_live_read_description_es.py::TestR4SparePartsExport` for the
dedicated manual-name-wins coverage.
"""
import uuid
from decimal import Decimal

import openpyxl

from app.models.imports import SparePartLot, SparePartItem
from app.models.parts_manual import PartsReference

from tests.conftest import make_test_client
from tests.imports.conftest import FakeAsyncSession, make_imports_editor


def _lot(**overrides):
    defaults = dict(
        id=uuid.uuid4(),
        shipment_order_id=uuid.uuid4(),
        lot_identifier="E0000600-SP",
        detail_loaded=True,
    )
    defaults.update(overrides)
    return SparePartLot(**defaults)


def _item(lot_id, **overrides):
    defaults = dict(
        id=uuid.uuid4(),
        lot_id=lot_id,
        part_number="4510A-ADAN-9000",
        description="BRAKE PAD",
        description_es="PASTILLA DE FRENO",
        model_applicable="RENEGADE SPORT 200",
        qty_ordered=10,
        qty_received=10,
        qty_pending=0,
        status="RECEIVED",
        backorder_pi=None,
        unit_price=Decimal("3.94"),
        amount=Decimal("39.40"),
    )
    defaults.update(overrides)
    return SparePartItem(**defaults)


def _superadmin():
    return make_imports_editor(role="superadmin")


def _read_rows(response):
    wb = openpyxl.load_workbook(io_from(response.content))
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    return rows[0], rows[1:]


def io_from(content: bytes):
    import io
    return io.BytesIO(content)


class TestRotationColumn:
    def test_export_includes_rotation_class_looked_up_by_part_number(self):
        lot = _lot()
        lot.items = [_item(lot.id, part_number="4510A-ADAN-9000")]
        fake_db = FakeAsyncSession(execute_queue=[
            [lot],
            [("4510A-ADAN-9000", "alta", None)],  # no manual name -> stored value stays
        ])

        with make_test_client(current_user=_superadmin(), fake_db_session=fake_db) as client:
            response = client.get("/api/v1/imports/spare-parts/export")

        assert response.status_code == 200
        headers, rows = _read_rows(response)
        assert "ROTACIÓN" in headers
        rotation_idx = headers.index("ROTACIÓN")
        assert rows[0][rotation_idx] == "ALTA"

    def test_export_leaves_rotation_blank_when_part_has_no_reference_or_no_class(self):
        lot = _lot()
        lot.items = [_item(lot.id, part_number="UNKNOWN-PART")]
        fake_db = FakeAsyncSession(execute_queue=[
            [lot],
            [],  # no matching PartsReference row at all
        ])

        with make_test_client(current_user=_superadmin(), fake_db_session=fake_db) as client:
            response = client.get("/api/v1/imports/spare-parts/export")

        assert response.status_code == 200
        headers, rows = _read_rows(response)
        rotation_idx = headers.index("ROTACIÓN")
        assert rows[0][rotation_idx] in (None, "")

    def test_export_with_no_lots_still_returns_a_headered_workbook(self):
        fake_db = FakeAsyncSession(execute_queue=[
            [],
            [],
        ])

        with make_test_client(current_user=_superadmin(), fake_db_session=fake_db) as client:
            response = client.get("/api/v1/imports/spare-parts/export")

        assert response.status_code == 200
        headers, rows = _read_rows(response)
        assert "ROTACIÓN" in headers
        assert rows == []
