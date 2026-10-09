"""
Inventory counts, reconteo -- pair side (odd/motored-conteos-inventario,
WU9; design §5.2, §6.2, §7).

The assigned session sees its reconteo tasks (code, name and the round-1
locations: never a quantity, a cost or a difference), sends round-2
readings with `reconteo_id` through the usual `/lecturas`, and marks a
task done. A reading for a reconteo that is not this session's is
refused, never stored.

Same `FakeAsyncSession` queue convention as `test_publico_conteos_
lecturas.py`: the leading `[]` is the DB probe, then the `(session,
conteo, store)` row of `sesion_de_pareja`, then the service's queries.
"""
import datetime
import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql

from app.motored.models.conteo_reconteo import ConteoReconteo
from app.motored.services.conteos import errores, lecturas, reconteos
from tests.motored.test_publico_conteos_lecturas import (  # noqa: F401
    REF_A, _ahora, _ciego, _inserciones, _item, _listo, _llamar, _pareja,
    _ubicacion,
)

RID = uuid.uuid4()


# --- which round a reading belongs to (pure) ---------------------------------


def _entrada(codigo="ABC-1", reconteo_id=None):
    return lecturas.Entrada(
        id=uuid.uuid4(), codigo_leido=codigo, cantidad=1,
        leida_en=_ahora(), metodo="ESCANER", reconteo_id=reconteo_id)


def test_round_one_readings_only_while_counting():
    uno, dos = _entrada(), _entrada()

    aptas, cerradas = lecturas.por_ronda([uno], "EN_CONTEO", {})
    _, cerradas2 = lecturas.por_ronda([dos], "EN_RECONTEO", {})

    assert (aptas, cerradas) == ([uno], [])
    assert cerradas2 == [(dos.id, "RONDA_CERRADA")]


def test_a_round_two_reading_needs_its_own_assigned_reconteo():
    ajena = _entrada(reconteo_id=uuid.uuid4())
    temprana = _entrada(reconteo_id=RID)

    _, cerradas = lecturas.por_ronda(
        [ajena], "EN_RECONTEO", {RID: ("ABC-1", True)})
    _, cerradas2 = lecturas.por_ronda(
        [temprana], "EN_CONTEO", {RID: ("ABC-1", True)})

    assert cerradas == [(ajena.id, "RECONTEO_NO_ASIGNADO")]
    assert cerradas2 == [(temprana.id, "RECONTEO_NO_ASIGNADO")]


def test_a_round_two_reading_must_be_the_reconteos_code():
    otra = _entrada("ZZZ-9", RID)
    propia = _entrada(" abc-1 ", RID)

    aptas, cerradas = lecturas.por_ronda(
        [otra, propia], "EN_RECONTEO", {RID: ("ABC-1", True)})

    assert aptas == [propia]
    assert cerradas == [(otra.id, "RECONTEO_OTRO_CODIGO")]


def test_an_unknown_code_reconteo_is_stored_without_forcing():
    lectura = _entrada("XQ-1", RID)

    aptas, _ = lecturas.por_ronda(
        [lectura], "EN_RECONTEO", {RID: ("XQ-1", False)})

    assert aptas[0].forzar_desconocido is True


# --- round-2 readings over HTTP ----------------------------------------------


def test_a_round_two_reading_for_someone_elses_reconteo_is_refused():
    pareja = _pareja("EN_RECONTEO", ubicacion=_ubicacion())
    item = _item("ABC-1", reconteo_id=str(RID))

    r, db = _llamar(
        "POST", "/lecturas", [["EN_RECONTEO"], []], pareja,
        json={"lecturas": [item]})

    assert r.status_code == 200, r.text
    assert r.json()["rechazadas"] == [
        {"id": item["id"], "motivo": "RECONTEO_NO_ASIGNADO"}]
    assert r.json()["aceptadas"] == []
    assert not _inserciones(db)
    _ciego(r)


def test_a_round_two_reading_is_stored_with_its_reconteo():
    ubicacion = _ubicacion()
    pareja = _pareja("EN_RECONTEO", ubicacion=ubicacion)
    item = _item("abc-1", reconteo_id=str(RID))
    filas = [["EN_RECONTEO"], [(RID, "ABC-1", REF_A)],
             [(REF_A, "ABC-1", "Pastilla")], [uuid.UUID(item["id"])]]

    r, db = _llamar(
        "POST", "/lecturas", filas, pareja, json={"lecturas": [item]})

    assert r.status_code == 200, r.text
    assert r.json()["aceptadas"] == [item["id"]]
    [insercion] = _inserciones(db)
    params = insercion.compile(dialect=postgresql.dialect()).params
    assert params["ronda_m0"] == 2
    assert params["reconteo_id_m0"] == RID
    assert params["ubicacion_id_m0"] == ubicacion.id
    _ciego(r)


# --- tasks and finishing -----------------------------------------------------


def test_the_pair_sees_its_tasks_blind(monkeypatch):
    tarea = reconteos.Tarea(
        id=RID, codigo="ABC-1", descripcion="Pastilla",
        ubicaciones=["Estante A3", "Bodega 2"], estado="ASIGNADO")
    tareas = AsyncMock(return_value=[tarea])
    monkeypatch.setattr(reconteos, "tareas", tareas)

    r, _ = _llamar("GET", "/reconteos", [])

    assert r.status_code == 200, r.text
    assert r.json() == [{
        "id": str(RID), "codigo": "ABC-1", "descripcion": "Pastilla",
        "ubicaciones": ["Estante A3", "Bodega 2"], "estado": "ASIGNADO"}]
    _ciego(r)


def test_the_pair_finishes_a_task(monkeypatch):
    pareja = _pareja("EN_RECONTEO")
    sesion, conteo = pareja
    hecho = ConteoReconteo(
        id=RID, conteo_id=conteo.id, codigo="ABC-1", estado="TERMINADO",
        origen="UMBRAL", sesion_id=sesion.id,
        terminado_en=datetime.datetime.now(datetime.timezone.utc))
    terminar = AsyncMock(return_value=hecho)
    monkeypatch.setattr(reconteos, "terminar", terminar)

    r, db = _llamar("POST", f"/reconteos/{RID}/terminar", [], pareja)

    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "TERMINADO"
    assert terminar.await_args.args[1:3] == (sesion, RID)
    assert db.committed
    _ciego(r)


def test_finishing_a_task_that_is_not_yours_is_a_404(monkeypatch):
    monkeypatch.setattr(reconteos, "terminar", AsyncMock(
        side_effect=errores.ReconteoNoEncontrado()))

    r, db = _llamar("POST", f"/reconteos/{RID}/terminar", [])

    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "RECONTEO_NO_ENCONTRADO"
    assert not db.committed


@pytest.mark.parametrize("metodo, ruta", [
    ("GET", "/reconteos"), ("POST", f"/reconteos/{RID}/terminar")])
def test_the_reconteo_routes_need_an_active_session(metodo, ruta):
    pareja = _pareja("EN_RECONTEO", estado="DESCONECTADA")

    r, _ = _llamar(metodo, ruta, [], pareja)

    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "SESION_INACTIVA"
