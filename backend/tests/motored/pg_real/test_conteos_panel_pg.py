"""
Inventory counts, the leader's live panel against a real Postgres
(opt-in, `MOTORED_TEST_PG_URL`, database migrated to head;
odd/motored-conteos-inventario, WU12b; design ADR-8, §6.1, §9.3).

Same savepoint harness and scene as `test_conteos_reconteos_pg.py`:
snapshot A=10, B=10, D=3, E=5 (C is outside it) plus F=0 added here.
Round 1 by pair UNO: A = 5 + 3 (a voided 4), B = 1, C = 2, D = 3 and
one unknown code. Proves the progress numbers (voided readings, round 2
and a surplus outside the snapshot never count, a zero snapshot line is
outside the universe), the per-pair counts, the summary matching the
differences list, and the version moving on a reading, a void, an
assignment and a disconnect while staying put otherwise.
"""
import uuid
from decimal import Decimal

import pytest

from app.motored.models.conteo_snapshot_linea import ConteoSnapshotLinea
from app.motored.models.referencia import Referencia
from tests.motored.pg_real import test_conteos_reconteos_pg as base
from tests.motored.pg_real.test_conteos_api_pg import (  # noqa: F401
    BASE, llamar, pytestmark,
)

fabrica = base.fabrica
_app_lista = base._app_lista
abierto = base.abierto
escena = base.escena
D = Decimal


@pytest.fixture
async def con_cero(escena, fabrica):
    """The scene plus F: a snapshot line with existencia 0."""
    async with fabrica() as db:
        referencia = Referencia(
            id=uuid.uuid4(), codigo=f"F-{uuid.uuid4().hex[:8].upper()}",
            nombre="Repuesto F", proveedor_id=escena.proveedor.id,
            unidad_empaque=1)
        db.add(referencia)
        await db.flush()
        db.add(ConteoSnapshotLinea(
            id=uuid.uuid4(), conteo_id=escena.conteo.id,
            referencia_id=referencia.id, existencia=D("0"),
            costo_unitario=D("1000"), costo_fuente="BODEGA"))
        await db.commit()
    return escena


async def _panel(mundo, version=None):
    ruta = "/panel" if version is None else f"/panel?version={version}"
    r = await base._lider(mundo, "GET", ruta)
    assert r.status_code == 200, r.text
    return r.json()


def _pareja(cuerpo, sesion_id):
    return next(
        p for p in cuerpo["parejas"] if p["sesion_id"] == str(sesion_id))


# --- progress and pairs ------------------------------------------------------


async def test_progress_counts_the_universe_read_in_round_one(con_cero):
    uno = await base._ronda_uno(con_cero)

    cuerpo = await _panel(con_cero)

    assert cuerpo["sin_cambios"] is False
    assert cuerpo["estado"] == "EN_CONTEO"
    progreso = cuerpo["progreso"]
    # Universe A, B, D, E (F is 0, C is outside); E was never read.
    assert (progreso["refs_universo"], progreso["refs_contadas"]) == (4, 3)
    # A 5, A 3, B, C, D and the unknown code: the voided 4 is out.
    assert progreso["lecturas_total"] == 6
    assert progreso["ultima_lectura_en"] is not None
    pareja = _pareja(cuerpo, uno.id)
    assert pareja["lecturas"] == 6 and pareja["estado"] == "CONECTADA"
    assert pareja["ubicacion_actual"]["nombre"] == "Estante B1"
    assert pareja["etiqueta"].startswith("Pareja 1")
    assert pareja["ultima_lectura_en"] is not None


async def test_partial_accuracy_and_the_summary(con_cero):
    await base._ronda_uno(con_cero)

    cuerpo = await _panel(con_cero)
    lista = await base._diferencias(con_cero)

    exactitud = cuerpo["exactitud_parcial"]
    # Counted: A, B, C, D, unknown; only D matches the system.
    assert (exactitud["refs_evaluadas"], exactitud["refs_exactas"]) == (
        5, 1)
    assert exactitud["exactitud_pct"] == "20.00"
    # A -2 x 20000, B -9 x 50000; C and the unknown code have no cost.
    assert exactitud["valor_diferencia_neta"] == "-490000.00"
    assert exactitud["valor_diferencia_abs"] == "490000.00"
    assert cuerpo["diferencias_resumen"] == {
        "criticas": lista["criticas"], "en_reconteo": lista["en_reconteo"],
        "total": lista["total"]}


async def test_nothing_counted_yet_has_no_partial_accuracy(con_cero):
    cuerpo = await _panel(con_cero)

    assert cuerpo["exactitud_parcial"] is None
    assert cuerpo["progreso"] == {
        "refs_universo": 4, "refs_contadas": 0, "lecturas_total": 0,
        "ultima_lectura_en": None}
    assert cuerpo["parejas"] == []


async def test_round_two_readings_are_not_progress(con_cero, fabrica):
    await base._ronda_uno(con_cero)
    await base._terminar_ronda(con_cero)
    rec = await base._reconteos(fabrica, con_cero)
    e = rec[con_cero.codigos["E"]]
    tres = await base._unirse(con_cero, base.TRES)
    r = await base._asignar(con_cero, e, tres)
    assert r.status_code == 200, r.text
    await base._ubicar(con_cero, tres, "UBI-A3")
    await base._leer(con_cero, tres, base._item(
        con_cero.codigos["E"], "5", reconteo_id=e.id))

    cuerpo = await _panel(con_cero)

    assert cuerpo["progreso"]["refs_contadas"] == 3
    assert cuerpo["progreso"]["lecturas_total"] == 7
    assert _pareja(cuerpo, tres.id)["lecturas"] == 1
    assert cuerpo["diferencias_resumen"]["en_reconteo"] == 4


# --- the version (ADR-8) -----------------------------------------------------


async def _sin_cambios(mundo, version):
    cuerpo = await _panel(mundo, version)
    assert cuerpo == {"version": version, "sin_cambios": True}


async def _cambio(mundo, version):
    cuerpo = await _panel(mundo, version)
    assert cuerpo["sin_cambios"] is False
    assert cuerpo["version"] != version
    return cuerpo["version"]


async def test_the_version_moves_on_readings_and_voids(con_cero):
    uno = await base._unirse(con_cero, base.UNO)
    await base._ubicar(con_cero, uno, "UBI-A3")
    version = (await _panel(con_cero))["version"]
    await _sin_cambios(con_cero, version)

    lectura = base._item(con_cero.codigos["A"], "2")
    await base._leer(con_cero, uno, lectura)
    version = await _cambio(con_cero, version)
    await _sin_cambios(con_cero, version)

    r = await base._pedir(
        con_cero, uno, "POST", f"/lecturas/{lectura['id']}/anular")
    assert r.status_code == 200, r.text
    await _cambio(con_cero, version)


async def test_the_version_moves_on_assignment_and_disconnect(
        con_cero, fabrica):
    await base._ronda_uno(con_cero)
    await base._terminar_ronda(con_cero)
    tres = await base._unirse(con_cero, base.TRES)
    b = (await base._reconteos(fabrica, con_cero))[con_cero.codigos["B"]]
    version = (await _panel(con_cero))["version"]
    await _sin_cambios(con_cero, version)

    r = await base._asignar(con_cero, b, tres)
    assert r.status_code == 200, r.text
    version = await _cambio(con_cero, version)
    await _sin_cambios(con_cero, version)

    r = await base._lider(
        con_cero, "POST", f"/sesiones/{tres.id}/desconectar")
    assert r.status_code == 200, r.text
    version = await _cambio(con_cero, version)
    assert _pareja(await _panel(con_cero), tres.id)["estado"] == (
        "DESCONECTADA")


async def test_another_leader_gets_a_404(con_cero):
    r = await llamar(
        "GET", f"{BASE}/{con_cero.conteo.id}/panel",
        ("LIDER_INVENTARIOS", uuid.uuid4()))

    assert r.status_code == 404, r.text


# --- the list ----------------------------------------------------------------


async def test_the_list_carries_the_progress_of_open_conteos(con_cero):
    await base._ronda_uno(con_cero)

    r = await base.llamar("GET", BASE, con_cero.lider_rol)

    assert r.status_code == 200, r.text
    item = next(
        c for c in r.json() if c["id"] == str(con_cero.conteo.id))
    assert item["progreso"] == {"refs_universo": 4, "refs_contadas": 3}
