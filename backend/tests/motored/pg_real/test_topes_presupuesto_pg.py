"""
Fase 4 "Pantallas del pedido" (sdd/motored-pedidos-ui, B5a, ADR-6, F4-7):
el tope de presupuesto contra un Postgres real (opt-in).

Las rutas reales (la app completa, httpx sobre ASGI) con sesiones reales:
lo que el doble `FakeAsyncSession` no puede probar.

- Un tope `null` ("sin tope") entra a la columna JSONB NOT NULL como JSON
  `null`, no como NULL de SQL, y se lee de vuelta como "sin tope".
- Una versión nueva sólo para la tienda que cambia; la más nueva gana.
- Todo o nada: una entrada inválida no deja ni la primera escrita.
- El interruptor por `POST /parametros` y el lector `obtener_vigentes_motor`
  ven lo mismo que la API.

Siembra: la de `test_envio_pg.py` (un usuario y dos tiendas activas).
"""
import datetime
import uuid
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import delete, func, select, text

from app.config import settings
from app.main import app
from app.motored.deps import get_current_motored_user, get_motored_db
from app.motored.models.parametro_metodologia import ParametroMetodologia
from app.motored.services import parametros, parametros_claves as pc
from app.motored.services.auth import MotoredUser
from app.motored.services.reloj import hoy_bogota
from tests.motored.pg_real.test_envio_pg import (  # noqa: F401 (fixture)
    URL,
    escenario,
)

pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

RUTA = "/api/motored/parametros/topes-presupuesto"
MODO = pc.CLAVE_MODO_TOPE
TOPE = pc.CLAVE_TOPE_PEDIDO
D = Decimal


@pytest.fixture
async def limpio(escenario):
    """Borra lo que escribieron los tests antes de que el escenario borre al
    usuario y las tiendas (`created_by` y `sucursal_id` son FK)."""
    yield escenario
    async with escenario.maker() as db:
        await db.execute(delete(ParametroMetodologia).where(
            ParametroMetodologia.created_by == escenario.usuario_id))
        await db.commit()


def _cliente(esc, monkeypatch, rol):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "topes-pg")

    async def sesion():
        async with esc.maker() as db:
            yield db

    async def usuario():
        return MotoredUser(user_id=str(esc.usuario_id), role=rol)

    app.dependency_overrides[get_motored_db] = sesion
    app.dependency_overrides[get_current_motored_user] = usuario
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://motored")


@pytest.fixture
async def admin(limpio, monkeypatch):
    async with _cliente(limpio, monkeypatch, "ADMIN") as http:
        yield http
    app.dependency_overrides.clear()


@pytest.fixture
async def compras(limpio, monkeypatch):
    async with _cliente(limpio, monkeypatch, "COMPRAS") as http:
        yield http
    app.dependency_overrides.clear()


def _por_id(cuerpo):
    return {t["sucursal_id"]: t for t in cuerpo["topes"]}


async def _filas(esc, clave=TOPE):
    async with esc.maker() as db:
        resultado = await db.execute(
            select(ParametroMetodologia)
            .where(ParametroMetodologia.clave == clave,
                   ParametroMetodologia.created_by == esc.usuario_id)
            .order_by(ParametroMetodologia.created_at))
        return resultado.scalars().all()


def _cuerpo(*topes):
    return {"topes": [
        {"sucursal_id": str(sid), "valor": valor} for sid, valor in topes]}


# --- Lectura ----------------------------------------------------------------


async def test_a_fresh_database_reads_the_switch_off_and_no_caps(
        admin, limpio):
    respuesta = await admin.get(RUTA)

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["modo_activo"] is False
    tiendas = _por_id(cuerpo)
    assert tiendas[str(limpio.a)]["nombre"] == limpio.nombre_a
    assert tiendas[str(limpio.a)]["valor"] is None
    assert tiendas[str(limpio.b)]["vigente_desde"] is None


async def test_compras_can_read_the_caps_but_not_write_them(
        compras, limpio):
    lectura = await compras.get(RUTA)
    escritura = await compras.post(RUTA, json=_cuerpo((limpio.a, 10)))

    assert lectura.status_code == 200
    assert escritura.status_code == 403
    assert await _filas(limpio) == []


# --- Escritura --------------------------------------------------------------


async def test_a_cap_is_written_once_and_read_back(admin, limpio):
    respuesta = await admin.post(
        RUTA, json=_cuerpo((limpio.a, "80000000.50"), (limpio.b, 12)))

    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json() == {
        "actualizados": [str(limpio.a), str(limpio.b)], "sin_cambios": []}
    lectura = _por_id((await admin.get(RUTA)).json())
    assert D(lectura[str(limpio.a)]["valor"]) == D("80000000.50")
    assert D(lectura[str(limpio.b)]["valor"]) == D("12")
    assert lectura[str(limpio.a)]["vigente_desde"] == (
        hoy_bogota().isoformat())
    filas = await _filas(limpio)
    assert {f.sucursal_id: f.valor for f in filas} == {
        limpio.a: "80000000.50", limpio.b: "12"}
    assert {f.created_by for f in filas} == {limpio.usuario_id}


async def test_the_same_value_again_writes_no_new_version(admin, limpio):
    await admin.post(RUTA, json=_cuerpo((limpio.a, 50)))

    respuesta = await admin.post(
        RUTA, json=_cuerpo((limpio.a, "50.00"), (limpio.b, 7)))

    assert respuesta.json() == {
        "actualizados": [str(limpio.b)], "sin_cambios": [str(limpio.a)]}
    assert len(await _filas(limpio)) == 2


async def test_a_changed_cap_adds_a_version_and_the_newest_wins(
        admin, limpio):
    await admin.post(RUTA, json=_cuerpo((limpio.a, 50)))

    await admin.post(RUTA, json=_cuerpo((limpio.a, 75)))

    lectura = _por_id((await admin.get(RUTA)).json())
    assert D(lectura[str(limpio.a)]["valor"]) == D("75")
    assert len(await _filas(limpio)) == 2


async def test_a_null_cap_is_stored_as_json_null_and_reads_as_no_cap(
        admin, limpio):
    await admin.post(RUTA, json=_cuerpo((limpio.a, 50)))

    respuesta = await admin.post(RUTA, json=_cuerpo((limpio.a, None)))

    assert respuesta.json()["actualizados"] == [str(limpio.a)]
    lectura = _por_id((await admin.get(RUTA)).json())
    assert lectura[str(limpio.a)]["valor"] is None
    async with limpio.maker() as db:
        tipos = (await db.execute(
            text("SELECT jsonb_typeof(valor) FROM parametro_metodologia "
                 "WHERE clave = :c AND sucursal_id = :s "
                 "ORDER BY created_at DESC"),
            {"c": TOPE, "s": limpio.a})).scalars().all()
    assert tipos == ["null", "string"]


async def test_removing_a_cap_that_was_never_set_writes_nothing(
        admin, limpio):
    respuesta = await admin.post(RUTA, json=_cuerpo((limpio.a, None)))

    assert respuesta.json()["sin_cambios"] == [str(limpio.a)]
    assert await _filas(limpio) == []


async def test_one_invalid_entry_leaves_the_valid_one_unwritten(
        admin, limpio):
    respuesta = await admin.post(
        RUTA, json=_cuerpo((limpio.a, 10), (limpio.b, -3)))

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "E-PARAM-002"
    assert await _filas(limpio) == []


async def test_an_unknown_sucursal_writes_nothing_even_for_the_valid_one(
        admin, limpio):
    respuesta = await admin.post(
        RUTA, json=_cuerpo((limpio.a, 10), (uuid.uuid4(), 10)))

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "E-PARAM-002"
    assert await _filas(limpio) == []


# --- El interruptor y el lector del motor -----------------------------------


async def test_the_switch_written_with_the_generic_endpoint_reads_on(
        admin, limpio):
    respuesta = await admin.post("/api/motored/parametros", json={
        "clave": MODO, "valor": True, "vigente_desde": "2026-09-01"})

    assert respuesta.status_code == 201, respuesta.text
    cuerpo = (await admin.get(RUTA)).json()
    assert cuerpo["modo_activo"] is True
    assert cuerpo["modo_vigente_desde"] == "2026-09-01"


async def test_a_global_cap_through_the_generic_endpoint_is_e_param_004(
        admin, limpio):
    respuesta = await admin.post("/api/motored/parametros", json={
        "clave": TOPE, "valor": "100", "vigente_desde": "2026-09-01"})

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"]["code"] == "E-PARAM-004"
    assert await _filas(limpio) == []


async def test_the_engine_reader_sees_the_caps_per_tienda(admin, limpio):
    await admin.post(RUTA, json=_cuerpo((limpio.a, "90.5")))

    async with limpio.maker() as db:
        vigentes = await parametros.obtener_vigentes_motor(
            db, [MODO, TOPE], hoy_bogota())

    propio = vigentes.resolver(TOPE, limpio.a)
    ajeno = vigentes.resolver(TOPE, limpio.b)
    assert propio.valor == "90.5"
    assert propio.fuente == parametros.FUENTE_SUCURSAL
    assert ajeno.valor is None and ajeno.fuente == parametros.FUENTE_DEFAULT


async def test_the_budget_keys_stay_out_of_the_engine_read(admin, limpio):
    await admin.post(RUTA, json=_cuerpo((limpio.a, 10)))
    async with limpio.maker() as db:
        antes = await db.scalar(
            select(func.count()).select_from(ParametroMetodologia))
        vigentes = await parametros.obtener_vigentes_motor(
            db, pc.claves_motor(), datetime.date.today())

    claves = {clave for clave, _ in vigentes.filas}
    assert TOPE not in claves and MODO not in claves
    assert antes >= 1
