"""
Motored "Configuración" admin page, T1 (odd/motored-configuracion-admin):
the ADMIN-only read endpoints (`/configuracion`, `/{clave}/historial`) and
the vigencia rule of `POST /parametros`.
"""
import datetime
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.motored.api import parametros as parametros_api
from app.motored.models.parametro_metodologia import ParametroMetodologia
from app.motored.services import parametros_claves as pc
from app.motored.services.auth import MotoredUser
from tests.motored.conftest import (
    FakeAsyncSession, override_motored_db, override_motored_user,
)

URL = "/api/motored/parametros"
HOY = datetime.date(2026, 10, 15)


@pytest.fixture(autouse=True)
def _motored_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "cfg-test-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "cfg-test-asc360-secret")
    monkeypatch.setattr(parametros_api, "hoy_bogota", lambda: HOY)
    yield
    app.dependency_overrides.clear()


def _cliente(execute_queue=None, rol="ADMIN"):
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role=rol))
    db = FakeAsyncSession(execute_queue=execute_queue or [[]] * 4)
    override_motored_db(db)
    return TestClient(app), db


def _fila(clave, valor, desde):
    return ParametroMetodologia(
        id=uuid.uuid4(), clave=clave, valor=valor, vigente_desde=desde,
        created_at=datetime.datetime(2026, 9, 1, 12, 0))


# --- GET /configuracion ----------------------------------------------------

def test_configuracion_lists_every_key_grouped_by_section():
    client, _db = _cliente([[], [], []])

    respuesta = client.get(f"{URL}/configuracion")

    assert respuesta.status_code == 200, respuesta.text
    secciones = respuesta.json()["secciones"]
    assert [s["seccion"] for s in secciones] == list(pc.SECCIONES)
    claves = [c["clave"] for s in secciones for g in s["grupos"]
              for c in g["claves"]]
    assert sorted(claves) == sorted(pc.REGISTRO)


def test_configuracion_carries_type_range_scope_default_and_flag():
    client, _db = _cliente([[], [], []])

    secciones = client.get(f"{URL}/configuracion").json()["secciones"]
    pedido = next(s for s in secciones if s["seccion"] == "pedido")
    dias = next(
        c for g in pedido["grupos"] for c in g["claves"]
        if c["clave"] == "dias_entre_pedidos")

    assert dias["tipo"] == "entero"
    assert (dias["minimo"], dias["maximo"]) == (1, 60)
    assert dias["ambito"] == pc.AMBITO_GLOBAL_Y_SUCURSAL
    assert dias["default"] == 30
    assert dias["snapshotted"] is True
    assert dias["efectivo_global"]["fuente"] == "DEFAULT"
    assert dias["por_sucursal"] == [] and dias["programados"] == []


def test_configuracion_shows_the_stored_global_value():
    fila = _fila("dias_entre_pedidos", 45, datetime.date(2026, 9, 1))
    client, _db = _cliente([[], [fila], []])

    secciones = client.get(f"{URL}/configuracion").json()["secciones"]
    dias = next(
        c for s in secciones for g in s["grupos"] for c in g["claves"]
        if c["clave"] == "dias_entre_pedidos")

    assert dias["efectivo_global"]["valor"] == 45
    assert dias["efectivo_global"]["fuente"] == "GLOBAL"
    assert dias["efectivo_global"]["vigente_desde"] == "2026-09-01"


@pytest.mark.parametrize("rol", ["COMPRAS", "CONSULTA", "SUCURSAL"])
def test_configuracion_is_admin_only(rol):
    client, _db = _cliente(rol=rol)

    assert client.get(f"{URL}/configuracion").status_code == 403


# --- GET /{clave}/historial ------------------------------------------------

def test_historial_returns_versions_with_the_author_name():
    nueva = _fila("dias_ventana_ingresos", 60, datetime.date(2026, 10, 1))
    vieja = _fila("dias_ventana_ingresos", 45, datetime.date(2026, 1, 1))
    autor = uuid.uuid4()
    nueva.created_by = autor
    client, _db = _cliente([[], [(nueva, "Ana"), (vieja, None)]])

    respuesta = client.get(f"{URL}/dias_ventana_ingresos/historial")

    assert respuesta.status_code == 200, respuesta.text
    filas = respuesta.json()
    assert [f["valor"] for f in filas] == [60, 45]
    assert filas[0]["created_by_nombre"] == "Ana"
    assert filas[0]["created_by"] == str(autor)
    assert filas[0]["vigente_desde"] == "2026-10-01"
    assert filas[0]["created_at"].startswith("2026-09-01")
    assert filas[0]["sucursal_id"] is None
    assert filas[1]["created_by_nombre"] is None


def test_historial_of_a_key_without_versions_is_an_empty_list():
    client, _db = _cliente([[], []])

    respuesta = client.get(f"{URL}/umbral_f/historial")

    assert respuesta.status_code == 200 and respuesta.json() == []


@pytest.mark.parametrize("rol", ["COMPRAS", "CONSULTA", "SUCURSAL"])
def test_historial_is_admin_only(rol):
    client, _db = _cliente(rol=rol)

    assert client.get(f"{URL}/umbral_f/historial").status_code == 403


# --- POST /parametros: vigencia rule ---------------------------------------

def _post(client, clave, valor, desde):
    return client.post(URL, json={
        "clave": clave, "valor": valor, "vigente_desde": desde})


def test_post_normalizes_a_mid_month_date_to_the_first_day():
    client, db = _cliente()

    respuesta = _post(client, "dias_ventana_ingresos", 60, "2026-11-20")

    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["vigente_desde"] == "2026-11-01"
    assert db.added[0].vigente_desde == datetime.date(2026, 11, 1)


def test_post_rejects_a_past_month_for_a_snapshotted_key_and_says_why():
    client, db = _cliente()

    respuesta = _post(client, "dias_entre_pedidos", 15, "2026-09-01")

    assert respuesta.status_code == 422
    detalle = respuesta.json()["detail"]
    assert detalle["code"] == "E-PARAM-005"
    assert "mes en curso" in detalle["message"]
    assert db.added == [] and db.committed is False


def test_post_allows_the_current_month_for_a_snapshotted_key():
    client, db = _cliente()

    respuesta = _post(client, "dias_entre_pedidos", 15, "2026-10-01")

    assert respuesta.status_code == 201, respuesta.text
    assert db.added[0].vigente_desde == datetime.date(2026, 10, 1)


def test_post_allows_a_past_month_for_a_non_snapshotted_key():
    client, db = _cliente()

    respuesta = _post(client, "dias_ventana_ingresos", 60, "2026-03-01")

    assert respuesta.status_code == 201, respuesta.text
    assert db.added[0].vigente_desde == datetime.date(2026, 3, 1)


def test_post_validates_the_value_before_the_date():
    client, db = _cliente()

    respuesta = _post(client, "dias_entre_pedidos", 0, "2026-01-01")

    assert respuesta.json()["detail"]["code"] == "E-PARAM-002"
    assert "entero" in respuesta.json()["detail"]["message"]
    assert db.added == []
