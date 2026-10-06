"""
Motored satisfaction survey, slice T3: customer-base Excel upload API
(`/api/motored/encuesta/cargas*`). Same conventions as
`test_carga_api_excel.py`: xlsx built in memory, multipart post, fake session.
"""
import io
import uuid
from datetime import datetime
from types import SimpleNamespace

import openpyxl
import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.auth import create_motored_token
from app.motored.deps import get_motored_user_lookup
from app.motored.models.encuesta_carga import EncuestaCarga
from app.motored.models.encuesta_registro import EncuestaRegistro
from app.motored.services.auth import MotoredUser
from tests.motored.conftest import FakeAsyncSession, override_motored_db, override_motored_user

BASE = "/api/motored/encuesta/cargas"
VALIDAR_URL = f"{BASE}/validar"
PLANTILLA_URL = f"{BASE}/plantilla"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
HEADERS = ["Nombre", "Cédula", "Celular", "Línea", "Placa", "SIC", "Centro de servicio", "Tipo"]
USER_ID = str(uuid.uuid4())


def _xlsx_bytes(headers, rows):
    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _upload(name, content):
    return {"file": (name, content, XLSX_MIME)}


def _row(nombre="Ana Perez", cedula="12345678", celular="3001112233", linea="Xtreet 401",
         placa="ABC12D", sic="S001", centro="Cali Norte", tipo="Servicio taller"):
    return [nombre, cedula, celular, linea, placa, sic, centro, tipo]


def _post(url, headers, rows, name="base.xlsx", session=None):
    session = session or FakeAsyncSession(execute_queue=[[]])
    override_motored_db(session)
    with TestClient(app) as client:
        response = client.post(url, files=_upload(name, _xlsx_bytes(headers, rows)))
    return response, session


@pytest.fixture(autouse=True)
def _motored_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "encuesta-carga-test-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "encuesta-carga-test-asc360-secret")
    override_motored_user(MotoredUser(user_id=USER_ID, role="ADMIN"))
    yield
    app.dependency_overrides.clear()


# --- roles -----------------------------------------------------------------

@pytest.mark.parametrize("role", ["ADMIN", "SERVICIO_CLIENTE"])
def test_allowed_roles_can_validate(role):
    override_motored_user(MotoredUser(user_id=USER_ID, role=role))
    response, _ = _post(VALIDAR_URL, HEADERS, [_row()])
    assert response.status_code == 200


@pytest.mark.parametrize("role", ["COMPRAS", "CONSULTA", "SUCURSAL"])
def test_other_roles_are_forbidden_everywhere(role):
    override_motored_user(MotoredUser(user_id=USER_ID, role=role))
    session = FakeAsyncSession(execute_queue=[[], [], [], []])  # one readiness probe per request
    override_motored_db(session)
    with TestClient(app) as client:
        assert client.post(VALIDAR_URL, files=_upload("b.xlsx", _xlsx_bytes(HEADERS, [_row()]))).status_code == 403
        assert client.post(BASE, files=_upload("b.xlsx", _xlsx_bytes(HEADERS, [_row()]))).status_code == 403
        assert client.get(BASE).status_code == 403
        assert client.get(PLANTILLA_URL).status_code == 403
    assert session.added == [] and session.committed is False


def test_servicio_cliente_reaches_routes_through_real_confinement():
    async def _lookup(user_id: str):
        return MotoredUser(user_id=user_id, role="SERVICIO_CLIENTE")

    app.dependency_overrides.clear()
    app.dependency_overrides[get_motored_user_lookup] = lambda: _lookup
    override_motored_db(FakeAsyncSession(execute_queue=[[], [], [], []]))
    token = create_motored_token(sub=USER_ID, role="SERVICIO_CLIENTE")
    auth = {"Authorization": f"Bearer {token}"}
    with TestClient(app) as client:
        response = client.get(PLANTILLA_URL, headers=auth)
        listing = client.get(BASE, headers=auth)
        denied = client.get("/api/motored/maestros/sucursales", headers=auth)
    assert response.status_code == 200
    assert listing.status_code == 200
    assert denied.status_code == 403


# --- template --------------------------------------------------------------

def test_plantilla_downloads_xlsx_with_expected_headers():
    with TestClient(app) as client:
        override_motored_db(FakeAsyncSession(execute_queue=[[]]))
        response = client.get(PLANTILLA_URL)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(XLSX_MIME)
    assert "plantilla_encuesta.xlsx" in response.headers["content-disposition"]
    sheet = openpyxl.load_workbook(io.BytesIO(response.content)).active
    assert [c.value for c in sheet[1]] == HEADERS


# --- dry run and commit ----------------------------------------------------

def test_validar_valid_file_writes_nothing():
    response, session = _post(VALIDAR_URL, HEADERS, [_row(), _row(cedula="999", placa="XYZ99A")])
    body = response.json()
    assert body["ok"] is True
    assert body["total_filas"] == 2
    assert body["errores"] == []
    assert session.added == [] and session.committed is False


def test_commit_creates_one_carga_and_registros_in_one_transaction():
    response, session = _post(BASE, HEADERS, [_row(), _row(cedula="999", placa="XYZ99A")], name="mayo.xlsx")
    body = response.json()
    assert body["ok"] is True
    assert body["insertados"] == 2
    assert session.committed is True
    cargas = session.added_of_type(EncuestaCarga)
    registros = session.added_of_type(EncuestaRegistro)
    assert len(cargas) == 1 and len(registros) == 2
    assert cargas[0].nombre_archivo == "mayo.xlsx"
    assert cargas[0].total_registros == 2
    assert str(cargas[0].usuario_id) == USER_ID
    assert body["carga_id"] == str(cargas[0].id)
    assert all(r.carga_id == cargas[0].id for r in registros)
    first = registros[0]
    assert (first.nombre, first.cedula, first.celular, first.linea) == ("Ana Perez", "12345678", "3001112233", "Xtreet 401")
    assert (first.placa, first.sic, first.centro_servicio, first.tipo) == ("ABC12D", "S001", "Cali Norte", "SERVICIO_TALLER")


def test_commit_invalid_file_rejects_all_and_writes_nothing():
    response, session = _post(BASE, HEADERS, [_row(), _row(nombre="", cedula="55")])
    body = response.json()
    assert response.status_code == 200
    assert body["ok"] is False
    assert body["insertados"] == 0
    assert [e["fila"] for e in body["errores"]] == [2]
    assert session.added == [] and session.committed is False


def test_optional_columns_blank_are_stored_as_null_and_may_be_absent():
    headers = ["Nombre", "Cédula", "Celular", "Placa", "Tipo"]
    response, session = _post(BASE, headers, [["Ana", "1", "3001112233", "abc12d", "Venta"]])
    assert response.json()["ok"] is True
    reg = session.added_of_type(EncuestaRegistro)[0]
    assert (reg.linea, reg.sic, reg.centro_servicio) == (None, None, None)

    response, session = _post(BASE, HEADERS, [_row(linea="", sic="", centro="")])
    reg = session.added_of_type(EncuestaRegistro)[0]
    assert (reg.linea, reg.sic, reg.centro_servicio) == (None, None, None)


# --- normalization ---------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("12.345.678", "12345678"),
    (" 12 345-678 ", "12345678"),
    (12345678, "12345678"),
    (12345678.0, "12345678"),
])
def test_cedula_is_normalized_to_digits(raw, expected):
    _, session = _post(BASE, HEADERS, [_row(cedula=raw)])
    assert session.added_of_type(EncuestaRegistro)[0].cedula == expected


def test_placa_is_uppercased_and_stripped_of_spaces_and_dashes():
    _, session = _post(BASE, HEADERS, [_row(placa=" abc-12 d ")])
    assert session.added_of_type(EncuestaRegistro)[0].placa == "ABC12D"


def test_celular_is_digits_only_text():
    _, session = _post(BASE, HEADERS, [_row(celular=3001112233), _row(celular="+57 300-111 2244", cedula="2")])
    regs = session.added_of_type(EncuestaRegistro)
    assert [r.celular for r in regs] == ["3001112233", "573001112244"]


@pytest.mark.parametrize("raw,expected", [
    ("Servicio taller", "SERVICIO_TALLER"),
    ("servicio de taller", "SERVICIO_TALLER"),
    ("TALLER", "SERVICIO_TALLER"),
    ("SERVICIO_TALLER", "SERVICIO_TALLER"),
    ("Venta", "VENTA"),
    ("VENTA", "VENTA"),
    (" venta ", "VENTA"),
])
def test_tipo_synonyms_are_accepted(raw, expected):
    _, session = _post(BASE, HEADERS, [_row(tipo=raw)])
    assert session.added_of_type(EncuestaRegistro)[0].tipo == expected


def test_header_aliases_are_accent_and_case_insensitive():
    headers = ["nombre cliente", "CEDULA", "celular", "linea", "PLACA", "sic", "Nombre del centro de servicio", "tipo"]
    response, session = _post(BASE, headers, [_row()])
    assert response.json()["ok"] is True
    assert session.added_of_type(EncuestaRegistro)[0].centro_servicio == "Cali Norte"
    headers = ["Nombre", "Cedula", "Celular", "Linea", "Placa", "SIC", "Centro servicio", "TIPO"]
    response, _ = _post(VALIDAR_URL, headers, [_row()])
    assert response.json()["ok"] is True


# --- validation errors -----------------------------------------------------

def _errors(rows):
    response, session = _post(VALIDAR_URL, HEADERS, rows)
    body = response.json()
    assert response.status_code == 200 and body["ok"] is False
    assert session.added == [] and session.committed is False
    return body["errores"]


def test_each_required_field_reports_its_row():
    errores = _errors([
        _row(),
        _row(nombre="", cedula="1", placa="A1"),
        _row(cedula="", placa="A2"),
        _row(cedula="---", placa="A3"),
        _row(cedula="2", placa=""),
        _row(cedula="3", placa="A5", tipo=""),
    ])
    assert [e["fila"] for e in errores] == [2, 3, 4, 5, 6]
    assert "Nombre" in errores[0]["motivo"]
    assert "Cédula" in errores[1]["motivo"]
    assert "Cédula" in errores[2]["motivo"]
    assert "Placa" in errores[3]["motivo"]
    assert "Tipo" in errores[4]["motivo"]


@pytest.mark.parametrize("celular", ["", None, "---"])
def test_blank_celular_is_a_row_error(celular):
    errores = _errors([_row(celular=celular)])
    assert errores[0]["fila"] == 1
    assert errores[0]["motivo"] == "Celular es obligatorio"


@pytest.mark.parametrize("celular", ["123456", "30-01 1"])
def test_celular_with_fewer_than_7_digits_is_invalid(celular):
    errores = _errors([_row(celular=celular)])
    assert errores[0]["motivo"] == "Celular inválido"


def test_celular_with_7_digits_is_accepted():
    response, _ = _post(VALIDAR_URL, HEADERS, [_row(celular="1234567")])
    assert response.json()["ok"] is True


def test_cedula_longer_than_32_digits_is_an_error():
    errores = _errors([_row(cedula="1" * 33)])
    assert errores[0]["fila"] == 1
    assert "32" in errores[0]["motivo"]


def test_unknown_tipo_lists_accepted_values():
    errores = _errors([_row(tipo="Garantia")])
    assert errores[0]["fila"] == 1
    assert "Servicio taller" in errores[0]["motivo"] and "Venta" in errores[0]["motivo"]


def test_in_file_duplicate_flags_the_later_row_only():
    errores = _errors([_row(), _row(cedula="999", placa="Z1"), _row(cedula="12.345.678", placa="abc-12d")])
    assert [e["fila"] for e in errores] == [3]
    assert "duplicad" in errores[0]["motivo"].lower()


def test_same_cedula_placa_with_different_tipo_is_not_a_duplicate():
    response, _ = _post(VALIDAR_URL, HEADERS, [_row(), _row(tipo="Venta")])
    assert response.json()["ok"] is True


def test_multiple_errors_are_all_reported():
    errores = _errors([_row(nombre=""), _row(cedula="2", tipo="x")])
    assert [e["fila"] for e in errores] == [1, 2]


# --- file-level guards -----------------------------------------------------

def test_missing_required_column_is_a_400_and_writes_nothing():
    response, session = _post(BASE, ["Nombre", "Cédula", "Placa"], [["Ana", "1", "A1"]])
    assert response.status_code == 400
    assert "Tipo" in response.json()["detail"]
    assert session.added == [] and session.committed is False


def test_missing_celular_column_is_a_400_and_writes_nothing():
    response, session = _post(BASE, ["Nombre", "Cédula", "Placa", "Tipo"], [["Ana", "1", "A1", "Venta"]])
    assert response.status_code == 400
    assert "Celular" in response.json()["detail"]
    assert session.added == [] and session.committed is False


def test_xls_is_rejected():
    response, _ = _post(VALIDAR_URL, HEADERS, [_row()], name="base.xls")
    assert response.status_code == 400
    assert ".xls" in response.json()["detail"]


def test_row_cap_is_enforced(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_MAX_UPLOAD_ROWS", 2)
    rows = [_row(cedula=str(i), placa=f"P{i}") for i in range(3)]
    response, session = _post(BASE, HEADERS, rows)
    assert response.status_code == 422
    assert session.added == [] and session.committed is False


def test_oversized_content_length_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_MAX_UPLOAD_MB", 1)
    override_motored_db(FakeAsyncSession(execute_queue=[[]]))
    with TestClient(app) as client:
        response = client.post(
            BASE, files=_upload("b.xlsx", b"x"), headers={"content-length": str(5 * 1024 * 1024)}
        )
    assert response.status_code == 413


def test_oversized_body_without_header_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_MAX_UPLOAD_MB", 1)
    override_motored_db(FakeAsyncSession(execute_queue=[[]]))
    with TestClient(app) as client:
        response = client.post(BASE, files=_upload("b.xlsx", b"x" * (1024 * 1024 + 10)))
    assert response.status_code == 413


# --- warnings --------------------------------------------------------------

def test_venta_rows_produce_a_warning_but_are_stored():
    rows = [_row(tipo="Venta"), _row(cedula="2", placa="B2", tipo="venta"), _row(cedula="3", placa="C3")]
    response, session = _post(BASE, HEADERS, rows)
    body = response.json()
    assert body["ok"] is True and body["insertados"] == 3
    assert body["advertencias"] == ["2 registros de Venta se guardaron pero aún no se encuestan"]
    assert len(session.added_of_type(EncuestaRegistro)) == 3


def test_venta_warning_also_shows_in_dry_run_and_is_absent_when_none():
    response, _ = _post(VALIDAR_URL, HEADERS, [_row(tipo="Venta")])
    assert response.json()["advertencias"] == ["1 registros de Venta se guardaron pero aún no se encuestan"]
    response, _ = _post(VALIDAR_URL, HEADERS, [_row()])
    assert response.json()["advertencias"] == []


# --- list ------------------------------------------------------------------

def test_list_returns_batches_with_answered_counts():
    cid = uuid.uuid4()
    created = datetime(2026, 9, 29, 12, 0, 0)
    row = SimpleNamespace(
        id=cid, nombre_archivo="mayo.xlsx", total_registros=10, created_at=created,
        usuario_nombre="Agente SC", respondidos=4,
    )
    session = FakeAsyncSession(execute_queue=[[], [row]])
    override_motored_db(session)
    with TestClient(app) as client:
        response = client.get(BASE)
    assert response.status_code == 200
    assert response.json() == [{
        "id": str(cid), "nombre_archivo": "mayo.xlsx", "total_registros": 10,
        "created_at": "2026-09-29T12:00:00+00:00", "usuario": "Agente SC", "respondidos": 4,
    }]
    assert "encuesta_carga" in str(session.executed_statements[-1])
    assert "ORDER BY encuesta_carga.created_at DESC" in str(session.executed_statements[-1])
