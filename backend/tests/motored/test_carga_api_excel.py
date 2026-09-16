"""
Batch: `.xlsx` bulk-upload HTTP surface (sdd/motored-pedidos-cimientos,
post-Fase-6, owner brief "Excel upload capability").

Mirrors `test_carga_api.py`'s conventions exactly, but drives the new
multipart file endpoints (`/carga/excel/validar`, `/carga/excel`) instead of
the JSON-rows ones. Proves: correct parsing+upsert through the SAME
`validate_rows`/`procesar_carga` codepath as the JSON path (by asserting the
identical `session.committed`/`insertados` outcome for an equivalent file),
RBAC parity, and that the row-count/`.xls` guards reject before any
DB-writing query.
"""
import io
import uuid

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.models.proveedor import Proveedor
from app.motored.services.auth import MotoredUser
from tests.motored.conftest import FakeAsyncSession, override_motored_db, override_motored_user

VALIDAR_EXCEL_URL = "/api/motored/maestros/sucursal/carga/excel/validar"
CARGA_EXCEL_URL = "/api/motored/maestros/sucursal/carga/excel"
CARGA_EXCEL_REFERENCIA_URL = "/api/motored/maestros/referencia/carga/excel"


def _xlsx_bytes(headers, rows):
    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _upload_file(name, content):
    return {
        "file": (
            name,
            content,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }


@pytest.fixture(autouse=True)
def _motored_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "carga-excel-test-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "carga-excel-test-asc360-secret")
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN"))
    yield
    app.dependency_overrides.clear()


def test_validar_excel_with_valid_file_writes_nothing():
    session = FakeAsyncSession(execute_queue=[[]])  # only the readiness probe
    override_motored_db(session)
    file_bytes = _xlsx_bytes(["Nombre"], [["CALI NORTE"]])

    with TestClient(app) as client:
        response = client.post(VALIDAR_EXCEL_URL, files=_upload_file("sucursales.xlsx", file_bytes))

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert session.added == []
    assert session.committed is False


def test_validar_excel_with_missing_required_column_reports_error_and_writes_nothing():
    session = FakeAsyncSession(execute_queue=[[]])
    override_motored_db(session)
    file_bytes = _xlsx_bytes(["SIC"], [["S001"]])

    with TestClient(app) as client:
        response = client.post(VALIDAR_EXCEL_URL, files=_upload_file("sucursales.xlsx", file_bytes))

    assert response.status_code == 400
    assert "Nombre" in response.json()["detail"]
    assert session.added == []
    assert session.committed is False


def test_carga_excel_with_fully_valid_file_commits_atomically_same_as_json_path():
    """Same 1-row sucursal upsert as
    `test_carga_api.py::test_carga_with_fully_valid_file_commits_atomically`
    -- proves the Excel path reaches the exact same `procesar_carga`
    codepath (same execute_queue shape: probe + get-by-nombre lookup)."""
    session = FakeAsyncSession(execute_queue=[[], []])
    override_motored_db(session)
    file_bytes = _xlsx_bytes(["Nombre"], [["CALI NORTE  "]])

    with TestClient(app) as client:
        response = client.post(CARGA_EXCEL_URL, files=_upload_file("sucursales.xlsx", file_bytes))

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["insertados"] == 1
    assert session.committed is True


def test_carga_excel_with_invalid_row_rejects_whole_file_and_writes_nothing():
    session = FakeAsyncSession(execute_queue=[[]])
    override_motored_db(session)
    # Row 2 has a blank Nombre but a populated SIC -- NOT a fully-blank row
    # (which would be silently skipped, mirroring papaparse's
    # `skipEmptyLines`), so it reaches validation and is correctly reported
    # as invalid.
    file_bytes = _xlsx_bytes(["Nombre", "SIC"], [["CALI NORTE", "S001"], ["", "S002"]])

    with TestClient(app) as client:
        response = client.post(CARGA_EXCEL_URL, files=_upload_file("sucursales.xlsx", file_bytes))

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert len(body["errores"]) == 1
    assert session.added == []
    assert session.committed is False


def test_carga_excel_rejects_oversized_row_count_before_any_db_write(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_MAX_UPLOAD_ROWS", 1)
    session = FakeAsyncSession(execute_queue=[[]])
    override_motored_db(session)
    file_bytes = _xlsx_bytes(["Nombre"], [["A"], ["B"]])

    with TestClient(app) as client:
        response = client.post(CARGA_EXCEL_URL, files=_upload_file("sucursales.xlsx", file_bytes))

    assert response.status_code == 422
    assert session.added == []
    assert session.committed is False


def test_carga_excel_rejects_xls_extension_with_a_clear_message():
    session = FakeAsyncSession(execute_queue=[[]])
    override_motored_db(session)

    with TestClient(app) as client:
        response = client.post(
            CARGA_EXCEL_URL,
            files={"file": ("sucursales.xls", b"legacy binary content", "application/vnd.ms-excel")},
        )

    assert response.status_code == 400
    assert ".xls" in response.json()["detail"]
    assert session.added == []
    assert session.committed is False


def test_carga_excel_rejects_corrupt_file_with_400_not_500():
    session = FakeAsyncSession(execute_queue=[[]])
    override_motored_db(session)

    with TestClient(app) as client:
        response = client.post(
            CARGA_EXCEL_URL,
            files=_upload_file("sucursales.xlsx", b"not a real xlsx file"),
        )

    assert response.status_code == 400
    assert session.added == []
    assert session.committed is False


def test_carga_excel_referencia_resolves_proveedor_codigo_to_proveedor_id():
    proveedor_id = uuid.uuid4()
    proveedor = Proveedor(id=proveedor_id, codigo="HMCL", nombre="HMCL", es_principal=True)
    # probe, proveedor-codigo-resolution query, get_referencia_by_codigo_proveedor (no match)
    session = FakeAsyncSession(execute_queue=[[], [proveedor], []])
    override_motored_db(session)
    file_bytes = _xlsx_bytes(["Código", "Código proveedor"], [["REF1", "HMCL"]])

    with TestClient(app) as client:
        response = client.post(CARGA_EXCEL_REFERENCIA_URL, files=_upload_file("referencias.xlsx", file_bytes))

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True, body
    assert body["insertados"] == 1


def test_non_admin_compras_role_is_rejected_with_403(monkeypatch):
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role="CONSULTA"))
    session = FakeAsyncSession(execute_queue=[[]])
    override_motored_db(session)
    file_bytes = _xlsx_bytes(["Nombre"], [["CALI NORTE"]])

    with TestClient(app) as client:
        response = client.post(CARGA_EXCEL_URL, files=_upload_file("sucursales.xlsx", file_bytes))

    assert response.status_code == 403
    assert session.added == []
    assert session.committed is False
