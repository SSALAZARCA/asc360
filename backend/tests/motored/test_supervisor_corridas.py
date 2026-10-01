"""
Motored Pedidos F3 "Motor", S6b (sdd/motored-pedidos-motor, ADR-5,
tasks S6b-1/S6b-3/S6b-8): el loop asyncio PROPIO de las corridas, el runner
y la retención.

El loop se arranca igual que el de F2 (`deps.require_motored_ready`, sin
`lifespan`), pero no comparte con él el claim, el barrido ni el tick: un
tick que falla se registra y el loop sigue, un tick del supervisor de cargas
no espera una corrida, y con la tabla `corrida` ausente (migración sin
aplicar) el loop queda en espera sin tumbar la app.
"""
import asyncio
import datetime
import logging
import uuid

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.config import settings
from app.motored import deps
from app.motored.services.corridas import ejecucion as ej
from app.motored.services.corridas import estados
from app.motored.services.corridas import retencion_corridas as rc
from app.motored.services.trabajos import runner_corridas as rr
from app.motored.services.trabajos import supervisor
from app.motored.services.trabajos import supervisor_corridas as sc
from tests.motored.conftest import (
    INSTANTE_CONGELADO,
    FabricaDeSesion,
    SesionConCommits,
)

ID = uuid.UUID(int=901)
AHORA = INSTANTE_CONGELADO


def _reloj():
    return AHORA


def _sql(sentencia):
    return sentencia.compile(dialect=postgresql.dialect())


def _fabrica():
    return FabricaDeSesion(SesionConCommits())


def _tabla_ausente():
    return ProgrammingError(
        "SELECT corrida.id FROM corrida", {},
        Exception('relation "corrida" does not exist'))


class Dormir:
    """`asyncio.sleep` de juguete: anota y corta el loop tras N esperas."""

    def __init__(self, cortar_en):
        self.esperas = []
        self.cortar_en = cortar_en

    async def __call__(self, segundos):
        self.esperas.append(segundos)
        if len(self.esperas) >= self.cortar_en:
            raise asyncio.CancelledError


# --- Arranque perezoso -------------------------------------------------------


@pytest.fixture
def habilitado(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_CORRIDAS_LOOP_ENABLED", True)


async def test_the_loop_starts_once_and_stays_alive(habilitado):
    sc.ensure_started()
    primera = sc._task
    sc.ensure_started()

    assert primera is not None and not primera.done()
    assert sc._task is primera


async def test_a_disabled_module_never_creates_a_task(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", False)
    monkeypatch.setattr(settings, "MOTORED_CORRIDAS_LOOP_ENABLED", True)

    sc.ensure_started()

    assert sc._task is None


async def test_the_loop_flag_alone_switches_the_corrida_loop_off(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_CORRIDAS_LOOP_ENABLED", False)

    sc.ensure_started()

    assert sc._task is None


def test_the_loop_flag_defaults_to_on_and_is_a_real_setting():
    campos = type(settings).model_fields
    assert campos["MOTORED_CORRIDAS_LOOP_ENABLED"].default is True


async def test_the_corrida_loop_never_starts_the_carga_supervisor(habilitado):
    sc.ensure_started()

    assert supervisor._task is None


async def test_a_failure_starting_the_task_never_reaches_the_request(
        habilitado, monkeypatch, caplog):
    def _explota():
        raise RuntimeError("no hay loop")

    monkeypatch.setattr(sc, "_crear_tarea", _explota)

    with caplog.at_level(logging.ERROR, logger=sc.logger.name):
        sc.ensure_started()

    assert sc._task is None
    assert "no hay loop" in caplog.text


async def test_a_dead_task_is_restarted_by_the_next_request(habilitado):
    sc.ensure_started()
    primera = sc._task
    primera.cancel()
    await asyncio.gather(primera, return_exceptions=True)

    sc.ensure_started()

    assert sc._task is not primera and not sc._task.done()


async def test_stopping_cancels_the_task_and_clears_the_state(habilitado):
    sc.ensure_started()
    tarea = sc._task

    await sc.detener()

    assert tarea.done() and sc._task is None


async def test_stopping_with_nothing_running_is_a_no_op():
    await sc.detener()

    assert sc._task is None


async def test_require_motored_ready_starts_both_supervisors(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(deps, "motored_secret_is_safe", lambda: True)
    llamadas = []
    monkeypatch.setattr(
        deps.supervisor, "ensure_started", lambda: llamadas.append("cargas"))
    monkeypatch.setattr(
        deps.supervisor_corridas, "ensure_started",
        lambda: llamadas.append("corridas"))

    await deps.require_motored_ready()

    assert llamadas == ["cargas", "corridas"]


# --- El loop: un tick roto no lo tumba ---------------------------------------


async def test_a_failing_tick_is_logged_and_the_loop_keeps_going(
        monkeypatch, caplog):
    ticks = []

    async def _tick(**kwargs):
        ticks.append(1)
        raise RuntimeError("tick roto")

    monkeypatch.setattr(sc, "run_tick", _tick)
    dormir = Dormir(cortar_en=3)

    with caplog.at_level(logging.ERROR, logger=sc.logger.name):
        with pytest.raises(asyncio.CancelledError):
            await sc._run_forever(dormir=dormir)

    assert len(ticks) == 3
    assert caplog.text.count("tick roto") >= 3
    assert dormir.esperas == [settings.MOTORED_CORRIDA_POLL_SEGUNDOS] * 3


async def test_a_healthy_tick_sleeps_the_poll_interval(monkeypatch):
    async def _tick(**kwargs):
        return None

    monkeypatch.setattr(sc, "run_tick", _tick)
    dormir = Dormir(cortar_en=2)

    with pytest.raises(asyncio.CancelledError):
        await sc._run_forever(dormir=dormir)

    assert dormir.esperas == [settings.MOTORED_CORRIDA_POLL_SEGUNDOS] * 2


async def test_cancelling_the_loop_propagates_for_a_clean_shutdown(
        monkeypatch):
    async def _tick(**kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(sc, "run_tick", _tick)
    tarea = asyncio.create_task(sc._run_forever())
    await asyncio.sleep(0)

    tarea.cancel()

    with pytest.raises(asyncio.CancelledError):
        await tarea


# --- S6b-8: la tabla `corrida` no existe ------------------------------------


def test_the_missing_table_error_is_recognised():
    assert sc.es_tabla_ausente(_tabla_ausente()) is True


def test_the_missing_table_error_of_a_child_table_is_recognised():
    error = ProgrammingError(
        "SELECT 1", {},
        Exception('relation "corrida_sucursal" does not exist'))

    assert sc.es_tabla_ausente(error) is True


@pytest.mark.parametrize("error", [
    ProgrammingError("x", {}, Exception('relation "carga_archivo" does not '
                                        'exist')),
    ProgrammingError("x", {}, Exception('syntax error at or near "FROM"')),
    OperationalError("x", {}, Exception("connection refused")),
    RuntimeError('relation "corrida" does not exist'),
])
def test_other_errors_are_not_mistaken_for_a_missing_table(error):
    assert sc.es_tabla_ausente(error) is False


async def test_a_missing_table_idles_with_a_single_warning(
        monkeypatch, caplog):
    llamadas = []

    async def _tick(**kwargs):
        llamadas.append(1)
        raise _tabla_ausente()

    monkeypatch.setattr(sc, "run_tick", _tick)
    monkeypatch.setattr(sc, "_aviso_tabla_ausente", False)
    dormir = Dormir(cortar_en=4)

    with caplog.at_level(logging.DEBUG, logger=sc.logger.name):
        with pytest.raises(asyncio.CancelledError):
            await sc._run_forever(dormir=dormir)

    avisos = [r for r in caplog.records if r.levelno == logging.WARNING]
    errores = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(llamadas) == 4
    assert len(avisos) == 1 and "corrida" in avisos[0].getMessage()
    assert errores == []


async def test_a_missing_table_waits_longer_than_the_normal_poll(monkeypatch):
    async def _tick(**kwargs):
        raise _tabla_ausente()

    monkeypatch.setattr(sc, "run_tick", _tick)
    monkeypatch.setattr(sc, "_aviso_tabla_ausente", False)
    dormir = Dormir(cortar_en=2)

    with pytest.raises(asyncio.CancelledError):
        await sc._run_forever(dormir=dormir)

    assert dormir.esperas == [sc.ESPERA_SIN_TABLA_SEGUNDOS] * 2
    poll = settings.MOTORED_CORRIDA_POLL_SEGUNDOS
    assert sc.ESPERA_SIN_TABLA_SEGUNDOS > poll


async def test_the_loop_resumes_normally_once_the_table_appears(
        monkeypatch, caplog):
    respuestas = [_tabla_ausente(), None, None]

    async def _tick(**kwargs):
        actual = respuestas.pop(0)
        if actual is not None:
            raise actual

    monkeypatch.setattr(sc, "run_tick", _tick)
    monkeypatch.setattr(sc, "_aviso_tabla_ausente", False)
    dormir = Dormir(cortar_en=3)

    with caplog.at_level(logging.INFO, logger=sc.logger.name):
        with pytest.raises(asyncio.CancelledError):
            await sc._run_forever(dormir=dormir)

    poll = settings.MOTORED_CORRIDA_POLL_SEGUNDOS
    assert dormir.esperas == [sc.ESPERA_SIN_TABLA_SEGUNDOS, poll, poll]
    assert "disponible" in caplog.text


async def test_stopping_the_loop_rearms_the_single_warning(
        monkeypatch, caplog):
    async def _tick(**kwargs):
        raise _tabla_ausente()

    monkeypatch.setattr(sc, "run_tick", _tick)
    monkeypatch.setattr(sc, "_aviso_tabla_ausente", True)

    with caplog.at_level(logging.WARNING, logger=sc.logger.name):
        with pytest.raises(asyncio.CancelledError):
            await sc._run_forever(dormir=Dormir(cortar_en=1))

    assert caplog.records == []

    await sc.detener()

    assert sc._aviso_tabla_ausente is False


# --- Un tick ----------------------------------------------------------------


class Traza:
    """Anota el orden en que el tick llama al barrido, al claim y al job."""

    def __init__(self, reclamada=None):
        self.pasos = []
        self.reclamada = reclamada
        self.kwargs = {}

    async def barrer(self, db, ahora, **kwargs):
        self.pasos.append("barrer")
        self.kwargs["barrer"] = (ahora, kwargs)
        return []

    async def reclamar(self, db, ahora):
        self.pasos.append("reclamar")
        return self.reclamada

    async def ejecutar(self, corrida_id, **kwargs):
        self.pasos.append("ejecutar")
        self.kwargs["ejecutar"] = (corrida_id, kwargs)
        return "BORRADOR"

    async def retener(self, db, ahora):
        self.pasos.append("retener")
        return None


@pytest.fixture
def traza(monkeypatch):
    doble = Traza()
    monkeypatch.setattr(ej, "barrer_estancadas", doble.barrer)
    monkeypatch.setattr(ej, "reclamar_siguiente", doble.reclamar)
    monkeypatch.setattr(ej, "ejecutar_corrida", doble.ejecutar)
    monkeypatch.setattr(rc, "ejecutar_si_corresponde", doble.retener)
    return doble


async def test_a_tick_sweeps_then_claims_then_runs_the_claimed_corrida(
        traza):
    traza.reclamada = ID

    resultado = await sc.run_tick(
        session_factory=_fabrica(), reloj=_reloj)

    assert resultado == ID
    assert traza.pasos == ["barrer", "reclamar", "ejecutar"]


async def test_the_sweep_uses_the_configured_timeout_and_attempts(traza):
    await sc.run_tick(session_factory=_fabrica(), reloj=_reloj)

    ahora, kwargs = traza.kwargs["barrer"]
    assert ahora == AHORA
    assert kwargs == {
        "timeout_min": settings.MOTORED_CORRIDA_TIMEOUT_MIN,
        "max_intentos": settings.MOTORED_CORRIDA_MAX_INTENTOS}


async def test_the_job_shares_the_carga_thread_pool(traza):
    traza.reclamada = ID

    await sc.run_tick(session_factory=_fabrica(), reloj=_reloj)

    _, kwargs = traza.kwargs["ejecutar"]
    assert kwargs["ejecutor"] is supervisor.POOL_INGESTA


async def test_a_tick_with_nothing_pending_runs_the_retention_check(traza):
    resultado = await sc.run_tick(
        session_factory=_fabrica(), reloj=_reloj)

    assert resultado is None
    assert traza.pasos == ["barrer", "reclamar", "retener"]


async def test_a_tick_that_claimed_a_corrida_skips_the_retention(traza):
    traza.reclamada = ID

    await sc.run_tick(session_factory=_fabrica(), reloj=_reloj)

    assert "retener" not in traza.pasos


async def test_the_corrida_job_runs_after_the_claim_session_is_closed(
        monkeypatch, traza):
    estado = {"abierta": False, "abierta_al_ejecutar": None}

    class Contexto(FabricaDeSesion):
        async def __aenter__(self):
            estado["abierta"] = True
            return self.sesion

        async def __aexit__(self, tipo, valor, traza_):
            estado["abierta"] = False
            return False

    async def _ejecutar(corrida_id, **kwargs):
        estado["abierta_al_ejecutar"] = estado["abierta"]
        return "BORRADOR"

    traza.reclamada = ID
    monkeypatch.setattr(ej, "ejecutar_corrida", _ejecutar)

    await sc.run_tick(
        session_factory=Contexto(SesionConCommits()), reloj=_reloj)

    assert estado["abierta_al_ejecutar"] is False


# --- Runner -----------------------------------------------------------------


async def test_the_inline_runner_claims_and_runs_the_corrida(monkeypatch):
    llamadas = []

    async def _reclamar_y_ejecutar(corrida_id, **kwargs):
        llamadas.append(corrida_id)
        return "BORRADOR"

    monkeypatch.setattr(ej, "reclamar_y_ejecutar", _reclamar_y_ejecutar)

    await rr.InlineCorridaRunner().enqueue(ID)

    assert llamadas == [ID]


async def test_the_supervisor_runner_only_makes_sure_the_loop_runs(
        monkeypatch):
    llamadas = []
    monkeypatch.setattr(
        sc, "ensure_started", lambda: llamadas.append("arranque"))

    await rr.SupervisorCorridaRunner().enqueue(ID)

    assert llamadas == ["arranque"]


# --- Retención --------------------------------------------------------------


@pytest.fixture
def retencion_activa(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_CORRIDA_RETENCION_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_CORRIDA_RETENCION_DIAS", 45)


async def test_the_retention_is_off_by_default_and_never_queries(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_CORRIDA_RETENCION_ENABLED", False)
    db = SesionConCommits()

    assert await rc.ejecutar_si_corresponde(db, AHORA) is None
    assert db.executed_statements == []


def test_the_retention_setting_defaults_are_the_design_values():
    campos = type(settings).model_fields
    assert campos["MOTORED_CORRIDA_RETENCION_ENABLED"].default is False
    assert campos["MOTORED_CORRIDA_RETENCION_DIAS"].default == 45
    assert campos["MOTORED_CORRIDA_POLL_SEGUNDOS"].default == 5
    assert campos["MOTORED_CORRIDA_TIMEOUT_MIN"].default == 10
    assert campos["MOTORED_CORRIDA_MAX_INTENTOS"].default == 3


async def test_the_retention_waits_for_its_daily_due_check(retencion_activa):
    ayer = (AHORA - datetime.timedelta(hours=2)).replace(tzinfo=None)
    db = SesionConCommits(execute_queue=[[ayer]])

    assert await rc.ejecutar_si_corresponde(db, AHORA) is None
    assert len(db.executed_statements) == 1


async def test_the_retention_deletes_only_annulled_failed_or_draft_corridas(
        retencion_activa):
    db = SesionConCommits(execute_queue=[[None], [ID, ID], [], []])

    borradas = await rc.ejecutar_si_corresponde(db, AHORA)

    assert borradas == 2
    seleccion = db.executed_statements[1]
    valores = _sql(seleccion).params.values()
    estados_en_consulta = next(v for v in valores if isinstance(v, list))
    assert sorted(estados_en_consulta) == sorted(
        [estados.ANULADA, estados.FALLIDA, estados.BORRADOR])
    assert estados.CERRADA not in estados_en_consulta


async def test_the_retention_keeps_corridas_with_events_or_closed_tiendas(
        retencion_activa):
    """F4 (B3a): una corrida BORRADOR cuyo pedido ya tuvo un evento
    (cerrado, reabierto) o cuya tienda está CERRADO/ENVIADO es historia del
    negocio, aunque su estado de cálculo sea purgable."""
    db = SesionConCommits(execute_queue=[[None], [], []])

    await rc.ejecutar_si_corresponde(db, AHORA)

    sql = str(db.executed_statements[1].compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True}))
    assert "NOT (EXISTS (SELECT * \nFROM pedido_evento" in sql
    assert "pedido_evento.corrida_id = corrida.id" in sql
    assert "NOT (EXISTS (SELECT * \nFROM corrida_sucursal" in sql
    assert "corrida_sucursal.estado_pedido IN ('CERRADO', 'ENVIADO')" in sql


async def test_the_retention_cutoff_is_45_days_before_now(retencion_activa):
    db = SesionConCommits(execute_queue=[[None], [ID], []])

    await rc.ejecutar_si_corresponde(db, AHORA)

    limite = (AHORA - datetime.timedelta(days=45)).replace(tzinfo=None)
    assert limite in _sql(db.executed_statements[1]).params.values()


async def test_the_retention_writes_one_ledger_row_for_the_corrida_table(
        retencion_activa):
    db = SesionConCommits(execute_queue=[[None], [ID, ID], []])

    await rc.ejecutar_si_corresponde(db, AHORA)

    (fila,) = db.added
    assert fila.tabla == "corrida"
    assert fila.filas_eliminadas == 2
    assert fila.fecha_limite == (AHORA - datetime.timedelta(days=45)).date()
    assert fila.ejecutado_en == AHORA.replace(tzinfo=None)
    assert db.commits >= 2


async def test_the_retention_deletes_in_bounded_chunks(retencion_activa):
    db = SesionConCommits(execute_queue=[[None], [ID, ID], [], [ID], []])

    borradas = await rc.ejecutar_si_corresponde(db, AHORA, tamano=2)

    assert borradas == 3


async def test_the_due_check_reads_the_ledger_rows_of_the_corrida_table(
        retencion_activa):
    db = SesionConCommits(execute_queue=[[None], []])

    await rc.ejecutar_si_corresponde(db, AHORA)

    assert "corrida" in _sql(db.executed_statements[0]).params.values()


async def test_a_run_with_nothing_to_delete_still_records_the_ledger_row(
        retencion_activa):
    db = SesionConCommits(execute_queue=[[None], []])

    borradas = await rc.ejecutar_si_corresponde(db, AHORA)

    assert borradas == 0
    assert [fila.filas_eliminadas for fila in db.added] == [0]
