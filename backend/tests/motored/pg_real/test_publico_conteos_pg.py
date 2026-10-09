"""
Inventory counts, public pair access against a real Postgres (opt-in,
`MOTORED_TEST_PG_URL`, database migrated to head;
odd/motored-conteos-inventario, WU7; design §8.2, §5.3).

Same savepoint-mode harness as `test_conteos_api_pg.py`: a route's
`commit()` is visible to the next request, so a counter that survives a
401 proves it was committed BEFORE the error.
"""
import datetime
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.motored.models.conteo import Conteo
from app.motored.models.conteo_acceso_intento import ConteoAccesoIntento
from app.motored.models.conteo_lectura import ConteoLectura
from app.motored.models.conteo_sesion import ConteoIntegrante, ConteoSesion
from app.motored.models.ubicacion_inventario import UbicacionInventario
from app.motored.services.conteos import acceso
from tests.motored.pg_real import test_conteos_api_pg as base
from tests.motored.pg_real.test_conteos_api_pg import (  # noqa: F401
    BASE, CEDULAS, PUBLICO, integrantes, llamar, pytestmark,
)
from tests.motored.pg_real.test_conteos_snapshot_pg import HOY, Mundo

CODIGO = "482913"
UTC = datetime.timezone.utc

# The shared harness (savepoint sessions, app settings) as fixtures here.
fabrica = base.fabrica
_app_lista = base._app_lista


@pytest.fixture
async def abierto(fabrica):
    """A running TOTAL conteo with a known code and one location."""
    async with fabrica() as db:
        mundo = await Mundo(db).base()
        sucursal = await mundo.tienda()
        ahora = datetime.datetime.now(UTC)
        conteo = Conteo(
            id=uuid.uuid4(), tipo="TOTAL", estado="EN_CONTEO",
            origen="MANUAL", sucursal_id=sucursal.id,
            lider_id=mundo.lider.id, fecha_programada=HOY,
            snapshot_tomado_en=ahora, iniciado_en=ahora,
            umbral_reconteo_pesos=Decimal("100000"),
            umbral_critico_pesos=Decimal("500000"),
            enlace_slug=acceso.nuevo_slug())
        conteo.codigo_hash = acceso.hash_codigo(conteo.id, CODIGO)
        ubicacion = UbicacionInventario(
            id=uuid.uuid4(), sucursal_id=sucursal.id, codigo="A3",
            nombre="Estante A3", origen="LIDER")
        db.add_all([conteo, ubicacion])
        await db.commit()
    mundo.conteo, mundo.ubicacion = conteo, ubicacion
    return mundo


async def _unirse(mundo, codigo=CODIGO):
    return await llamar(
        "POST", f"{PUBLICO}/{mundo.conteo.enlace_slug}/unirse",
        json={"codigo": codigo, "dispositivo": "MOVIL",
              "integrantes": integrantes()})


async def _con_token(mundo, metodo, ruta, token):
    return await llamar(
        metodo, f"{PUBLICO}/{mundo.conteo.enlace_slug}{ruta}",
        headers={"Authorization": f"Bearer {token}"})


async def _conteo(fabrica, mundo):
    async with fabrica() as db:
        return await db.get(Conteo, mundo.conteo.id)


async def test_the_attempt_counters_survive_the_401(abierto, fabrica):
    r = await _unirse(abierto, codigo="000000")

    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "ACCESO_INVALIDO"
    async with fabrica() as db:
        intentos = (await db.scalars(select(ConteoAccesoIntento).where(
            ConteoAccesoIntento.conteo_id == abierto.conteo.id))).all()
    assert [i.fallidos for i in intentos] == [1]
    assert len(intentos[0].cliente) == 64
    assert (await _conteo(fabrica, abierto)).acceso_fallidos_hora == 1


async def test_five_failures_lock_even_the_right_code(abierto):
    for _ in range(5):
        assert (await _unirse(abierto, codigo="000000")).status_code == 401

    r = await _unirse(abierto)

    assert r.status_code == 429, r.text


async def test_the_30th_failure_rotates_the_code_but_keeps_pairs(
        abierto, fabrica):
    token = (await _unirse(abierto)).json()["sesion_token"]
    async with fabrica() as db:
        conteo = await db.get(Conteo, abierto.conteo.id)
        conteo.acceso_fallidos_hora = 29
        conteo.acceso_ventana_inicio = datetime.datetime.now(UTC)
        await db.commit()

    assert (await _unirse(abierto, codigo="000000")).status_code == 401

    conteo = await _conteo(fabrica, abierto)
    assert not acceso.verificar_codigo(conteo.id, CODIGO, conteo.codigo_hash)
    assert conteo.acceso_fallidos_hora == 0
    r = await _con_token(abierto, "GET", "/sesion", token)
    assert r.status_code == 200, r.text
    assert (await _unirse(abierto)).status_code == 401


async def test_a_join_creates_the_session_and_its_members(abierto, fabrica):
    r = await _unirse(abierto)

    assert r.status_code == 201, r.text
    assert r.headers["cache-control"] == "no-store"
    for cedula in CEDULAS:
        assert cedula not in r.text
    sesion_id = uuid.UUID(r.json()["sesion_id"])
    async with fabrica() as db:
        sesion = await db.get(ConteoSesion, sesion_id)
        personas = (await db.scalars(select(ConteoIntegrante).where(
            ConteoIntegrante.sesion_id == sesion_id).order_by(
            ConteoIntegrante.orden))).all()
    assert (sesion.estado, sesion.dispositivo) == ("CONECTADA", "MOVIL")
    assert sesion.token_hash != r.json()["sesion_token"]
    assert [(p.nombre, p.cedula) for p in personas] == [
        ("Ana Ruiz", CEDULAS[0]), ("Luis Gil", CEDULAS[1])]
    quien = await _con_token(
        abierto, "GET", "/sesion", r.json()["sesion_token"])
    assert quien.json()["etiqueta"] == "Pareja 1 · Ana R. y Luis G."


async def test_disconnecting_keeps_the_readings(abierto, fabrica):
    r = await _unirse(abierto)
    token, sesion_id = r.json()["sesion_token"], r.json()["sesion_id"]
    lectura_id = uuid.uuid4()
    async with fabrica() as db:
        db.add(ConteoLectura(
            id=lectura_id, conteo_id=abierto.conteo.id,
            sesion_id=uuid.UUID(sesion_id),
            ubicacion_id=abierto.ubicacion.id, codigo_leido="ABC-1",
            cantidad=Decimal("2"), ronda=1, metodo="MANUAL",
            leida_en=datetime.datetime.now(UTC)))
        await db.commit()

    r = await llamar(
        "POST",
        f"{BASE}/{abierto.conteo.id}/sesiones/{sesion_id}/desconectar",
        ("LIDER_INVENTARIOS", abierto.lider.id))

    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "DESCONECTADA"
    assert (await _con_token(abierto, "GET", "/sesion", token)
            ).status_code == 401
    async with fabrica() as db:
        lectura = await db.get(ConteoLectura, lectura_id)
        sesion = await db.get(ConteoSesion, uuid.UUID(sesion_id))
    assert lectura is not None and lectura.cantidad == Decimal("2")
    assert sesion.desconectada_por == abierto.lider.id


async def test_salir_disconnects_by_itself(abierto, fabrica):
    token = (await _unirse(abierto)).json()["sesion_token"]

    r = await _con_token(abierto, "POST", "/salir", token)

    assert r.status_code == 204, r.text
    assert (await _con_token(abierto, "GET", "/sesion", token)
            ).status_code == 401
    async with fabrica() as db:
        estados = (await db.scalars(select(ConteoSesion.estado).where(
            ConteoSesion.conteo_id == abierto.conteo.id))).all()
    assert estados == ["DESCONECTADA"]
