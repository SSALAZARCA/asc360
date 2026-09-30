"""
Motored Pedidos F3 "Motor", S6b (sdd/motored-pedidos-motor, ADR-5): la
ejecución de una corrida en segundo plano.

Sin base de datos real (el claim y el barrido reales se prueban en
`pg_real/test_supervisor_corridas_pg.py`): un reloj congelado, sesiones de
juguete que anotan commits y rollbacks, y los colaboradores del servicio
reemplazados por dobles. Cubre el claim atómico, el latido, el barrido de
corridas estancadas con su backoff, los reintentos DBAPI (1 s, 2 s), el
cómputo fuera del event loop, la falla aislada por sucursal, la parada
cooperativa y la devolución ordenada ante un cierre del proceso.
"""
import asyncio
import dataclasses
import datetime
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import (
    DataError,
    DBAPIError,
    IntegrityError,
    InterfaceError,
    OperationalError,
    ProgrammingError,
)

from app.motored.services.corridas import codigos
from app.motored.services.corridas import ejecucion as ej
from app.motored.services.corridas import servicio as sv
from app.motored.services.corridas.cargador import (
    DatosSucursal, ErrorCargador)
from app.motored.services.motor.tipos import ParametrosMotor
from tests.motored.conftest import (
    INSTANTE_CONGELADO,
    FabricaDeSesion,
    SesionConCommits,
)
from tests.motored.fixtures.motor.constructores import (
    atributos,
    fila_patron,
)

ID = uuid.UUID(int=901)
OTRA = uuid.UUID(int=902)
SUC_A, SUC_B = uuid.UUID(int=101), uuid.UUID(int=102)
AHORA = INSTANTE_CONGELADO
SEGUNDOS = datetime.timedelta(seconds=1)


def _reloj():
    return AHORA


class Dormir:
    def __init__(self):
        self.esperas = []

    async def __call__(self, segundos):
        self.esperas.append(segundos)


def _sql(sentencia):
    return sentencia.compile(dialect=postgresql.dialect())


def _valores(sentencia):
    return list(_sql(sentencia).params.values())


# --- Backoff y decisión de una corrida estancada -----------------------------


@pytest.mark.parametrize("intentos, segundos", [(1, 30), (2, 60), (3, 120)])
def test_the_retry_wait_starts_at_30_seconds_and_doubles(intentos, segundos):
    assert ej.espera_reintento(intentos) == datetime.timedelta(
        seconds=segundos)


def test_a_stuck_corrida_with_attempts_left_goes_back_to_pending():
    decision = ej.decidir_estancada(2, 3, AHORA)

    assert decision.estado == "PENDIENTE"
    assert decision.reintentar_despues_de == AHORA + 60 * SEGUNDOS
    assert decision.codigo is None


def test_the_first_attempt_waits_30_seconds_before_the_retry():
    decision = ej.decidir_estancada(1, 3, AHORA)

    assert decision.reintentar_despues_de == AHORA + 30 * SEGUNDOS


def test_a_corrida_out_of_attempts_fails_with_e031():
    decision = ej.decidir_estancada(3, 3, AHORA)

    assert decision.estado == "FALLIDA"
    assert decision.codigo == codigos.E_CORRIDA_REINTENTOS_AGOTADOS
    assert decision.reintentar_despues_de is None


# --- Qué errores de base se reintentan ---------------------------------------


def _dbapi(clase):
    return clase("SELECT 1", {}, Exception("boom"))


@pytest.mark.parametrize("clase", [OperationalError, InterfaceError])
def test_connection_level_errors_are_transient(clase):
    assert sv.es_transitorio(_dbapi(clase)) is True


def test_a_generic_dbapi_error_such_as_a_deadlock_is_transient():
    assert sv.es_transitorio(_dbapi(DBAPIError)) is True


@pytest.mark.parametrize(
    "clase", [IntegrityError, DataError, ProgrammingError])
def test_deterministic_database_errors_are_not_transient(clase):
    assert sv.es_transitorio(_dbapi(clase)) is False


def test_a_plain_python_error_is_not_transient():
    assert sv.es_transitorio(ValueError("x")) is False


# --- Claim atómico -----------------------------------------------------------


async def test_the_claim_is_one_atomic_update_returning_the_id():
    db = SesionConCommits(execute_queue=[[ID]])

    reclamada = await ej.reclamar_siguiente(db, AHORA)

    assert reclamada == ID
    (sentencia,) = db.executed_statements
    texto = str(_sql(sentencia))
    assert texto.startswith("UPDATE corrida SET")
    assert "FOR UPDATE SKIP LOCKED" in texto
    assert "RETURNING corrida.id" in texto
    assert db.commits == 1


async def test_the_claim_only_touches_the_corrida_table():
    db = SesionConCommits(execute_queue=[[ID]])

    await ej.reclamar_siguiente(db, AHORA)

    assert "carga_archivo" not in str(_sql(db.executed_statements[0]))


async def test_the_claim_only_takes_pending_corridas_whose_wait_is_over():
    db = SesionConCommits(execute_queue=[[ID]])

    await ej.reclamar_siguiente(db, AHORA)

    texto = str(_sql(db.executed_statements[0]))
    valores = _valores(db.executed_statements[0])
    assert "corrida.reintentar_despues_de IS NULL" in texto
    assert "corrida.reintentar_despues_de <=" in texto
    assert texto.count("corrida.estado =") == 2
    assert valores.count("PENDIENTE") == 2
    assert AHORA in valores


async def test_the_claim_starts_the_heartbeat_and_counts_the_attempt():
    db = SesionConCommits(execute_queue=[[ID]])

    await ej.reclamar_siguiente(db, AHORA)

    sin_espacios = str(_sql(db.executed_statements[0])).replace(" ", "")
    valores = _valores(db.executed_statements[0])
    assert "CALCULANDO" in valores
    assert "intentos=(corrida.intentos+" in sin_espacios
    assert "latido_en=" in sin_espacios
    assert valores.count(AHORA) >= 2


async def test_the_claim_takes_the_oldest_pending_corrida_first():
    db = SesionConCommits(execute_queue=[[ID]])

    await ej.reclamar_siguiente(db, AHORA)

    texto = str(_sql(db.executed_statements[0]))
    assert "ORDER BY corrida.created_at" in texto


async def test_no_pending_corrida_means_no_claim_and_no_error():
    db = SesionConCommits(execute_queue=[[]])

    assert await ej.reclamar_siguiente(db, AHORA) is None
    assert db.commits == 1


# --- Barrido de corridas estancadas ------------------------------------------


async def test_the_sweep_selects_only_calculando_with_an_expired_heartbeat():
    db = SesionConCommits(execute_queue=[[]])

    resultado = await ej.barrer_estancadas(
        db, AHORA, timeout_min=10, max_intentos=3)

    assert resultado == []
    (consulta,) = db.executed_statements
    texto = str(_sql(consulta))
    valores = _valores(consulta)
    assert "FOR UPDATE SKIP LOCKED" in texto
    assert "corrida.latido_en IS NOT NULL" in texto
    assert "corrida.latido_en <" in texto
    assert AHORA - datetime.timedelta(minutes=10) in valores
    assert "CALCULANDO" in valores


async def test_the_sweep_retries_a_stuck_corrida_with_backoff():
    db = SesionConCommits(execute_queue=[[(ID, 1)], [ID]])

    resultado = await ej.barrer_estancadas(
        db, AHORA, timeout_min=10, max_intentos=3)

    assert resultado == [(ID, "PENDIENTE")]
    actualizar = db.executed_statements[1]
    valores = _valores(actualizar)
    assert "PENDIENTE" in valores
    assert AHORA + 30 * SEGUNDOS in valores
    assert db.commits == 1


async def test_the_sweep_backs_off_longer_after_more_attempts():
    db = SesionConCommits(execute_queue=[[(ID, 2)], [ID]])

    await ej.barrer_estancadas(db, AHORA, timeout_min=10, max_intentos=3)

    assert AHORA + 60 * SEGUNDOS in _valores(db.executed_statements[1])


async def test_the_sweep_fails_a_corrida_that_ran_out_of_attempts():
    db = SesionConCommits(execute_queue=[[(ID, 3)], [ID]])

    resultado = await ej.barrer_estancadas(
        db, AHORA, timeout_min=10, max_intentos=3)

    assert resultado == [(ID, "FALLIDA")]
    valores = _valores(db.executed_statements[1])
    assert "FALLIDA" in valores
    assert "PENDIENTE" not in valores


async def test_the_sweep_records_the_event_in_the_append_only_log():
    db = SesionConCommits(execute_queue=[[(ID, 3)], [ID]])

    await ej.barrer_estancadas(db, AHORA, timeout_min=10, max_intentos=3)

    eventos = [
        v[0] for v in _valores(db.executed_statements[1])
        if isinstance(v, list) and v and isinstance(v[0], dict)]
    assert eventos[0]["evento"] == "BARRIDA"
    assert eventos[0]["resultado"] == "FALLIDA"
    assert eventos[0]["codigo"] == codigos.E_CORRIDA_REINTENTOS_AGOTADOS


async def test_the_sweep_transition_is_guarded_by_state_and_attempts():
    db = SesionConCommits(execute_queue=[[(ID, 1)], [ID]])

    await ej.barrer_estancadas(db, AHORA, timeout_min=10, max_intentos=3)

    texto = str(_sql(db.executed_statements[1]))
    assert "corrida.estado =" in texto
    assert "corrida.intentos =" in texto


async def test_a_corrida_claimed_by_someone_else_meanwhile_is_not_reported():
    db = SesionConCommits(execute_queue=[[(ID, 1)], []])

    resultado = await ej.barrer_estancadas(
        db, AHORA, timeout_min=10, max_intentos=3)

    assert resultado == []


# --- Cómputo fuera del event loop --------------------------------------------


class Colaboradores:
    """Dobles de la carga, el cálculo y el guardado de una sucursal."""

    def __init__(self):
        self.hilos = []
        self.guardadas = []
        self.fallidas = []
        self.errores_carga = {}
        self.errores_guardado = []

    async def cargar(self, db, sucursal_id, ctx):
        if sucursal_id in self.errores_carga:
            raise self.errores_carga[sucursal_id]
        return DatosSucursal(
            dataclasses.replace(atributos(), sucursal_id=sucursal_id),
            (fila_patron(),))

    def calcular(self, entradas, sucursal, motor, resoluciones):
        self.hilos.append(threading.current_thread().name)
        return SimpleNamespace(estado="OK")

    async def guardar(self, db, corrida_id, datos, resultado, *,
                      consolidar=False):
        if self.errores_guardado:
            raise self.errores_guardado.pop(0)
        self.guardadas.append(datos.atributos.sucursal_id)

    async def marcar(self, db, corrida_id, sucursal_id, codigo, mensaje):
        self.fallidas.append((sucursal_id, codigo))


@pytest.fixture
def colaboradores(monkeypatch):
    doble = Colaboradores()
    monkeypatch.setattr(sv.cargador, "cargar_sucursal", doble.cargar)
    monkeypatch.setattr(sv, "calcular_sucursal", doble.calcular)
    monkeypatch.setattr(sv.persistencia, "guardar_sucursal", doble.guardar)
    monkeypatch.setattr(
        sv.persistencia, "marcar_sucursal_fallida", doble.marcar)
    return doble


CTX = SimpleNamespace(resoluciones={}, consolidar=False)
REF = sv.CorridaRef(ID, "PED-2026-S39-001")


async def test_the_compute_runs_in_the_executor_thread(colaboradores):
    ejecutor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="hilo-x")
    try:
        seguir = await sv.procesar_sucursal(
            SesionConCommits(), REF, SUC_A, CTX, ParametrosMotor(), ejecutor)
    finally:
        ejecutor.shutdown()

    assert seguir is True
    assert colaboradores.hilos == ["hilo-x_0"]
    assert colaboradores.hilos[0] != threading.current_thread().name


async def test_without_an_executor_the_compute_stays_inline(colaboradores):
    await sv.procesar_sucursal(
        SesionConCommits(), REF, SUC_A, CTX, ParametrosMotor())

    assert colaboradores.hilos == [threading.current_thread().name]


async def test_a_transient_database_error_is_not_swallowed_as_e099(
        colaboradores):
    colaboradores.errores_guardado = [_dbapi(OperationalError)]

    with pytest.raises(OperationalError):
        await sv.procesar_sucursal(
            SesionConCommits(), REF, SUC_A, CTX, ParametrosMotor())

    assert colaboradores.fallidas == []


async def test_a_deterministic_database_error_still_fails_only_the_sucursal(
        colaboradores):
    colaboradores.errores_guardado = [_dbapi(IntegrityError)]

    seguir = await sv.procesar_sucursal(
        SesionConCommits(), REF, SUC_A, CTX, ParametrosMotor())

    assert seguir is True
    assert colaboradores.fallidas == [(SUC_A, codigos.E_CORRIDA_INTERNO)]


async def test_a_coded_loader_error_is_kept_and_never_retried(colaboradores):
    error = ErrorCargador(codigos.E_CORRIDA_SUCURSAL_SIN_SIC, "sin SIC")
    colaboradores.errores_carga = {SUC_A: error}

    await sv.procesar_sucursal(
        SesionConCommits(), REF, SUC_A, CTX, ParametrosMotor())

    assert colaboradores.fallidas == [
        (SUC_A, codigos.E_CORRIDA_SUCURSAL_SIN_SIC)]


# --- El recorrido de la corrida ----------------------------------------------


class Servicio:
    """Dobles de las piezas del servicio que el recorrido orquesta."""

    def __init__(self):
        self.procesadas = []
        self.marcadas = []
        self.finalizadas = []
        self.respuestas = {}
        self.pendientes_ids = [SUC_A, SUC_B]
        self.falla_preparar = None
        self.falla_pendientes = None

    async def preparar(self, db, corrida):
        if self.falla_preparar is not None:
            raise self.falla_preparar
        return ParametrosMotor(), CTX

    async def pendientes(self, db, corrida_id):
        if self.falla_pendientes is not None:
            raise self.falla_pendientes
        return list(self.pendientes_ids)

    async def procesar(self, db, corrida, sucursal_id, ctx, motor,
                       ejecutor=None):
        self.procesadas.append((corrida, sucursal_id, ejecutor))
        respuesta = self.respuestas.get(sucursal_id, [True])
        actual = respuesta.pop(0) if len(respuesta) > 1 else respuesta[0]
        if isinstance(actual, BaseException):
            raise actual
        return actual

    async def marcar(self, db, corrida_id, sucursal_id, codigo, mensaje):
        self.marcadas.append((sucursal_id, codigo))
        return True

    async def finalizar(self, db, corrida_id):
        self.finalizadas.append(corrida_id)
        return "BORRADOR"


@pytest.fixture
def servicio(monkeypatch):
    doble = Servicio()
    monkeypatch.setattr(sv, "preparar", doble.preparar)
    monkeypatch.setattr(sv, "pendientes", doble.pendientes)
    monkeypatch.setattr(sv, "procesar_sucursal", doble.procesar)
    monkeypatch.setattr(sv, "marcar_fallida", doble.marcar)
    monkeypatch.setattr(sv, "finalizar_corrida", doble.finalizar)
    return doble


def _corrida(intentos=1):
    return SimpleNamespace(
        id=ID, codigo="PED-2026-S39-001", intentos=intentos)


def _sesion(intentos=1, cola=()):
    return SesionConCommits(
        get_queue=[_corrida(intentos)], execute_queue=list(cola))


async def _correr(db, dormir=None, **kwargs):
    return await ej.ejecutar_corrida(
        ID, session_factory=FabricaDeSesion(db), dormir=dormir or Dormir(),
        reloj=_reloj, max_intentos=3, **kwargs)


async def test_every_pending_sucursal_is_committed_on_its_own(servicio):
    db = _sesion()

    estado = await _correr(db)

    assert estado == "BORRADOR"
    assert [p[1] for p in servicio.procesadas] == [SUC_A, SUC_B]
    assert servicio.finalizadas == [ID]
    assert db.commits == 3


async def test_the_recorrido_hands_plain_values_not_the_orm_row(servicio):
    await _correr(_sesion())

    referencia = servicio.procesadas[0][0]
    assert referencia == sv.CorridaRef(ID, "PED-2026-S39-001")


async def test_the_executor_reaches_every_sucursal(servicio):
    ejecutor = object()

    await _correr(_sesion(), ejecutor=ejecutor)

    assert [p[2] for p in servicio.procesadas] == [ejecutor, ejecutor]


async def test_a_transient_error_is_retried_after_1_and_2_seconds(servicio):
    servicio.respuestas = {SUC_A: [
        _dbapi(OperationalError), _dbapi(OperationalError), True]}
    dormir = Dormir()
    db = _sesion()

    estado = await _correr(db, dormir)

    assert estado == "BORRADOR"
    assert dormir.esperas == [1.0, 2.0]
    assert db.rollbacks == 2
    assert [p[1] for p in servicio.procesadas] == [SUC_A, SUC_A, SUC_A, SUC_B]
    assert servicio.marcadas == []


async def test_three_transient_failures_fail_only_that_sucursal(servicio):
    servicio.respuestas = {SUC_A: [_dbapi(OperationalError)]}
    dormir = Dormir()

    estado = await _correr(_sesion(), dormir)

    assert estado == "BORRADOR"
    assert dormir.esperas == [1.0, 2.0]
    assert servicio.marcadas == [(SUC_A, codigos.E_CORRIDA_INTERNO)]
    assert [p[1] for p in servicio.procesadas][-1] == SUC_B


async def test_a_sucursal_without_a_transient_error_never_waits(servicio):
    dormir = Dormir()

    await _correr(_sesion(), dormir)

    assert dormir.esperas == []


async def test_an_annulled_corrida_stops_the_walk_without_finalizing(
        servicio):
    servicio.respuestas = {SUC_A: [False]}

    estado = await _correr(_sesion())

    assert estado == "ANULADA"
    assert [p[1] for p in servicio.procesadas] == [SUC_A]
    assert servicio.finalizadas == []


async def test_a_failed_preparation_releases_the_corrida_with_backoff(
        servicio):
    servicio.falla_preparar = LookupError("sin proveedor principal")
    db = _sesion(intentos=1, cola=[[ID]])

    estado = await _correr(db)

    assert estado == "PENDIENTE"
    assert servicio.procesadas == []
    valores = _valores(db.executed_statements[-1])
    assert "PENDIENTE" in valores
    assert AHORA + 30 * SEGUNDOS in valores
    assert db.rollbacks == 1
    assert db.commits == 1


async def test_a_failed_preparation_with_no_attempts_left_ends_fallida(
        servicio):
    servicio.falla_preparar = LookupError("sin proveedor principal")
    db = _sesion(intentos=3, cola=[[ID]])

    estado = await _correr(db)

    assert estado == "FALLIDA"
    valores = _valores(db.executed_statements[-1])
    assert "FALLIDA" in valores and "PENDIENTE" not in valores


async def test_any_unexpected_error_mid_walk_also_releases_the_corrida(
        servicio):
    servicio.falla_pendientes = RuntimeError("boom")

    estado = await _correr(_sesion(cola=[[ID]]))

    assert estado == "PENDIENTE"


async def test_the_walk_never_raises_out_of_the_job(servicio):
    servicio.falla_preparar = RuntimeError("boom")

    await _correr(_sesion(cola=[[ID]]))


async def test_a_release_that_cannot_write_leaves_it_to_the_sweep(servicio):
    servicio.falla_preparar = RuntimeError("boom")
    db = _sesion(cola=[_dbapi(OperationalError)])

    estado = await _correr(db)

    assert estado == "CALCULANDO"


async def test_a_shutdown_hands_the_corrida_back_and_keeps_cancelling(
        servicio):
    servicio.respuestas = {SUC_A: [asyncio.CancelledError()]}
    db = _sesion(intentos=2, cola=[[ID]])

    with pytest.raises(asyncio.CancelledError):
        await _correr(db)

    valores = _valores(db.executed_statements[-1])
    texto = str(_sql(db.executed_statements[-1]))
    assert "PENDIENTE" in valores
    assert "greatest(" in texto
    assert servicio.finalizadas == []


async def test_a_shutdown_that_cannot_write_still_cancels(servicio):
    servicio.respuestas = {SUC_A: [asyncio.CancelledError()]}
    db = _sesion(cola=[_dbapi(OperationalError)])

    with pytest.raises(asyncio.CancelledError):
        await _correr(db)


# --- Reclamar y ejecutar una corrida concreta (runner en línea) --------------


async def test_the_inline_path_claims_the_given_corrida_then_runs_it(
        servicio):
    db = _sesion(cola=[[ID]])

    estado = await ej.reclamar_y_ejecutar(
        ID, session_factory=FabricaDeSesion(db), dormir=Dormir(), reloj=_reloj,
        max_intentos=3)

    assert estado == "BORRADOR"
    assert "CALCULANDO" in _valores(db.executed_statements[0])
    assert servicio.finalizadas == [ID]


async def test_the_inline_path_refuses_a_corrida_that_is_not_pending(
        servicio):
    db = _sesion(cola=[[]])

    with pytest.raises(codigos.ErrorCorrida) as error:
        await ej.reclamar_y_ejecutar(
            ID, session_factory=FabricaDeSesion(db), dormir=Dormir(),
            reloj=_reloj, max_intentos=3)

    assert error.value.codigo == codigos.E_CORRIDA_ESTADO_NO_ADMITE
    assert servicio.procesadas == []
