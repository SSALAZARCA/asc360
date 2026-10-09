"""
Motored satisfaction survey: per-carga detail and Excel exports
(`/api/motored/encuesta/cargas/{id}/detalle`, `/{id}/excel`, `/resultados/excel`).
Same conventions as `test_encuesta_carga_api.py`: fake session, one queued
result per query (the first queued list is the readiness probe).
"""
import io
import uuid
from datetime import date, datetime
from types import SimpleNamespace

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.services import encuesta_excel, encuesta_resultados
from app.motored.services.auth import MotoredUser
from tests.motored.conftest import FakeAsyncSession, override_motored_db, override_motored_user

BASE = "/api/motored/encuesta/cargas"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
USER_ID = str(uuid.uuid4())
CARGA_ID = uuid.uuid4()
# 2026-09-30 23:30 UTC is 18:30 in Bogota; 2026-10-01 03:00 UTC is still 2026-09-30 22:00 there.
CARGA_AT = datetime(2026, 10, 1, 3, 0, 0)


@pytest.fixture(autouse=True)
def _motored_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "encuesta-res-test-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "encuesta-res-test-asc360-secret")
    override_motored_user(MotoredUser(user_id=USER_ID, role="ADMIN"))
    yield
    app.dependency_overrides.clear()


def _row(nombre="Ana Perez", cedula="0012345", celular="3001112233", centro="Cali Norte",
         nota=None, obs=None, respondida_at=None, archivo="mayo.xlsx", carga_at=CARGA_AT):
    return SimpleNamespace(
        nombre_archivo=archivo, carga_created_at=carga_at, nombre=nombre, cedula=cedula,
        celular=celular, centro_servicio=centro, satisfaccion_general=nota,
        observaciones=obs, respuesta_created_at=respondida_at,
    )


ROWS = [
    _row("Ana", nota=5, obs="Excelente", respondida_at=datetime(2026, 10, 2, 15, 0, 0)),
    _row("Beto", nota=2, obs="Mal servicio", respondida_at=datetime(2026, 10, 3, 4, 0, 0)),
    _row("Carlos", nota=3),
    _row("Dora"),
]
ROWS[2].satisfaccion_general = 3
ROWS[2].respuesta_created_at = datetime(2026, 10, 3, 5, 0, 0)


def _get(url, rows):
    session = FakeAsyncSession(execute_queue=[[], rows])
    override_motored_db(session)
    with TestClient(app) as client:
        return client.get(url), session


# --- classification and estado ---------------------------------------------

@pytest.mark.parametrize("nota,esperada", [(1, "DETRACTOR"), (3, "DETRACTOR"), (4, "SATISFECHO"), (5, "SATISFECHO"), (None, None)])
def test_categoria_reuses_the_existing_detractor_threshold(nota, esperada):
    assert encuesta_resultados.clasificar(nota) == esperada


def test_detail_derives_estado_categoria_and_utc_date():
    response, session = _get(f"{BASE}/{CARGA_ID}/detalle", ROWS)
    assert response.status_code == 200
    filas = {f["cliente"]: f for f in response.json()}
    assert filas["Ana"] == {
        "cliente": "Ana", "cedula": "0012345", "telefono": "3001112233", "tienda": "Cali Norte",
        "estado": "RESPONDIDA", "nota": 5, "categoria": "SATISFECHO", "comentario": "Excelente",
        "fecha_respuesta": "2026-10-02T15:00:00+00:00",
    }
    assert filas["Beto"]["categoria"] == "DETRACTOR"
    assert filas["Carlos"]["categoria"] == "DETRACTOR"
    assert filas["Dora"]["estado"] == "SIN_RESPONDER"
    assert filas["Dora"]["nota"] is None and filas["Dora"]["categoria"] is None
    assert filas["Dora"]["fecha_respuesta"] is None
    assert "encuesta_registro.carga_id" in str(session.executed_statements[-1])


def test_detail_unknown_carga_is_404():
    response, _ = _get(f"{BASE}/{CARGA_ID}/detalle", [])
    assert response.status_code == 404


@pytest.mark.parametrize("filtro,esperados", [
    ("todas", {"Ana", "Beto", "Carlos", "Dora"}),
    ("respondidas", {"Ana", "Beto", "Carlos"}),
    ("sin_responder", {"Dora"}),
    ("detractores", {"Beto", "Carlos"}),
])
def test_detail_filters(filtro, esperados):
    response, _ = _get(f"{BASE}/{CARGA_ID}/detalle?filtro={filtro}", ROWS)
    assert {f["cliente"] for f in response.json()} == esperados


def test_detail_rejects_unknown_filter():
    response, _ = _get(f"{BASE}/{CARGA_ID}/detalle?filtro=otra", ROWS)
    assert response.status_code == 422


# --- roles -----------------------------------------------------------------

@pytest.mark.parametrize("role", ["ADMIN", "SERVICIO_CLIENTE"])
def test_allowed_roles(role):
    override_motored_user(MotoredUser(user_id=USER_ID, role=role))
    response, _ = _get(f"{BASE}/{CARGA_ID}/detalle", ROWS)
    assert response.status_code == 200


@pytest.mark.parametrize("role", ["COMPRAS", "CONSULTA", "SUCURSAL"])
def test_other_roles_are_forbidden(role):
    override_motored_user(MotoredUser(user_id=USER_ID, role=role))
    override_motored_db(FakeAsyncSession(execute_queue=[[], [], [], []]))
    with TestClient(app) as client:
        assert client.get(f"{BASE}/{CARGA_ID}/detalle").status_code == 403
        assert client.get(f"{BASE}/{CARGA_ID}/excel").status_code == 403
        assert client.get(f"{BASE}/resultados/excel?desde=2026-10-01&hasta=2026-10-31").status_code == 403


# --- Excel per carga -------------------------------------------------------

def _sheet(response):
    return openpyxl.load_workbook(io.BytesIO(response.content)).active


def _values(sheet):
    return [[c.value for c in row] for row in sheet.iter_rows()]


def test_excel_per_carga_columns_text_cells_and_bogota_dates():
    response, _ = _get(f"{BASE}/{CARGA_ID}/excel", ROWS)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(XLSX_MIME)
    # carga at 2026-10-01 03:00 UTC is 2026-09-30 in Bogota
    assert 'filename="encuesta_mayo_2026-09-30.xlsx"' in response.headers["content-disposition"]
    values = _values(_sheet(response))
    header = next(r for r in values if r and r[0] == "Cliente")
    assert header == ["Cliente", "Cédula", "Teléfono", "Tienda", "Estado", "Nota", "Categoría",
                      "Comentario", "Fecha de respuesta", "Archivo de carga", "Fecha de envío"]
    ana = next(r for r in values if r and r[0] == "Ana")
    assert ana[1:9] == ["0012345", "3001112233", "Cali Norte", "Respondida", 5, "Satisfecho",
                        "Excelente", "2026-10-02 10:00"]
    assert ana[9:] == ["mayo.xlsx", "2026-09-30 22:00"]
    dora = next(r for r in values if r and r[0] == "Dora")
    assert dora[4] == "Sin responder" and dora[5] is None and dora[8] is None
    cells = {c.value: c for row in _sheet(response).iter_rows() for c in row if isinstance(c.value, str)}
    assert cells["0012345"].data_type == "s" and cells["0012345"].number_format == "@"
    assert cells["3001112233"].data_type == "s" and cells["3001112233"].number_format == "@"


def test_excel_per_carga_filename_is_sanitized():
    rows = [_row(archivo="Base Mayo / 2026 (final).xlsx")]
    response, _ = _get(f"{BASE}/{CARGA_ID}/excel", rows)
    assert 'filename="encuesta_Base_Mayo_2026_final_2026-09-30.xlsx"' in response.headers["content-disposition"]


def test_excel_per_carga_unknown_is_404():
    response, _ = _get(f"{BASE}/{CARGA_ID}/excel", [])
    assert response.status_code == 404


# --- Excel by range --------------------------------------------------------

RANGO = f"{BASE}/resultados/excel"


def test_range_excel_has_headers_and_filename():
    response, session = _get(f"{RANGO}?desde=2026-09-01&hasta=2026-09-30", ROWS)
    assert response.status_code == 200
    assert 'filename="encuestas_envio_2026-09-01_2026-09-30.xlsx"' in response.headers["content-disposition"]
    values = _values(_sheet(response))
    flat = [v for r in values for v in r if v is not None]
    assert any("2026-09-01" in str(v) and "2026-09-30" in str(v) for v in flat)
    assert any("fecha de envío" in str(v).lower() for v in flat)
    assert any(r and r[0] == "Cliente" for r in values)
    assert sum(1 for r in values if r and r[0] in {"Ana", "Beto", "Carlos", "Dora"}) == 4
    assert "encuesta_carga.created_at" in str(session.executed_statements[-1])


def test_range_bounds_are_inclusive_in_bogota_time():
    desde, hasta = date(2026, 9, 1), date(2026, 9, 30)
    inicio, fin = encuesta_resultados.limites_utc(desde, hasta)
    # Bogota midnight is 05:00 UTC; the whole last day is included, the next day is not.
    assert inicio == datetime(2026, 9, 1, 5, 0, 0)
    assert fin == datetime(2026, 10, 1, 5, 0, 0)
    assert inicio <= datetime(2026, 9, 1, 5, 0, 0) < fin
    assert inicio <= datetime(2026, 10, 1, 4, 59, 59) < fin
    assert not (inicio <= datetime(2026, 10, 1, 5, 0, 0) < fin)


def test_range_query_uses_those_bounds():
    _, session = _get(f"{RANGO}?desde=2026-09-01&hasta=2026-09-30", ROWS)
    params = session.executed_statements[-1].compile().params
    assert datetime(2026, 9, 1, 5, 0, 0) in params.values()
    assert datetime(2026, 10, 1, 5, 0, 0) in params.values()


def test_range_rejects_desde_after_hasta():
    response, _ = _get(f"{RANGO}?desde=2026-10-02&hasta=2026-10-01", [])
    assert response.status_code == 422


def test_range_rejects_more_than_366_days_but_accepts_exactly_366():
    response, _ = _get(f"{RANGO}?desde=2026-01-01&hasta=2027-01-02", [])
    assert response.status_code == 422
    response, _ = _get(f"{RANGO}?desde=2026-01-01&hasta=2027-01-01", [])
    assert response.status_code == 200


def test_range_requires_both_dates():
    response, _ = _get(f"{RANGO}?desde=2026-10-01", [])
    assert response.status_code == 422


def test_range_with_no_rows_still_returns_a_workbook():
    response, _ = _get(f"{RANGO}?desde=2026-09-01&hasta=2026-09-30", [])
    assert response.status_code == 200
    assert any(r and r[0] == "Cliente" for r in _values(_sheet(response)))


# --- range filtered by response date ---------------------------------------

def test_range_by_response_date_filename_header_and_query():
    response, session = _get(f"{RANGO}?desde=2026-10-01&hasta=2026-10-31&por=respuesta", ROWS[:3])
    assert response.status_code == 200
    assert 'filename="encuestas_respuesta_2026-10-01_2026-10-31.xlsx"' in response.headers["content-disposition"]
    flat = [v for r in _values(_sheet(response)) for v in r if v is not None]
    assert any("fecha de respuesta" in str(v).lower() for v in flat)
    statement = session.executed_statements[-1]
    sql = str(statement)
    assert "encuesta_respuesta.created_at >=" in sql and "encuesta_carga.created_at >=" not in sql
    params = statement.compile().params
    assert datetime(2026, 10, 1, 5, 0, 0) in params.values()
    assert datetime(2026, 11, 1, 5, 0, 0) in params.values()


def test_range_by_send_date_filters_on_the_carga_not_the_response():
    _, session = _get(f"{RANGO}?desde=2026-09-01&hasta=2026-09-30&por=envio", ROWS)
    sql = str(session.executed_statements[-1])
    assert "encuesta_carga.created_at >=" in sql and "encuesta_respuesta.created_at >=" not in sql


def test_range_rejects_unknown_por():
    response, _ = _get(f"{RANGO}?desde=2026-09-01&hasta=2026-09-30&por=otra", [])
    assert response.status_code == 422
