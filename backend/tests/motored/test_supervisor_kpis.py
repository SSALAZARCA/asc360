"""R7b: the loop that rebuilds the KPI summaries (pure tick logic with an injected clock and fake sessions)."""
import asyncio
import datetime
from datetime import timezone

import pytest

from app.config import settings
from app.motored.services import kpi_resumen as k
from app.motored.services.trabajos import supervisor_kpis as sup

UTC = timezone.utc


def _en_bogota(hora, minuto=0, dia=10):
    """A UTC instant that is `hora:minuto` in Bogota (UTC-5) on the given day of October 2026."""
    return datetime.datetime(2026, 10, dia, hora, minuto, tzinfo=timezone(datetime.timedelta(hours=-5))).astimezone(UTC)


def _estado(**cambios):
    base = dict(sucio=False, reconstruyendo=False, actualizado_en=None,
                ultima_reconstruccion_total=_en_bogota(2, dia=9), version=1)
    return k.Estado(**{**base, **cambios})


# --- decidir --------------------------------------------------------------------------------


def test_a_missing_state_row_or_a_never_built_one_builds_for_the_first_time():
    ahora = _en_bogota(14)

    assert sup.decidir(None, ahora) == sup.MOTIVO_PRIMERA
    assert sup.decidir(_estado(ultima_reconstruccion_total=None, sucio=True), ahora) == sup.MOTIVO_PRIMERA


def test_a_dirty_summary_is_rebuilt_at_any_hour():
    assert sup.decidir(_estado(sucio=True), _en_bogota(14)) == sup.MOTIVO_SUCIA


def test_a_clean_recent_summary_is_left_alone():
    ahora = _en_bogota(3)

    assert sup.decidir(_estado(ultima_reconstruccion_total=_en_bogota(2, dia=10)), ahora) is None
    assert sup.decidir(_estado(ultima_reconstruccion_total=_en_bogota(14, dia=9)), ahora) is None  # only 13 h old


def test_an_old_summary_is_rebuilt_only_inside_the_night_window():
    vieja = _estado(ultima_reconstruccion_total=_en_bogota(2, dia=8))

    assert sup.decidir(vieja, _en_bogota(14)) is None
    assert sup.decidir(vieja, _en_bogota(0, 59)) is None
    assert sup.decidir(vieja, _en_bogota(1, 0)) == sup.MOTIVO_NOCTURNA
    assert sup.decidir(vieja, _en_bogota(4, 59)) == sup.MOTIVO_NOCTURNA
    assert sup.decidir(vieja, _en_bogota(5, 0)) is None


def test_the_night_window_uses_bogota_time_not_utc():
    vieja = _estado(ultima_reconstruccion_total=_en_bogota(2, dia=8))
    utc_1am = datetime.datetime(2026, 10, 10, 1, 0, tzinfo=UTC)  # 20:00 in Bogota

    assert sup.decidir(vieja, utc_1am) is None


def test_a_naive_timestamp_from_the_database_is_read_as_utc():
    naive = datetime.datetime(2026, 10, 8, 7, 0)  # 02:00 Bogota two days earlier

    assert sup.decidir(_estado(ultima_reconstruccion_total=naive), _en_bogota(2)) == sup.MOTIVO_NOCTURNA


# --- reconstruir / run_tick -----------------------------------------------------------------


class _Db:
    def __init__(self, eventos):
        self.eventos = eventos

    async def execute(self, sentencia):
        self.eventos.append("execute")

    async def commit(self):
        self.eventos.append("commit")


class _Fabrica:
    def __init__(self, eventos):
        self.eventos = eventos

    def __call__(self):
        return self

    async def __aenter__(self):
        self.eventos.append("abrir")
        return _Db(self.eventos)

    async def __aexit__(self, *args):
        self.eventos.append("cerrar")


@pytest.fixture(autouse=True)
def _limpio():
    sup._no_reintentar_antes = None
    yield
    sup._no_reintentar_antes = None


@pytest.fixture
def servicio(monkeypatch):
    eventos = []
    estado = {"valor": None, "falla": None, "datos": True}

    async def leer(db):
        eventos.append("estado")
        return estado["valor"]

    async def marcar(db, valor):
        eventos.append(("reconstruyendo", valor))

    async def todo(db):
        eventos.append("reconstruir_todo")
        if estado["falla"]:
            raise estado["falla"]

    async def datos(db):
        eventos.append("hay_datos")
        return estado["datos"]

    monkeypatch.setattr(k, "estado", leer)
    monkeypatch.setattr(k, "hay_datos", datos)
    monkeypatch.setattr(k, "marcar_reconstruyendo", marcar)
    monkeypatch.setattr(k, "reconstruir_todo", todo)
    return eventos, estado, _Fabrica(eventos)


def _marcas(eventos):
    return [e for e in eventos if isinstance(e, tuple) or e == "reconstruir_todo"]


async def test_the_first_ever_build_runs_when_there_is_no_state_row(servicio):
    eventos, estado, fabrica = servicio

    assert await sup.run_tick(session_factory=fabrica, ahora=_en_bogota(14)) == sup.MOTIVO_PRIMERA

    assert _marcas(eventos) == [("reconstruyendo", True), "reconstruir_todo", ("reconstruyendo", False)]


async def test_the_first_build_waits_while_there_is_nothing_to_summarize(servicio):
    eventos, estado, fabrica = servicio
    estado["datos"] = False

    assert await sup.run_tick(session_factory=fabrica, ahora=_en_bogota(14)) is None

    assert _marcas(eventos) == []
    estado["datos"] = True
    assert await sup.run_tick(session_factory=fabrica, ahora=_en_bogota(14)) == sup.MOTIVO_PRIMERA


async def test_a_dirty_summary_is_rebuilt_with_the_flag_committed_before_and_cleared_after(servicio):
    eventos, estado, fabrica = servicio
    estado["valor"] = _estado(sucio=True)

    assert await sup.run_tick(session_factory=fabrica, ahora=_en_bogota(14)) == sup.MOTIVO_SUCIA

    primero = eventos.index(("reconstruyendo", True))
    assert eventos[primero + 1] == "commit"  # committed on its own, before the rebuild starts
    assert primero < eventos.index("reconstruir_todo") < eventos.index(("reconstruyendo", False))
    assert "execute" in eventos  # the statement_timeout guard of the rebuild transaction


async def test_a_clean_summary_does_nothing(servicio):
    eventos, estado, fabrica = servicio
    estado["valor"] = _estado()

    assert await sup.run_tick(session_factory=fabrica, ahora=_en_bogota(14)) is None

    assert _marcas(eventos) == []


async def test_the_night_rebuild_runs_for_an_old_summary_inside_the_window(servicio):
    eventos, estado, fabrica = servicio
    estado["valor"] = _estado(ultima_reconstruccion_total=_en_bogota(2, dia=8))

    assert await sup.run_tick(session_factory=fabrica, ahora=_en_bogota(2)) == sup.MOTIVO_NOCTURNA


async def test_a_failed_rebuild_clears_the_flag_and_propagates(servicio):
    eventos, estado, fabrica = servicio
    estado["valor"] = _estado(sucio=True)
    estado["falla"] = RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await sup.run_tick(session_factory=fabrica, ahora=_en_bogota(14))

    assert _marcas(eventos) == [("reconstruyendo", True), "reconstruir_todo", ("reconstruyendo", False)]


async def test_after_a_failure_the_next_ticks_wait_before_trying_again(servicio):
    eventos, estado, fabrica = servicio
    estado["valor"] = _estado(sucio=True)
    estado["falla"] = RuntimeError("boom")
    ahora = _en_bogota(14)
    with pytest.raises(RuntimeError):
        await sup.run_tick(session_factory=fabrica, ahora=ahora)
    eventos.clear()
    estado["falla"] = None

    assert await sup.run_tick(session_factory=fabrica, ahora=ahora + datetime.timedelta(seconds=60)) is None
    assert eventos == []  # not even the state read

    despues = ahora + datetime.timedelta(seconds=sup.ESPERA_TRAS_FALLO_SEGUNDOS)
    assert await sup.run_tick(session_factory=fabrica, ahora=despues) == sup.MOTIVO_SUCIA


async def test_a_failure_to_clear_the_flag_does_not_hide_the_rebuild_error(servicio, monkeypatch):
    eventos, estado, fabrica = servicio
    estado["valor"] = _estado(sucio=True)
    estado["falla"] = RuntimeError("rebuild failed")

    async def marcar(db, valor):
        if valor is False:
            raise ConnectionError("db gone")

    monkeypatch.setattr(k, "marcar_reconstruyendo", marcar)

    with pytest.raises(RuntimeError, match="rebuild failed"):
        await sup.run_tick(session_factory=fabrica, ahora=_en_bogota(14))


# --- loop -----------------------------------------------------------------------------------


async def test_the_loop_sleeps_before_each_tick_and_survives_a_failing_one(monkeypatch):
    pausas, ticks = [], []

    async def tick():
        ticks.append(1)
        if len(ticks) == 1:
            raise RuntimeError("tick failed")

    async def dormir(segundos):
        pausas.append(segundos)
        if len(pausas) == 3:
            raise asyncio.CancelledError

    monkeypatch.setattr(sup, "run_tick", tick)
    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_POLL_SEGUNDOS", 7)

    with pytest.raises(asyncio.CancelledError):
        await sup._run_forever(dormir)

    assert len(ticks) == 2 and pausas == [7, 7, 7]  # the first sleep comes before the first tick


async def test_the_kill_switch_prevents_the_loop_from_starting(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_LOOP_ENABLED", False)
    await sup.detener()  # a done task left by an earlier request would not prove anything

    sup.ensure_started()

    assert sup._task is None


async def test_ensure_started_is_idempotent_and_detener_cancels(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_LOOP_ENABLED", True)

    async def quieto(dormir=None):
        await asyncio.sleep(3600)

    monkeypatch.setattr(sup, "_run_forever", quieto)
    try:
        sup.ensure_started()
        primera = sup._task
        sup.ensure_started()
        assert primera is not None and sup._task is primera
    finally:
        await sup.detener()

    assert sup._task is None and primera.cancelled()


# --- a `reconstruyendo` flag left behind by a dead process ---------------------------------------


class _FabricaVacia:
    def __call__(self):
        return self

    async def __aenter__(self):
        return object()

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def pasos(monkeypatch):
    registro = []
    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_REBUILD_TIMEOUT_SEGUNDOS", 1800)
    monkeypatch.setattr(sup, "_reconstruyendo_desde", None)

    async def limpiar(fabrica, valor):
        registro.append(("flag", valor))

    monkeypatch.setattr(sup, "_poner_reconstruyendo", limpiar)
    return registro


def _con_estado(monkeypatch, estado):
    async def leer(db):
        return estado

    monkeypatch.setattr(k, "estado", leer)


async def test_a_reconstruyendo_flag_that_outlives_the_rebuild_timeout_is_reset(monkeypatch, pasos):
    _con_estado(monkeypatch, _estado(reconstruyendo=True))
    inicio = _en_bogota(14)
    limite = datetime.timedelta(seconds=1800 + sup.MARGEN_RECONSTRUCCION_SEGUNDOS)

    await sup.run_tick(session_factory=_FabricaVacia(), ahora=inicio)
    await sup.run_tick(session_factory=_FabricaVacia(), ahora=inicio + limite)
    assert pasos == []  # still within timeout + margin: a live rebuild may own the flag

    await sup.run_tick(session_factory=_FabricaVacia(), ahora=inicio + limite + datetime.timedelta(seconds=1))
    assert pasos == [("flag", False)]


async def test_a_new_rebuild_is_allowed_once_a_stale_flag_is_reset(monkeypatch, pasos):
    _con_estado(monkeypatch, _estado(reconstruyendo=True, sucio=True))
    hechas = []

    async def reconstruir(fabrica):
        hechas.append("reconstruir")

    monkeypatch.setattr(sup, "reconstruir", reconstruir)
    inicio = _en_bogota(14)
    await sup.run_tick(session_factory=_FabricaVacia(), ahora=inicio)

    tarde = inicio + datetime.timedelta(hours=3)
    assert await sup.run_tick(session_factory=_FabricaVacia(), ahora=tarde) == sup.MOTIVO_SUCIA
    assert pasos == [("flag", False)] and hechas == ["reconstruir", "reconstruir"]


async def test_the_staleness_clock_restarts_when_the_flag_clears(monkeypatch, pasos):
    inicio = _en_bogota(14)
    _con_estado(monkeypatch, _estado(reconstruyendo=True))
    await sup.run_tick(session_factory=_FabricaVacia(), ahora=inicio)
    _con_estado(monkeypatch, _estado(reconstruyendo=False))
    await sup.run_tick(session_factory=_FabricaVacia(), ahora=inicio + datetime.timedelta(minutes=5))

    _con_estado(monkeypatch, _estado(reconstruyendo=True))
    await sup.run_tick(session_factory=_FabricaVacia(), ahora=inicio + datetime.timedelta(hours=3))

    assert pasos == []  # a flag first seen just now is not stale
