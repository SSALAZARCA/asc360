"""
Inventory counts, reconteo against a real Postgres (opt-in,
`MOTORED_TEST_PG_URL`, database migrated to head;
odd/motored-conteos-inventario, WU9; design §5.1, §5.2, §7, ADR-4).

Same savepoint-mode harness as `test_publico_conteos_pg.py`: each
route's `commit()` is visible to the next request and nothing survives
the test. Proves what a fake session cannot: the one aggregate (missing
readings = 0, a surplus outside the snapshot, voided readings excluded,
sums across locations), the disjoint-cédula rule, the override guard,
round-2 readings only from the assignee, disconnection releasing tasks,
the auto-assign balance and the partial unique of live reconteos.
"""
import datetime
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.motored.models.conteo import Conteo
from app.motored.models.conteo_lectura import ConteoLectura
from app.motored.models.conteo_reconteo import ConteoReconteo
from app.motored.models.conteo_snapshot_linea import ConteoSnapshotLinea
from app.motored.models.referencia import Referencia
from app.motored.models.ubicacion_inventario import UbicacionInventario
from tests.motored.pg_real import test_publico_conteos_pg as publico
from tests.motored.pg_real.test_conteos_api_pg import (  # noqa: F401
    BASE, PUBLICO, llamar, pytestmark,
)

UTC = datetime.timezone.utc
D = Decimal
PROHIBIDOS = ("existencia", "costo", "diferencia", "valor", "sistema")
UNO = ("1001001", "1001002")
TRES = ("3003001", "3003002")
CUATRO = ("4004001", "4004002")

# The shared harness and the running conteo, as fixtures here.
fabrica = publico.fabrica
_app_lista = publico._app_lista
abierto = publico.abierto


# (key, existencia, costo) of the snapshot; None = not in the snapshot.
SNAPSHOT = {
    "A": (D("10"), D("20000")), "B": (D("10"), D("50000")),
    "C": None, "D": (D("3"), D("1000")), "E": (D("5"), D("20000")),
}


@pytest.fixture
async def escena(abierto, fabrica):
    """The running conteo with a second location, five referencias
    (codes sort A < B < ...) and their snapshot lines."""
    sufijo = uuid.uuid4().hex[:8].upper()
    abierto.codigos = {}
    async with fabrica() as db:
        db.add(UbicacionInventario(
            id=uuid.uuid4(), sucursal_id=abierto.conteo.sucursal_id,
            codigo="B1", nombre="Estante B1", origen="LIDER"))
        for clave, datos in SNAPSHOT.items():
            referencia = Referencia(
                id=uuid.uuid4(), codigo=f"{clave}-{sufijo}",
                nombre=f"Repuesto {clave}",
                proveedor_id=abierto.proveedor.id, unidad_empaque=1)
            db.add(referencia)
            await db.flush()
            abierto.codigos[clave] = referencia.codigo
            if datos is not None:
                db.add(ConteoSnapshotLinea(
                    id=uuid.uuid4(), conteo_id=abierto.conteo.id,
                    referencia_id=referencia.id, existencia=datos[0],
                    costo_unitario=datos[1], costo_fuente="BODEGA"))
        await db.commit()
    abierto.desconocido = f"ZZ-{sufijo}"
    abierto.lider_rol = ("LIDER_INVENTARIOS", abierto.lider.id)
    return abierto


# --- helpers -----------------------------------------------------------------


class Pareja:
    def __init__(self, token, sesion_id):
        self.token, self.id = token, sesion_id


async def _unirse(mundo, cedulas) -> Pareja:
    r = await llamar(
        "POST", f"{PUBLICO}/{mundo.conteo.enlace_slug}/unirse",
        json={"codigo": publico.CODIGO, "dispositivo": "ESCRITORIO",
              "integrantes": [
                  {"nombre": "Ana Ruiz", "cedula": cedulas[0]},
                  {"nombre": "Luis Gil", "cedula": cedulas[1]}]})
    assert r.status_code == 201, r.text
    return Pareja(r.json()["sesion_token"], uuid.UUID(r.json()["sesion_id"]))


async def _pedir(mundo, pareja, metodo, ruta, **kwargs):
    return await llamar(
        metodo, f"{PUBLICO}/{mundo.conteo.enlace_slug}{ruta}",
        headers={"Authorization": f"Bearer {pareja.token}"}, **kwargs)


async def _ubicar(mundo, pareja, codigo):
    r = await _pedir(mundo, pareja, "PUT", "/ubicacion",
                     json={"codigo": codigo})
    assert r.status_code == 200, r.text


def _item(codigo, cantidad="1", **extra):
    item = {"id": str(uuid.uuid4()), "codigo_leido": codigo,
            "cantidad": cantidad, "metodo": "MANUAL",
            "leida_en": datetime.datetime.now(UTC).isoformat()}
    item.update({k: str(v) if isinstance(v, uuid.UUID) else v
                 for k, v in extra.items()})
    return item


async def _leer(mundo, pareja, *items):
    r = await _pedir(mundo, pareja, "POST", "/lecturas",
                     json={"lecturas": list(items)})
    assert r.status_code == 200, r.text
    return r.json()


async def _lider(mundo, metodo, ruta, **kwargs):
    return await llamar(
        metodo, f"{BASE}/{mundo.conteo.id}{ruta}", mundo.lider_rol,
        **kwargs)


async def _ronda_uno(mundo) -> Pareja:
    """Pair UNO counts: A = 5 (A3) + 3 (B1) with a voided 4, B = 1,
    C = 2 (not in the snapshot), D = 3, the unknown code = 1. E and the
    rest of B are never read."""
    uno = await _unirse(mundo, UNO)
    cod = mundo.codigos
    await _ubicar(mundo, uno, "UBI-A3")
    anulada = _item(cod["A"], "4")
    await _leer(mundo, uno, _item(cod["A"].lower(), "5"), anulada,
                _item(cod["B"]), _item(cod["C"], "2"), _item(cod["D"], "3"),
                _item(mundo.desconocido, forzar_desconocido=True))
    r = await _pedir(mundo, uno, "POST", f"/lecturas/{anulada['id']}/anular")
    assert r.status_code == 200, r.text
    await _ubicar(mundo, uno, "UBI-B1")
    await _leer(mundo, uno, _item(cod["A"], "3"))
    return uno


async def _terminar_ronda(mundo):
    r = await _lider(mundo, "POST", "/terminar-ronda")
    assert r.status_code == 200, r.text
    return r.json()


async def _reconteos(fabrica, mundo):
    async with fabrica() as db:
        filas = (await db.scalars(select(ConteoReconteo).where(
            ConteoReconteo.conteo_id == mundo.conteo.id))).all()
    return {f.codigo: f for f in filas}


async def _diferencias(mundo, filtro="todas"):
    r = await _lider(mundo, "GET", f"/diferencias?filtro={filtro}")
    assert r.status_code == 200, r.text
    return r.json()


async def _asignar(mundo, reconteo, pareja, **extra):
    return await _lider(
        mundo, "POST", f"/reconteos/{reconteo.id}/asignar",
        json={"sesion_id": str(pareja.id), **extra})


def _ciego(cuerpo):
    texto = str(cuerpo).lower()
    assert not [p for p in PROHIBIDOS if p in texto], cuerpo


# --- end of round 1 and the differences --------------------------------------


async def test_ending_round_one_values_differences_and_picks_reconteos(
        escena, fabrica):
    uno = await _ronda_uno(escena)
    cod = escena.codigos

    fin = await _terminar_ronda(escena)

    assert fin["estado"] == "EN_RECONTEO"
    assert (fin["diferencias"], fin["reconteos_creados"]) == (5, 4)
    rec = await _reconteos(fabrica, escena)
    assert set(rec) == {cod["B"], cod["C"], cod["E"], escena.desconocido}
    assert {r.origen for r in rec.values()} == {"UMBRAL"}
    assert (rec[cod["B"]].diferencia_ronda1,
            rec[cod["B"]].valor_ronda1) == (D("-9"), D("-450000"))
    assert rec[cod["E"]].valor_ronda1 == D("-100000")
    assert rec[cod["C"]].valor_ronda1 is None
    assert rec[escena.desconocido].referencia_id is None
    async with fabrica() as db:
        conteo = await db.get(Conteo, escena.conteo.id)
    assert conteo.ronda_terminada_en is not None
    tarde = await _leer(escena, uno, _item(cod["A"]))
    assert tarde["rechazadas"][0]["motivo"] == "RONDA_CERRADA"


async def test_the_differences_sum_locations_and_skip_voided(escena):
    await _ronda_uno(escena)
    await _terminar_ronda(escena)
    cod = escena.codigos

    todas = await _diferencias(escena)

    items = {i["codigo"]: i for i in todas["items"]}
    assert [i["codigo"] for i in todas["items"]] == [
        cod["B"], cod["E"], cod["A"], cod["C"], escena.desconocido]
    assert cod["D"] not in items
    a = items[cod["A"]]
    assert (a["sistema"], a["contado"], a["diferencia"]) == (
        "10.00", "8.00", "-2.00")
    assert a["ubicaciones"] == ["Estante A3", "Estante B1"]
    assert a["valor"] == "-40000.00" and a["reconteo"] is None
    e = items[cod["E"]]
    assert (e["contado"], e["valor"], e["critico"]) == (
        "0", "-100000.00", False)
    c = items[cod["C"]]
    assert (c["sistema"], c["sin_costo"], c["valor"]) == ("0", True, None)
    assert items[cod["B"]]["reconteo"]["estado"] == "PENDIENTE"
    assert (todas["parcial"], todas["total"], todas["en_reconteo"]) == (
        False, 5, 4)


async def test_the_critical_flag_follows_the_frozen_amount(escena, fabrica):
    async with fabrica() as db:
        conteo = await db.get(Conteo, escena.conteo.id)
        conteo.umbral_critico_pesos = D("450000")
        await db.commit()
    await _ronda_uno(escena)

    criticas = await _diferencias(escena, "criticas")

    assert criticas["parcial"] is True
    assert [i["codigo"] for i in criticas["items"]] == [
        escena.codigos["B"]]


# --- the different pair (ADR-4) ----------------------------------------------


async def test_the_same_people_on_a_new_device_are_not_a_different_pair(
        escena, fabrica):
    await _ronda_uno(escena)
    await _terminar_ronda(escena)
    b = (await _reconteos(fabrica, escena))[escena.codigos["B"]]
    otro_equipo = await _unirse(escena, UNO)
    medio = await _unirse(escena, (UNO[1], "2002002"))
    distinta = await _unirse(escena, TRES)

    for pareja in (otro_equipo, medio):
        r = await _asignar(escena, b, pareja)
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "MISMA_PAREJA"
    r = await _asignar(escena, b, distinta)

    assert r.status_code == 200, r.text
    assert (r.json()["estado"], r.json()["sesion_id"]) == (
        "ASIGNADO", str(distinta.id))
    assert r.json()["misma_pareja_autorizada"] is False


async def test_the_override_needs_a_reason_and_no_eligible_pair(
        escena, fabrica):
    await _ronda_uno(escena)
    await _terminar_ronda(escena)
    rec = await _reconteos(fabrica, escena)
    otro_equipo = await _unirse(escena, UNO)

    sin_motivo = await _asignar(
        escena, rec[escena.codigos["B"]], otro_equipo,
        autorizar_misma_pareja=True)
    con_motivo = await _asignar(
        escena, rec[escena.codigos["B"]], otro_equipo,
        autorizar_misma_pareja=True, motivo="Solo vino una pareja")
    await _unirse(escena, TRES)
    con_otra = await _asignar(
        escena, rec[escena.codigos["C"]], otro_equipo,
        autorizar_misma_pareja=True, motivo="Solo vino una pareja")

    assert sin_motivo.status_code == 422, sin_motivo.text
    assert sin_motivo.json()["detail"]["code"] == "MOTIVO_REQUERIDO"
    assert con_motivo.status_code == 200, con_motivo.text
    assert con_otra.status_code == 409, con_otra.text
    assert con_otra.json()["detail"]["code"] == "HAY_PAREJA_ELEGIBLE"
    guardado = (await _reconteos(fabrica, escena))[escena.codigos["B"]]
    assert guardado.misma_pareja_autorizada is True
    assert guardado.motivo_autorizacion == "Solo vino una pareja"
    assert guardado.asignado_por == escena.lider.id


# --- round 2 -----------------------------------------------------------------


async def test_round_two_readings_come_only_from_the_assignee(
        escena, fabrica):
    await _ronda_uno(escena)
    await _terminar_ronda(escena)
    cod = escena.codigos
    rec = await _reconteos(fabrica, escena)
    b, e = rec[cod["B"]], rec[cod["E"]]
    tres, cuatro = await _unirse(escena, TRES), await _unirse(escena, CUATRO)
    assert (await _asignar(escena, b, tres)).status_code == 200
    assert (await _asignar(escena, e, cuatro)).status_code == 200

    tareas = await _pedir(escena, tres, "GET", "/reconteos")
    assert tareas.json() == [{
        "id": str(b.id), "codigo": cod["B"], "descripcion": "Repuesto B",
        "ubicaciones": ["Estante A3"], "estado": "ASIGNADO"}]
    _ciego(tareas.json())
    await _ubicar(escena, tres, "UBI-B1")
    await _ubicar(escena, cuatro, "UBI-A3")
    propia = await _leer(escena, tres, _item(cod["B"], "4", reconteo_id=b.id))
    otra = await _leer(escena, tres, _item(cod["A"], reconteo_id=b.id))
    ajena = await _leer(escena, cuatro, _item(cod["B"], reconteo_id=b.id))
    ronda1 = await _leer(escena, tres, _item(cod["B"]))

    assert len(propia["aceptadas"]) == 1
    assert otra["rechazadas"][0]["motivo"] == "RECONTEO_OTRO_CODIGO"
    assert ajena["rechazadas"][0]["motivo"] == "RECONTEO_NO_ASIGNADO"
    assert ronda1["rechazadas"][0]["motivo"] == "RONDA_CERRADA"
    async with fabrica() as db:
        fila = await db.get(ConteoLectura, uuid.UUID(propia["aceptadas"][0]))
        b1 = await db.scalar(select(UbicacionInventario.id).where(
            UbicacionInventario.codigo == "B1",
            UbicacionInventario.sucursal_id == escena.conteo.sucursal_id))
    assert (fila.ronda, fila.reconteo_id, fila.ubicacion_id) == (2, b.id, b1)


async def test_a_finished_reconteo_replaces_round_one(escena, fabrica):
    await _ronda_uno(escena)
    await _terminar_ronda(escena)
    cod = escena.codigos
    rec = await _reconteos(fabrica, escena)
    b, e = rec[cod["B"]], rec[cod["E"]]
    tres = await _unirse(escena, TRES)
    await _asignar(escena, b, tres)
    await _asignar(escena, e, tres)
    await _ubicar(escena, tres, "UBI-B1")
    await _leer(escena, tres, _item(cod["B"], "4", reconteo_id=b.id))

    for reconteo in (b, e, b):
        r = await _pedir(
            escena, tres, "POST", f"/reconteos/{reconteo.id}/terminar")
        assert r.status_code == 200, r.text
        assert r.json()["estado"] == "TERMINADO"
        _ciego(r.json())

    items = {i["codigo"]: i for i in (await _diferencias(escena))["items"]}
    assert (items[cod["B"]]["contado_ronda1"], items[cod["B"]]["contado"],
            items[cod["B"]]["diferencia"]) == ("1.00", "4.00", "-6.00")
    assert items[cod["E"]]["contado"] == "0"
    assert items[cod["E"]]["reconteo"]["estado"] == "TERMINADO"


async def test_another_pair_cannot_finish_or_see_a_task(escena, fabrica):
    await _ronda_uno(escena)
    await _terminar_ronda(escena)
    b = (await _reconteos(fabrica, escena))[escena.codigos["B"]]
    tres, cuatro = await _unirse(escena, TRES), await _unirse(escena, CUATRO)
    await _asignar(escena, b, tres)

    r = await _pedir(escena, cuatro, "POST", f"/reconteos/{b.id}/terminar")

    assert r.status_code == 404
    assert (await _pedir(escena, cuatro, "GET", "/reconteos")).json() == []


# --- disconnection -----------------------------------------------------------


async def test_disconnecting_a_pair_sends_its_tasks_back(escena, fabrica):
    await _ronda_uno(escena)
    await _terminar_ronda(escena)
    cod = escena.codigos
    rec = await _reconteos(fabrica, escena)
    tres, cuatro = await _unirse(escena, TRES), await _unirse(escena, CUATRO)
    for clave in ("B", "C"):
        await _asignar(escena, rec[cod[clave]], tres)
    await _asignar(escena, rec[cod["E"]], cuatro)
    await _pedir(escena, tres, "POST", f"/reconteos/{rec[cod['C']].id}"
                 "/terminar")

    cortar = await _lider(
        escena, "POST", f"/sesiones/{tres.id}/desconectar")
    salir = await _pedir(escena, cuatro, "POST", "/salir")

    assert (cortar.status_code, salir.status_code) == (200, 204)
    despues = await _reconteos(fabrica, escena)
    assert (despues[cod["B"]].estado, despues[cod["B"]].sesion_id) == (
        "PENDIENTE", None)
    assert despues[cod["E"]].estado == "PENDIENTE"
    assert despues[cod["E"]].asignado_en is None
    assert despues[cod["C"]].estado == "TERMINADO"


# --- auto-assign -------------------------------------------------------------


async def test_auto_assign_balances_and_reports_the_unassignable(
        escena, fabrica):
    await _ronda_uno(escena)
    await _terminar_ronda(escena)
    cod = escena.codigos

    solo_uno = await _lider(escena, "POST", "/reconteos/auto-asignar")
    tres, cuatro = await _unirse(escena, TRES), await _unirse(escena, CUATRO)
    todos = await _lider(escena, "POST", "/reconteos/auto-asignar")

    assert solo_uno.status_code == 200, solo_uno.text
    assert [r["codigo"] for r in solo_uno.json()["asignados"]] == [cod["E"]]
    assert sorted(r["codigo"] for r in solo_uno.json()["sin_pareja"]) == (
        sorted([cod["B"], cod["C"], escena.desconocido]))
    assert todos.json()["sin_pareja"] == []
    rec = await _reconteos(fabrica, escena)
    cuenta = {tres.id: 0, cuatro.id: 0}
    for codigo in (cod["B"], cod["C"], escena.desconocido):
        cuenta[rec[codigo].sesion_id] += 1
    assert sorted(cuenta.values()) == [1, 2]
    assert {r.estado for r in rec.values()} == {"ASIGNADO"}


# --- one live reconteo per code ----------------------------------------------


async def test_the_partial_unique_allows_one_live_reconteo_per_code(
        escena, fabrica):
    await _ronda_uno(escena)
    await _terminar_ronda(escena)
    cod = escena.codigos
    b = (await _reconteos(fabrica, escena))[cod["B"]]

    with pytest.raises(IntegrityError):
        async with fabrica() as db:
            db.add(ConteoReconteo(
                id=uuid.uuid4(), conteo_id=escena.conteo.id, codigo=b.codigo,
                estado="PENDIENTE", origen="LIDER"))
            await db.commit()
    doble = await _lider(escena, "POST", "/reconteos",
                         json={"codigo": cod["B"].lower()})
    cancelar = await _lider(escena, "POST", f"/reconteos/{b.id}/cancelar")
    nuevo = await _lider(escena, "POST", "/reconteos",
                         json={"codigo": cod["B"]})
    sin_diferencia = await _lider(escena, "POST", "/reconteos",
                                  json={"codigo": cod["D"]})
    inventado = await _lider(escena, "POST", "/reconteos",
                             json={"codigo": "NO-EXISTE-XYZ"})

    assert doble.status_code == 409
    assert doble.json()["detail"]["code"] == "RECONTEO_DUPLICADO"
    assert cancelar.json()["estado"] == "CANCELADO"
    assert nuevo.status_code == 201, nuevo.text
    assert (nuevo.json()["origen"], nuevo.json()["diferencia_ronda1"]) == (
        "LIDER", "-9.00")
    assert sin_diferencia.json()["diferencia_ronda1"] == "0.00"
    assert inventado.json()["detail"]["code"] == "CODIGO_DESCONOCIDO"
    en_reconteo = await _diferencias(escena, "reconteo")
    assert cod["D"] in {i["codigo"] for i in en_reconteo["items"]}
