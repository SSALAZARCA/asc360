"""
The KPI summaries' background rebuild and freshness (odd/motored-kpis-resumenes, R7b) against a
real Postgres (opt-in, database migrated to head).

The loop's tick runs its own sessions and commits; here every session is bound to ONE connection
inside an outer transaction (`create_savepoint`), so those commits are savepoint releases and the
test still rolls back. Covers the first build, the dirty rebuild, the `reconstruyendo` flag
(visible while it runs, cleared on failure), the endpoints and the freshness fields of the tabs.
"""
import datetime

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import settings
from app.main import app
from app.motored.deps import get_current_motored_user, get_motored_db
from app.motored.models.kpi_resumen import KpiResumenEstado, KpiVentaMes
from app.motored.services import kpi_resumen as k
from app.motored.services.auth import MotoredUser
from app.motored.services.trabajos import supervisor_kpis as sup
from tests.motored.pg_real.test_venta_detalle_pg import (  # noqa: F401
    SEP, URL, _aplicar, _mundo, _staging, pytestmark,
)

AHORA = datetime.datetime(2026, 10, 10, 19, 0, tzinfo=datetime.timezone.utc)  # 14:00 in Bogota
BASE = "/api/motored/tablero-asesores/kpis"


@pytest.fixture
async def fabrica():
    motor = create_async_engine(URL)
    async with motor.connect() as conexion:
        externa = await conexion.begin()

        def nueva():
            return AsyncSession(bind=conexion, join_transaction_mode="create_savepoint", expire_on_commit=False)

        yield nueva
        await externa.rollback()
    await motor.dispose()


@pytest.fixture(autouse=True)
def _sin_espera():
    sup._no_reintentar_antes = None
    yield
    sup._no_reintentar_antes = None


async def _con_ventas(fabrica):
    async with fabrica() as db:
        (a, _), ref, (c1, *_) = await _mundo(db)
        await _aplicar(db, c1, [_staging(c1, a, ref, 9, 1, "SEP-A1"), _staging(c1, a, ref, 9, 2, "SEP-A2")], *SEP)
        await db.commit()


async def _estado(fabrica):
    async with fabrica() as db:
        return await k.estado(db)


async def _filas(fabrica):
    async with fabrica() as db:
        return (await db.execute(select(func.count()).select_from(KpiVentaMes))).scalar_one()


async def test_the_first_tick_does_nothing_over_an_empty_database(fabrica):
    assert await sup.run_tick(session_factory=fabrica, ahora=AHORA) is None

    assert await _estado(fabrica) is None  # no state row either: nothing was claimed as built


async def test_the_first_tick_builds_everything_and_leaves_clean_flags(fabrica):
    await _con_ventas(fabrica)
    assert await _estado(fabrica) is None

    assert await sup.run_tick(session_factory=fabrica, ahora=AHORA) == sup.MOTIVO_PRIMERA

    estado = await _estado(fabrica)
    assert (estado.sucio, estado.reconstruyendo) == (False, False)
    assert estado.ultima_reconstruccion_total is not None and await _filas(fabrica) > 0
    assert await sup.run_tick(session_factory=fabrica, ahora=AHORA) is None  # clean: nothing to do


async def test_a_dirty_summary_is_rebuilt_by_the_next_tick(fabrica):
    await _con_ventas(fabrica)
    await sup.run_tick(session_factory=fabrica, ahora=AHORA)
    async with fabrica() as db:
        assert await k.marcar_sucio_si_construido(db) is True
        await db.commit()
    assert (await _estado(fabrica)).sucio is True

    assert await sup.run_tick(session_factory=fabrica, ahora=AHORA) == sup.MOTIVO_SUCIA

    assert (await _estado(fabrica)).sucio is False


async def test_the_reconstruyendo_flag_is_committed_before_the_rebuild_and_cleared_after(fabrica, monkeypatch):
    await _con_ventas(fabrica)
    visto = []
    original = k.reconstruir_todo

    async def espiando(db):
        visto.append((await _estado(fabrica)).reconstruyendo)  # what another session sees mid-rebuild
        await original(db)

    monkeypatch.setattr(k, "reconstruir_todo", espiando)

    await sup.run_tick(session_factory=fabrica, ahora=AHORA)

    assert visto == [True] and (await _estado(fabrica)).reconstruyendo is False


async def test_a_failed_rebuild_clears_the_flag_and_leaves_the_summaries_dirty(fabrica, monkeypatch):
    await _con_ventas(fabrica)

    async def falla(db):
        await db.execute(select(1))
        raise RuntimeError("rebuild failed")

    monkeypatch.setattr(k, "reconstruir_todo", falla)

    with pytest.raises(RuntimeError, match="rebuild failed"):
        await sup.run_tick(session_factory=fabrica, ahora=AHORA)

    estado = await _estado(fabrica)
    assert estado.reconstruyendo is False and estado.sucio is True and estado.ultima_reconstruccion_total is None
    assert await _filas(fabrica) == 0


# --- HTTP ---------------------------------------------------------------------------------------


@pytest.fixture
async def http(fabrica, monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "supervisor-kpis-pg")
    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_LOOP_ENABLED", False)
    usuario = {"rol": "ADMIN"}

    async def db():
        async with fabrica() as sesion:
            yield sesion

    async def quien():
        return MotoredUser(user_id="00000000-0000-0000-0000-000000000001", role=usuario["rol"])

    app.dependency_overrides[get_motored_db] = db
    app.dependency_overrides[get_current_motored_user] = quien
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://motored") as cliente:
        cliente.como = lambda rol: usuario.update(rol=rol)
        yield cliente
    app.dependency_overrides.clear()


async def test_the_tabs_say_where_their_data_comes_from(http, fabrica, monkeypatch):
    await _con_ventas(fabrica)
    params = {"meses": "2026-09"}

    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", True)
    antes = (await http.get(f"{BASE}/ventas", params=params)).json()
    assert antes["usando_resumen"] is False and antes["datos_actualizados_en"] is None  # not built yet: live

    await sup.run_tick(session_factory=fabrica, ahora=AHORA)
    for pestana in ("ventas", "tiendas", "asesores"):
        cuerpo = (await http.get(f"{BASE}/{pestana}", params=params)).json()
        assert cuerpo["usando_resumen"] is True, pestana
        assert datetime.datetime.fromisoformat(cuerpo["datos_actualizados_en"]), pestana

    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", False)
    apagado = (await http.get(f"{BASE}/ventas", params=params)).json()
    assert apagado["usando_resumen"] is False and apagado["datos_actualizados_en"] is None


async def test_the_estado_endpoint_follows_the_state_row(http, fabrica, monkeypatch):
    await _con_ventas(fabrica)
    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", True)
    assert (await http.get(f"{BASE}/estado")).json() == {
        "actualizado_en": None, "sucio": True, "reconstruyendo": False,
        "ultima_reconstruccion_total": None, "usando_resumen": False}

    await sup.run_tick(session_factory=fabrica, ahora=AHORA)
    http.como("COMPRAS")
    cuerpo = (await http.get(f"{BASE}/estado")).json()

    assert cuerpo["sucio"] is False and cuerpo["usando_resumen"] is True
    assert cuerpo["reconstruyendo"] is False and cuerpo["ultima_reconstruccion_total"] is not None


async def test_recalcular_marks_dirty_even_when_never_built_and_the_loop_rebuilds(http, fabrica):
    await _con_ventas(fabrica)

    respuesta = await http.post(f"{BASE}/recalcular")

    assert respuesta.status_code == 200 and respuesta.json()["sucio"] is True
    assert await sup.run_tick(session_factory=fabrica, ahora=AHORA) == sup.MOTIVO_PRIMERA
    respuesta = await http.post(f"{BASE}/recalcular")
    assert respuesta.status_code == 200
    assert await sup.run_tick(session_factory=fabrica, ahora=AHORA) == sup.MOTIVO_SUCIA


@pytest.mark.parametrize("rol", ["GERENCIA", "COMPRAS"])
async def test_recalcular_is_denied_to_gerencia_and_compras_and_changes_nothing(http, fabrica, rol):
    http.como(rol)

    respuesta = await http.post(f"{BASE}/recalcular")

    assert respuesta.status_code == 403 and await _estado(fabrica) is None


async def test_recalcular_while_a_rebuild_holds_the_lock_is_a_409_with_the_reason(http, monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_LOCK_TIMEOUT_SEGUNDOS", 1)
    motor = create_async_engine(URL)
    try:
        async with AsyncSession(motor) as reconstruyendo:
            await k._bloquear(reconstruyendo)  # another connection: a rebuild in flight

            respuesta = await http.post(f"{BASE}/recalcular")

            await reconstruyendo.rollback()
    finally:
        await motor.dispose()

    assert respuesta.status_code == 409 and "reconstruyendo" in respuesta.json()["detail"]
