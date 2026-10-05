"""
Ad-hoc bugfix (asc360, NOT tracked under any sdd/* change): server-side
`.xlsx` template generation for the Maestros bulk-upload modal.

Replaces the old client-side CSV template built in the browser
(`BulkUploadModal.js::downloadTemplate`, removed) -- that version never
wrote a UTF-8 BOM, so Excel on Windows misread the charset and showed
broken accents (e.g. "CÃ³digo" instead of "Código").

`GET /api/motored/maestros/{entidad}/plantilla.xlsx` -- `entidad` is
SINGULAR (sucursal|bodega|proveedor|referencia), the SAME convention
`api/carga.py`'s bulk-upload router already uses (`_entidad_or_404`, reused
directly here) -- NOT the plural convention `maestros.py`'s own CRUD
endpoints use for `{entidad}` (sucursales|bodegas|...). Column labels/order
come straight from `carga_excel.py::ALIASES_POR_ENTIDAD`, the same list
already used to PARSE an uploaded `.xlsx` -- one source of truth, never
duplicated a third time.
"""
import io
import uuid

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.services.auth import MotoredUser
from tests.motored.conftest import override_motored_user


def _plantilla_url(entidad: str) -> str:
    return f"/api/motored/maestros/{entidad}/plantilla.xlsx"


@pytest.fixture(autouse=True)
def _motored_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "plantilla-test-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "plantilla-test-asc360-secret")
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN"))
    yield
    app.dependency_overrides.clear()


def _header_row(content: bytes):
    workbook = openpyxl.load_workbook(io.BytesIO(content))
    try:
        return [cell.value for cell in next(workbook.active.iter_rows(max_row=1))]
    finally:
        workbook.close()


def test_plantilla_referencia_returns_valid_xlsx_with_all_columns_in_order():
    with TestClient(app) as client:
        response = client.get(_plantilla_url("referencia"))

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert response.headers["content-disposition"] == 'attachment; filename="plantilla_referencia.xlsx"'
    assert _header_row(response.content) == [
        "Código",
        "Código del proveedor",
        "Nombre",
        "Línea comercial",
        "Unidad de empaque",
        "Precio Normal antes de IVA",
        "Precio Público antes de IVA",
        "Código de referencia sustituta",
        "Homologados otras marcas",
    ]


def test_plantilla_sucursal_returns_expected_headers_in_order():
    with TestClient(app) as client:
        response = client.get(_plantilla_url("sucursal"))

    assert response.status_code == 200
    header = _header_row(response.content)
    assert header[0] == "Nombre"
    assert "SIC" in header
    assert header[-2:] == ["Activa", "Sucursal principal"]


def test_plantilla_bodega_and_proveedor_also_round_trip():
    with TestClient(app) as client:
        bodega_response = client.get(_plantilla_url("bodega"))
        proveedor_response = client.get(_plantilla_url("proveedor"))

    assert _header_row(bodega_response.content) == ["Código", "Descripción"]
    assert _header_row(proveedor_response.content)[0] == "Código"


def test_plantilla_unknown_entidad_returns_404():
    with TestClient(app) as client:
        response = client.get(_plantilla_url("no-existe"))

    assert response.status_code == 404


def test_plantilla_rejects_non_admin_compras_role_with_403():
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role="CONSULTA"))

    with TestClient(app) as client:
        response = client.get(_plantilla_url("sucursal"))

    assert response.status_code == 403


def test_plantilla_allows_compras_role():
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role="COMPRAS"))

    with TestClient(app) as client:
        response = client.get(_plantilla_url("proveedor"))

    assert response.status_code == 200
