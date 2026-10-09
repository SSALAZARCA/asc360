"""
Inventory counts, the leader's store locations (odd/motored-conteos-
inventario, WU8; design §4.3, §6.1).

`GET/POST /conteos/{id}/ubicaciones` and `PATCH .../{ubicacion_id}`:
the locations of the conteo's store, with their `origen` (a 'PAREJA' one
was typed by a pair during a count). Same scoping as WU6: ADMIN all, a
leader only its own conteos (404 otherwise), GERENCIA read-only.

Same seams as `test_conteos_api.py`: the conteo comes from `get_queue`
(the scoping lookup); the service's queries from `execute_queue`.
"""
import datetime
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.sql.dml import Insert

from app.config import settings
from app.main import app
from app.motored.models.ubicacion_inventario import UbicacionInventario
from tests.motored.conftest import (
    FakeAsyncSession, override_motored_db, override_motored_user,
)
from tests.motored.test_conteos_api import (
    LIDER_ID, OTRO_LIDER_ID, _conteo, _usuario,
)

BASE = "/api/motored/conteos"
UTC = datetime.timezone.utc


@pytest.fixture(autouse=True)
def _listo(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "conteos-ubic")
    monkeypatch.setattr(settings, "SECRET_KEY", "conteos-ubic-asc360")
    yield
    app.dependency_overrides.clear()


def _ubicacion(conteo, codigo="A3", origen="LIDER", activa=True):
    return UbicacionInventario(
        id=uuid.uuid4(), sucursal_id=conteo.sucursal_id, codigo=codigo,
        nombre=f"Estante {codigo}", activa=activa, origen=origen,
        created_at=datetime.datetime(2026, 10, 9, tzinfo=UTC))


def _llamar(rol, metodo, ruta, conteo, cola=(), json=None):
    override_motored_user(_usuario(rol))
    db = FakeAsyncSession(
        execute_queue=[[]] + list(cola), get_queue=[conteo])
    override_motored_db(db)
    respuesta = TestClient(app).request(
        metodo, f"{BASE}/{conteo.id}{ruta}", json=json)
    return respuesta, db


@pytest.mark.parametrize("rol", ["ADMIN", "LIDER_INVENTARIOS", "GERENCIA"])
def test_readers_list_the_store_locations_with_their_origin(rol):
    conteo = _conteo()
    filas = [_ubicacion(conteo), _ubicacion(conteo, "B9", "PAREJA", False)]

    r, _ = _llamar(rol, "GET", "/ubicaciones", conteo, [filas])

    assert r.status_code == 200, r.text
    assert [(u["codigo"], u["origen"], u["activa"]) for u in r.json()] == [
        ("A3", "LIDER", True), ("B9", "PAREJA", False)]


def test_another_leaders_conteo_hides_its_locations():
    conteo = _conteo(lider_id=OTRO_LIDER_ID)

    r, _ = _llamar("LIDER_INVENTARIOS", "GET", "/ubicaciones", conteo)

    assert r.status_code == 404


@pytest.mark.parametrize("rol", ["ADMIN", "LIDER_INVENTARIOS"])
def test_the_leader_creates_a_location_ahead(rol):
    conteo = _conteo("PROGRAMADO")
    nueva = uuid.uuid4()

    r, db = _llamar(
        rol, "POST", "/ubicaciones", conteo, [[], [], [nueva]],
        json={"codigo": " ubi-a3 ", "nombre": " Estante  A3 "})

    assert r.status_code == 201, r.text
    cuerpo = r.json()
    assert (cuerpo["id"], cuerpo["codigo"], cuerpo["nombre"]) == (
        str(nueva), "A3", "Estante A3")
    assert (cuerpo["origen"], cuerpo["activa"]) == ("LIDER", True)
    assert len([s for s in db.executed_statements
                if isinstance(s, Insert)]) == 1
    assert db.committed


def test_a_repeated_location_code_is_a_409():
    conteo = _conteo()

    r, db = _llamar(
        "ADMIN", "POST", "/ubicaciones", conteo, [[_ubicacion(conteo)]],
        json={"codigo": "a3", "nombre": "Otra"})

    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "UBICACION_DUPLICADA"
    assert not db.committed


def test_a_location_label_that_is_a_referencia_code_is_a_422():
    conteo = _conteo()

    r, _ = _llamar(
        "ADMIN", "POST", "/ubicaciones", conteo, [[], [uuid.uuid4()]],
        json={"codigo": "A3", "nombre": "Estante"})

    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "UBICACION_CHOCA_REFERENCIA"


def test_the_leader_renames_and_deactivates_a_location():
    conteo = _conteo()
    ubicacion = _ubicacion(conteo, origen="PAREJA")

    r, db = _llamar(
        "LIDER_INVENTARIOS", "PATCH", f"/ubicaciones/{ubicacion.id}",
        conteo, [[ubicacion]],
        json={"nombre": "Vitrina  1", "activa": False})

    assert r.status_code == 200, r.text
    assert (ubicacion.nombre, ubicacion.activa) == ("Vitrina 1", False)
    assert r.json()["codigo"] == "A3"
    assert db.committed


def test_a_location_of_another_store_is_not_found():
    conteo = _conteo()

    r, db = _llamar(
        "ADMIN", "PATCH", f"/ubicaciones/{uuid.uuid4()}", conteo, [[]],
        json={"activa": False})

    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "UBICACION_NO_ENCONTRADA"
    assert "sucursal_id" in str(db.executed_statements[-1])


@pytest.mark.parametrize("cuerpo", [
    {}, {"nombre": "  "}, {"nombre": "x" * 61}])
def test_an_empty_or_bad_edit_is_a_422(cuerpo):
    conteo = _conteo()

    r, _ = _llamar(
        "ADMIN", "PATCH", f"/ubicaciones/{uuid.uuid4()}", conteo,
        json=cuerpo)

    assert r.status_code == 422


@pytest.mark.parametrize("metodo, ruta", [
    ("POST", "/ubicaciones"), ("PATCH", f"/ubicaciones/{uuid.uuid4()}")])
def test_gerencia_cannot_write_locations(metodo, ruta):
    conteo = _conteo()

    r, _ = _llamar(
        "GERENCIA", metodo, ruta, conteo,
        json={"codigo": "A3", "nombre": "A3"})

    assert r.status_code == 403


@pytest.mark.parametrize("estado", ["CERRADO", "ANULADO"])
def test_a_finished_conteo_cannot_change_locations(estado):
    conteo = _conteo(estado)

    r, _ = _llamar(
        "ADMIN", "POST", "/ubicaciones", conteo,
        json={"codigo": "A3", "nombre": "A3"})

    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "ESTADO_INVALIDO"


def test_the_leader_id_is_the_creator():
    conteo = _conteo()

    r, db = _llamar(
        "LIDER_INVENTARIOS", "POST", "/ubicaciones", conteo,
        [[], [], [uuid.uuid4()]], json={"codigo": "C1", "nombre": "C1"})

    assert r.status_code == 201, r.text
    insercion = [s for s in db.executed_statements
                 if isinstance(s, Insert)][0]
    assert insercion.compile().params["created_by"] == LIDER_ID
