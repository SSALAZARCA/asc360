"""
Motored "Configuración", T6/T7: the Indicadores and Comisiones keys are
written through the API and read back with `vigente_en` against a real
Postgres (opt-in): a commission change applies from its month and a past
month still sees the rules that were in force then.
"""
import datetime

import httpx
import pytest
from sqlalchemy import delete

from app.config import settings
from app.main import app
from app.motored.deps import get_current_motored_user, get_motored_db
from app.motored.models.parametro_metodologia import ParametroMetodologia
from app.motored.services import parametros, parametros_claves as pc
from app.motored.services.auth import MotoredUser
from tests.motored.pg_real.test_envio_pg import (  # noqa: F401 (fixture)
    URL,
    escenario,
)

pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

RUTA = "/api/motored/parametros"
TRAMOS = "comision_tramos"
NITS = "hmcl_nits"
SEMAFORO = "kpi_semaforo_cortes"
CLAVES = [TRAMOS, NITS, SEMAFORO, "grupo_por_cargo"]
D = datetime.date


@pytest.fixture
async def limpio(escenario):
    yield escenario
    async with escenario.maker() as db:
        await db.execute(delete(ParametroMetodologia).where(
            ParametroMetodologia.clave.in_(CLAVES)))
        await db.commit()


@pytest.fixture
async def admin(limpio, monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "config-op-pg")

    async def sesion():
        async with limpio.maker() as db:
            yield db

    async def usuario():
        return MotoredUser(user_id=str(limpio.usuario_id), role="ADMIN")

    app.dependency_overrides[get_motored_db] = sesion
    app.dependency_overrides[get_current_motored_user] = usuario
    async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://motored") as http:
        yield http
    app.dependency_overrides.clear()


async def _vigente(esc, clave, fecha):
    async with esc.maker() as db:
        return await parametros.vigente_en(db, clave, fecha)


def _tramos(tasa_base):
    return [{"nombre": "BASE", "desde_pct": 0, "tasa_pct": tasa_base},
            {"nombre": "PRO", "desde_pct": 95, "tasa_pct": 2}]


async def _guardar(admin, clave, valor, desde):
    return await admin.post(RUTA, json={
        "clave": clave, "valor": valor, "vigente_desde": desde})


async def test_commission_tiers_apply_from_their_month_and_keep_the_past(
        admin, limpio):
    for tasa, desde in ((1.2, "2026-03-15"), (1.4, "2026-08-01")):
        respuesta = await _guardar(admin, TRAMOS, _tramos(tasa), desde)
        assert respuesta.status_code == 201, respuesta.text

    antes = await _vigente(limpio, TRAMOS, D(2026, 2, 28))
    marzo = await _vigente(limpio, TRAMOS, D(2026, 3, 20))
    julio = await _vigente(limpio, TRAMOS, D(2026, 7, 31))
    agosto = await _vigente(limpio, TRAMOS, D(2026, 8, 31))

    assert antes.fuente == parametros.FUENTE_DEFAULT
    assert antes.valor == pc.REGISTRO[TRAMOS].default
    assert marzo.valor[0]["tasa_pct"] == 1.2
    assert julio.valor[0]["tasa_pct"] == 1.2
    assert agosto.valor[0]["tasa_pct"] == 1.4


async def test_invalid_values_are_rejected_and_nothing_is_stored(
        admin, limpio):
    malos = [
        (NITS, ["900", "900"]),
        (SEMAFORO, {"verde_desde": 60, "ambar_desde": 70}),
        (TRAMOS, [{"nombre": "A", "desde_pct": 5, "tasa_pct": 1}]),
    ]
    for clave, valor in malos:
        respuesta = await _guardar(admin, clave, valor, "2026-10-01")
        assert respuesta.status_code == 422, clave
        assert respuesta.json()["detail"]["code"] == "E-PARAM-002"

    assert (await _vigente(limpio, NITS, D(2026, 10, 5))).fuente == (
        parametros.FUENTE_DEFAULT)


async def test_the_page_lists_the_new_keys_in_their_sections(admin, limpio):
    respuesta = await _guardar(admin, SEMAFORO, {
        "verde_desde": 95, "ambar_desde": 75}, "2026-01-01")
    assert respuesta.status_code == 201, respuesta.text

    pagina = await admin.get(f"{RUTA}/configuracion")

    assert pagina.status_code == 200, pagina.text
    secciones = {
        s["seccion"]: {c["clave"]: c for g in s["grupos"]
                       for c in g["claves"]}
        for s in pagina.json()["secciones"]}
    assert {NITS, "grupo_por_cargo", "lineas_comerciales",
            SEMAFORO} <= set(secciones["indicadores"])
    assert {TRAMOS, "comision_base_pago", "cumplimiento_base",
            "comision_cargos_asesor"} <= set(secciones["comisiones"])
    semaforo = secciones["indicadores"][SEMAFORO]
    assert semaforo["efectivo_global"]["valor"] == {
        "verde_desde": 95, "ambar_desde": 75}
    assert semaforo["snapshotted"] is False
    assert (semaforo["minimo"], semaforo["maximo"]) == (0, 200)
