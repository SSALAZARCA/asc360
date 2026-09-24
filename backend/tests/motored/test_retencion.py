"""
Motored Pedidos — Fase 2 "Ingesta", Phase 12 "Retention Purge" (sdd/motored-
pedidos-ingesta, ADR-3).

`services/retencion.py` runs off the supervisor's own tick (no new
mechanism), gated on `MOTORED_RETENCION_ENABLED` (default `False`), and
never touches Postgres directly in this suite — same `FakeAsyncSession`
convention as the rest of `tests/motored/` (`tests/motored/conftest.py`),
matching this suite's long-standing property of never requiring a live
database.

Deliberate deviation from the design's literal wording, documented here:
ADR-3 says "20 000-row `ctid`-bounded chunks". `ctid` is a Postgres physical
row identifier with no equivalent in a `FakeAsyncSession`-driven unit test
(and no live Postgres exists anywhere in this suite to exercise it against).
`ejecutar_purga_inventario` instead selects a bounded batch of PRIMARY KEY
ids (`LIMIT chunk_size`) and deletes exactly that batch — functionally
equivalent to the design's intent (a single DELETE never touches more than
`chunk_size` rows, no full-table scan, no long lock) and testable without a
live database. `chunk_size` defaults to the design's `20 000` in production
but is an explicit parameter here so a small fixture can force 2+ chunks
without instantiating tens of thousands of fake rows.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

from app.config import settings
from app.motored.services import retencion
from tests.motored.conftest import FakeAsyncSession

# ---------------------------------------------------------------------------
# MOTORED_RETENCION_ENABLED — actual default, and hard off-switch
# ---------------------------------------------------------------------------


def test_retencion_enabled_default_is_false():
    assert settings.MOTORED_RETENCION_ENABLED is False


async def test_ejecutar_si_corresponde_no_hace_nada_si_esta_deshabilitado(monkeypatch):
    """Disabled must short-circuit BEFORE any query — no due-check, no
    active-job check, nothing — regardless of how overdue the purge is."""
    monkeypatch.setattr(settings, "MOTORED_RETENCION_ENABLED", False)
    session = FakeAsyncSession(execute_queue=[])

    resultado = await retencion.ejecutar_si_corresponde(session)

    assert resultado is None
    assert session.executed_statements == []


# ---------------------------------------------------------------------------
# "No active job" gate — the core safety property (ADR-3)
# ---------------------------------------------------------------------------


async def test_hay_job_activo_true_cuando_hay_una_fila_procesando_o_aplicando():
    session = FakeAsyncSession(execute_queue=[[(uuid.uuid4(),)]])
    assert await retencion.hay_job_activo(session) is True


async def test_hay_job_activo_false_cuando_no_hay_ninguna_fila_activa():
    session = FakeAsyncSession(execute_queue=[[]])
    assert await retencion.hay_job_activo(session) is False


async def test_ejecutar_si_corresponde_se_salta_cuando_hay_job_activo(monkeypatch):
    """The purge-vs-apply hazard, eliminated rather than merely tested for:
    a live job (PROCESANDO/APLICANDO) must block the purge unconditionally,
    even if the retention window is badly overdue. Only ONE query should
    fire — the active-job check — proving the due-check never even runs."""
    monkeypatch.setattr(settings, "MOTORED_RETENCION_ENABLED", True)
    session = FakeAsyncSession(execute_queue=[[(uuid.uuid4(),)]])

    resultado = await retencion.ejecutar_si_corresponde(session)

    assert resultado is None
    assert len(session.executed_statements) == 1


# ---------------------------------------------------------------------------
# Due-check (ADR-3) — anchored purely in `retencion_ejecucion`, no in-process
# state, so it survives a restart with no external lock.
# ---------------------------------------------------------------------------


async def test_esta_vencida_true_cuando_nunca_corrio():
    session = FakeAsyncSession(execute_queue=[[None]])
    assert await retencion.esta_vencida(session) is True


async def test_esta_vencida_false_cuando_corrio_hace_menos_de_24h():
    now = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc)
    ultima = now - timedelta(hours=1)
    session = FakeAsyncSession(execute_queue=[[ultima]])
    assert await retencion.esta_vencida(session, now=now) is False


async def test_esta_vencida_true_cuando_corrio_hace_mas_de_24h():
    now = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc)
    ultima = now - timedelta(hours=25)
    session = FakeAsyncSession(execute_queue=[[ultima]])
    assert await retencion.esta_vencida(session, now=now) is True


async def test_esta_vencida_exactamente_24h_no_cuenta_como_vencida():
    now = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc)
    ultima = now - timedelta(hours=24)
    session = FakeAsyncSession(execute_queue=[[ultima]])
    assert await retencion.esta_vencida(session, now=now) is False


async def test_esta_vencida_reconstruida_desde_cero_reproduce_la_misma_decision_de_antes_del_reinicio():
    """Simulates a process restart: TWO completely independent
    `FakeAsyncSession` objects (nothing shared between them — no module
    global, no shared instance), both reading the SAME row that would live
    in `retencion_ejecucion`. If the schedule anchor lived in process memory
    instead of the table, a 'reconstructed from scratch' check would have
    nothing to read and could not reproduce the prior decision."""
    now = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc)
    fila_en_la_tabla = now - timedelta(hours=30)

    session_antes_del_reinicio = FakeAsyncSession(execute_queue=[[fila_en_la_tabla]])
    decision_antes = await retencion.esta_vencida(session_antes_del_reinicio, now=now)

    session_despues_del_reinicio = FakeAsyncSession(execute_queue=[[fila_en_la_tabla]])
    decision_despues = await retencion.esta_vencida(session_despues_del_reinicio, now=now)

    assert decision_antes is True
    assert decision_despues is True
    assert decision_antes == decision_despues


# ---------------------------------------------------------------------------
# Chunked purge — bounded to `fecha_corte < max(fecha_corte) - 90 days`,
# anchored to data not `now()`.
# ---------------------------------------------------------------------------


def test_tamano_chunk_default_es_20000():
    assert retencion.TAMANO_CHUNK == 20000


def test_calcular_fecha_limite_ancla_a_la_fecha_corte_maxima_no_a_now():
    maxima = date(2026, 9, 15)
    assert retencion.calcular_fecha_limite(maxima, dias=90) == maxima - timedelta(days=90)


async def test_ejecutar_purga_inventario_no_hace_nada_si_la_tabla_esta_vacia():
    session = FakeAsyncSession(execute_queue=[[None]])

    resultado = await retencion.ejecutar_purga_inventario(session)

    assert resultado is None
    assert session.added == []


async def test_ejecutar_purga_inventario_corre_en_chunks_acotados_y_escribe_una_fila_de_ledger():
    now = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc)
    max_fecha_corte = date(2026, 9, 15)
    limite_esperado = max_fecha_corte - timedelta(days=settings.MOTORED_RETENCION_DIAS)

    ids_chunk_1 = [uuid.uuid4(), uuid.uuid4()]
    ids_chunk_2 = [uuid.uuid4(), uuid.uuid4()]
    ids_chunk_3 = [uuid.uuid4()]  # último chunk, más chico que chunk_size -> corta el loop

    session = FakeAsyncSession(
        execute_queue=[
            [max_fecha_corte],  # select max(fecha_corte)
            ids_chunk_1,  # select ids, chunk 1 (lleno -> sigue)
            [],  # delete chunk 1
            ids_chunk_2,  # select ids, chunk 2 (lleno -> sigue)
            [],  # delete chunk 2
            ids_chunk_3,  # select ids, chunk 3 (1 < chunk_size=2 -> corta)
            [],  # delete chunk 3
        ]
    )

    ejecucion = await retencion.ejecutar_purga_inventario(session, now=now, chunk_size=2)

    assert ejecucion.filas_eliminadas == 5
    assert ejecucion.fecha_limite == limite_esperado
    assert ejecucion.tabla == retencion.TABLA_INVENTARIO_SNAPSHOT
    assert ejecucion.ejecutado_en == now.replace(tzinfo=None)
    assert ejecucion.duracion_ms >= 0
    assert len(session.added) == 1
    assert session.added[0] is ejecucion
    assert session.committed is True

    # nunca borra más de `chunk_size` filas por sentencia, y cada DELETE
    # toca EXACTAMENTE los ids que su propio SELECT bounded acaba de traer
    # -- nunca los de otro chunk, y nunca nada por fuera del filtro
    # `fecha_corte < limite`.
    delete_chunk1_params = session.executed_statements[2].compile().construct_params()
    ids_bound_en_delete_chunk1 = {
        item
        for valor in delete_chunk1_params.values()
        for item in (valor if isinstance(valor, list) else [valor])
    }
    assert set(ids_chunk_1) <= ids_bound_en_delete_chunk1
    assert not (set(ids_chunk_2) | set(ids_chunk_3)) & ids_bound_en_delete_chunk1

    select_ids_chunk1_params = session.executed_statements[1].compile().construct_params().values()
    assert limite_esperado in select_ids_chunk1_params


async def test_ejecutar_purga_inventario_guarda_ejecutado_en_como_naive_utc():
    """`retencion_ejecucion.ejecutado_en` es un `DateTime` NAIVE (a
    diferencia de `carga_archivo.latido_en`, que es `DateTime(timezone=
    True)`) -- verificado directamente contra el modelo. Escribir un
    datetime AWARE ahí es correcto en memoria pero revienta contra un
    asyncpg real ('can't subtract offset-naive and offset-aware
    datetimes'/DataError de tipo de columna) apenas esto corra contra
    Postgres de verdad. `ejecutar_purga_inventario` debe normalizar a
    naive UTC antes de construir la fila, igual que el resto de este
    modelo ya hace con `default=datetime.utcnow`."""
    now_aware = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc)
    session = FakeAsyncSession(execute_queue=[[date(2026, 9, 15)], []])

    ejecucion = await retencion.ejecutar_purga_inventario(session, now=now_aware)

    assert ejecucion.ejecutado_en.tzinfo is None
    assert ejecucion.ejecutado_en == now_aware.replace(tzinfo=None)


async def test_ejecutar_purga_inventario_se_detiene_en_un_solo_chunk_si_alcanza():
    now = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc)
    max_fecha_corte = date(2026, 9, 15)
    ids_unico_chunk = [uuid.uuid4(), uuid.uuid4()]

    session = FakeAsyncSession(
        execute_queue=[
            [max_fecha_corte],
            ids_unico_chunk,  # menos que chunk_size (20000 por default) -> corta enseguida
            [],
        ]
    )

    ejecucion = await retencion.ejecutar_purga_inventario(session, now=now)

    assert ejecucion.filas_eliminadas == 2
    assert len(session.executed_statements) == 3


# ---------------------------------------------------------------------------
# End-to-end (still FakeAsyncSession): enabled + no active job + overdue ->
# runs the purge and returns the ledger row.
# ---------------------------------------------------------------------------


async def test_ejecutar_si_corresponde_ejecuta_la_purga_completa_cuando_corresponde(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_RETENCION_ENABLED", True)
    now = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc)
    max_fecha_corte = date(2026, 9, 15)
    ultima_ejecucion = now - timedelta(hours=25)

    session = FakeAsyncSession(
        execute_queue=[
            [],  # hay_job_activo: sin filas activas
            [ultima_ejecucion],  # esta_vencida: última corrida hace 25h -> vencida
            [max_fecha_corte],  # ejecutar_purga_inventario: max(fecha_corte)
            [],  # select ids -> vacío -> nada que borrar, corta sin delete
        ]
    )

    ejecucion = await retencion.ejecutar_si_corresponde(session, now=now)

    assert ejecucion is not None
    assert ejecucion.filas_eliminadas == 0


async def test_ejecutar_si_corresponde_no_hace_nada_si_no_esta_vencida(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_RETENCION_ENABLED", True)
    now = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc)
    ultima_ejecucion = now - timedelta(hours=1)

    session = FakeAsyncSession(
        execute_queue=[
            [],  # hay_job_activo: sin filas activas
            [ultima_ejecucion],  # esta_vencida: corrió hace 1h -> no vencida
        ]
    )

    resultado = await retencion.ejecutar_si_corresponde(session, now=now)

    assert resultado is None
    assert len(session.executed_statements) == 2
