"""
Regression tests for controlled 422s on malformed Excel uploads across the
3 endpoints that call `_parse_physical_inspection_excel`/
`_parse_backorder_bulk_excel` (`imports.py`).

Bug fixed: both parse helpers called `openpyxl.load_workbook` with no
try/except. A corrupt or non-xlsx file raised an UNCAUGHT exception,
surfacing as a raw 500 to the client — unlike `create_sp_order_from_excel`'s
caller (`new_order_sp_from_excel`), which already catches its own parse
`ValueError` and returns a clean 422 `INVALID_COLUMNS`. This closes the
same gap: both parse helpers now catch the underlying openpyxl exception
and re-raise a `ValueError` with a readable message, and every caller
catches that `ValueError` and returns HTTP 422.
"""
from tests.conftest import make_test_client
from tests.imports.conftest import FakeAsyncSession, make_imports_editor, make_lot


def _garbage_file():
    return {"file": ("broken.xlsx", b"this is not a real xlsx file", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}


class TestPhysicalInspectionPreviewMalformedExcel:

    def test_corrupt_file_returns_422_not_500(self):
        lot = make_lot(packing_list_received=True)
        fake_db = FakeAsyncSession(execute_queue=[], get_objects=[lot])

        with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
            response = client.post(
                f"/api/v1/imports/lots/{lot.id}/physical-inspection-preview",
                files=_garbage_file(),
            )

        assert response.status_code == 422
        assert "no se pudo leer el archivo excel" in response.json()["detail"].lower()


class TestBackorderBulkResolvePreviewMalformedExcel:

    def test_corrupt_file_returns_422_not_500(self):
        fake_db = FakeAsyncSession(execute_queue=[])

        with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
            response = client.post(
                "/api/v1/imports/backorders/bulk-resolve-preview",
                files=_garbage_file(),
            )

        assert response.status_code == 422
        assert "no se pudo leer el archivo excel" in response.json()["detail"].lower()


class TestBackorderBulkResolveApplyMalformedExcel:

    def test_corrupt_file_returns_422_not_500(self):
        fake_db = FakeAsyncSession(execute_queue=[])

        with make_test_client(current_user=make_imports_editor(), fake_db_session=fake_db) as client:
            response = client.post(
                "/api/v1/imports/backorders/bulk-resolve-apply",
                files=_garbage_file(),
            )

        assert response.status_code == 422
        assert "no se pudo leer el archivo excel" in response.json()["detail"].lower()
