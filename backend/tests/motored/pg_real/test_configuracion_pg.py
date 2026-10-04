"""
Motored "Configuración" admin page, T1 (odd/motored-configuracion-admin):
the point-in-time read `vigente_en`, the history query and the page read
model against a real Postgres (opt-in).

- `vigente_en` takes the row with the max `vigente_desde` <= the first day
  of the month asked, with scope precedence sucursal > global > default.
- The history lists every scope newest first and joins the author's name.
- The page read model shows scheduled (future) versions apart from the
  effective one, and a sucursal override apart from the global value.

Siembra: la de `test_envio_pg.py` (un usuario y dos tiendas activas).
"""
import datetime

import httpx
import pytest
from sqlalchemy import delete, select

from app.config import settings
from app.main import app
from app.motored.deps import get_current_motored_user, get_motored_db
from app.motored.models.parametro_metodologia import ParametroMetodologia
from app.motored.services import parametros
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
INGRESOS = "dias_ventana_ingresos"
DIAS = "dias_entre_pedidos"
D = datetime.date


@pytest.fixture
async def limpio(escenario):
    """Borra lo que se escribió antes de que el escenario borre al usuario
    y a las tiendas (`created_by` y `sucursal_id` son FK)."""
    yield escenario
    async with escenario.maker() as db:
        await db.execute(delete(ParametroMetodologia).where(
            ParametroMetodologia.clave.in_([INGRESOS, DIAS])))
        await db.commit()


@pytest.fixture
async def admin(limpio, monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "config-pg")

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


async def _sembrar(esc, *filas):
    """Cada fila: (clave, valor, vigente_desde, sucursal_id, autor)."""
    async with esc.maker() as db:
        for clave, valor, desde, sucursal, autor in filas:
            await parametros.registrar_cambio(
                db, clave, valor, desde, autor, sucursal)
        await db.commit()


async def _vigente(esc, clave, fecha, sucursal=None):
    async with esc.maker() as db:
        return await parametros.vigente_en(db, clave, fecha, sucursal)


async def test_vigente_en_returns_the_version_in_force_that_month(limpio):
    await _sembrar(
        limpio,
        (INGRESOS, 50, D(2026, 3, 1), None, None),
        (INGRESOS, 60, D(2026, 6, 1), None, None),
        (INGRESOS, 70, D(2026, 9, 1), None, None))

    por_fecha = {
        fecha: (await _vigente(limpio, INGRESOS, fecha)).valor
        for fecha in (
            D(2026, 2, 28), D(2026, 3, 1), D(2026, 5, 31), D(2026, 6, 1),
            D(2026, 8, 31), D(2026, 9, 30), D(2027, 1, 15))}

    assert por_fecha == {
        D(2026, 2, 28): 45, D(2026, 3, 1): 50, D(2026, 5, 31): 50,
        D(2026, 6, 1): 60, D(2026, 8, 31): 60, D(2026, 9, 30): 70,
        D(2027, 1, 15): 70}


async def test_a_row_starting_mid_month_only_counts_from_the_next_month(
        limpio):
    await _sembrar(limpio, (INGRESOS, 99, D(2026, 10, 15), None, None))

    en_octubre = await _vigente(limpio, INGRESOS, D(2026, 10, 20))
    en_noviembre = await _vigente(limpio, INGRESOS, D(2026, 11, 2))

    assert en_octubre.fuente == parametros.FUENTE_DEFAULT
    assert (en_noviembre.valor, en_noviembre.fuente) == (
        99, parametros.FUENTE_GLOBAL)


async def test_vigente_en_resolves_sucursal_then_global_then_default(
        limpio):
    await _sembrar(
        limpio,
        (DIAS, 40, D(2026, 5, 1), None, None),
        (DIAS, 7, D(2026, 5, 1), limpio.a, None),
        (DIAS, 9, D(2026, 8, 1), limpio.a, None))
    fecha = D(2026, 6, 10)

    de_a = await _vigente(limpio, DIAS, fecha, limpio.a)
    de_b = await _vigente(limpio, DIAS, fecha, limpio.b)
    global_ = await _vigente(limpio, DIAS, fecha)
    antes = await _vigente(limpio, DIAS, D(2026, 4, 30), limpio.a)
    despues = await _vigente(limpio, DIAS, D(2026, 8, 31), limpio.a)

    assert (de_a.valor, de_a.fuente) == (7, parametros.FUENTE_SUCURSAL)
    assert (de_b.valor, de_b.fuente) == (40, parametros.FUENTE_GLOBAL)
    assert global_.valor == 40
    assert (antes.valor, antes.fuente) == (30, parametros.FUENTE_DEFAULT)
    assert despues.valor == 9


async def test_a_tie_on_vigente_desde_takes_the_newest_created(limpio):
    await _sembrar(limpio, (INGRESOS, 50, D(2026, 3, 1), None, None))
    await _sembrar(limpio, (INGRESOS, 55, D(2026, 3, 1), None, None))

    res = await _vigente(limpio, INGRESOS, D(2026, 3, 20))

    assert res.valor == 55


async def test_history_is_newest_first_across_scopes_with_author(
        admin, limpio):
    await _sembrar(
        limpio,
        (DIAS, 30, D(2026, 1, 1), None, limpio.usuario_id),
        (DIAS, 12, D(2026, 3, 1), limpio.a, None),
        (DIAS, 20, D(2026, 6, 1), None, limpio.usuario_id))

    respuesta = await admin.get(f"{RUTA}/{DIAS}/historial")

    assert respuesta.status_code == 200, respuesta.text
    filas = respuesta.json()
    assert [f["valor"] for f in filas] == [20, 12, 30]
    assert [f["vigente_desde"] for f in filas] == [
        "2026-06-01", "2026-03-01", "2026-01-01"]
    assert filas[0]["created_by_nombre"] == "Compras"
    assert filas[1]["created_by_nombre"] is None
    assert filas[1]["sucursal_id"] == str(limpio.a)
    assert filas[0]["created_at"] is not None


async def test_the_page_separates_effective_override_and_scheduled(
        admin, limpio):
    hoy = datetime.date.today()
    inicio = hoy.replace(day=1)
    futuro = (inicio + datetime.timedelta(days=40)).replace(day=1)
    await _sembrar(
        limpio,
        (INGRESOS, 61, D(2026, 1, 1), None, None),
        (INGRESOS, 62, futuro, None, None),
        (DIAS, 8, D(2026, 1, 1), limpio.b, None))

    respuesta = await admin.get(f"{RUTA}/configuracion")

    assert respuesta.status_code == 200, respuesta.text
    por_clave = {
        c["clave"]: c for s in respuesta.json()["secciones"]
        for g in s["grupos"] for c in g["claves"]}
    ingresos, dias = por_clave[INGRESOS], por_clave[DIAS]
    assert ingresos["efectivo_global"]["valor"] == 61
    assert [p["valor"] for p in ingresos["programados"]] == [62]
    assert [(o["sucursal_id"], o["valor"]) for o in dias["por_sucursal"]] \
        == [(str(limpio.b), 8)]
    assert dias["efectivo_global"]["fuente"] == "DEFAULT"


async def test_posting_a_mid_month_date_stores_the_first_day(admin, limpio):
    respuesta = await admin.post(RUTA, json={
        "clave": INGRESOS, "valor": 77, "vigente_desde": "2026-11-20"})

    assert respuesta.status_code == 201, respuesta.text
    async with limpio.maker() as db:
        filas = (await db.execute(select(ParametroMetodologia).where(
            ParametroMetodologia.clave == INGRESOS))).scalars().all()
    assert [f.vigente_desde for f in filas] == [D(2026, 11, 1)]
