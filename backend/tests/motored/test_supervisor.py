"""
Fase 2 "Ingesta", Phase 2 "JobRunner + Supervisor" (sdd/motored-pedidos-
ingesta, ADR-1/ADR-1b) — el supervisor asyncio en proceso.

No hay Postgres real disponible en CI para Motored, así que el contrato de
la base de datos (claim atómico, sweep) se ejercita contra SQLite real vía
`aiosqlite` -- el mismo patrón ya establecido en
`tests/motored/test_database.py` -- lo suficiente para probar la semántica
transaccional en sí, independiente del dialecto SQL.

`ensure_started()`/`_run_forever()` se prueban con el loop real de
pytest-asyncio, sin nunca dejar un task corriendo de fondo entre tests
(ver `_reset_supervisor` abajo).
"""
import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles

from app.config import settings
from app.motored import database as motored_database
from app.motored.models.carga_archivo import CargaArchivo
from app.motored.services import retencion
from app.motored.services.trabajos import jobs, supervisor


@compiles(JSONB, "sqlite")
def _compile_jsonb_as_json_for_sqlite(element, compiler, **kw):
    """`carga_archivo.log` es `JSONB` (correcto para el Postgres real de
    Motored) -- SQLite no tiene ese tipo, así que esto SOLO le enseña al
    dialecto de SQLite a renderizar la columna como `JSON` al crear la
    tabla en este test. No toca el modelo ni afecta a Postgres."""
    return "JSON"


@pytest.fixture(autouse=True)
async def _reset_supervisor():
    """Ningún test debe dejar el poll loop corriendo para el siguiente."""
    yield
    await supervisor.reset_for_tests()
    jobs.JOB_HANDLERS.clear()


@pytest.fixture
async def sqlite_session_maker(tmp_path, monkeypatch):
    """Un Postgres real de Motored no existe en este entorno de test; una
    SQLite real (no un mock) es suficiente para probar la semántica
    transaccional del claim y del sweep -- el mismo patrón que
    `test_database.py` ya usa para `get_motored_db`."""
    db_path = tmp_path / "supervisor_contract.db"
    monkeypatch.setattr(settings, "MOTORED_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    motored_database.get_motored_engine.cache_clear()

    engine = motored_database.get_motored_engine()
    async with engine.begin() as conn:
        await conn.run_sync(CargaArchivo.__table__.create)

    session_maker = motored_database.motored_session_maker()
    yield session_maker

    await engine.dispose()
    motored_database.get_motored_engine.cache_clear()


def _make_carga(**overrides) -> CargaArchivo:
    defaults = dict(
        id=uuid.uuid4(),
        tipo="VENTAS",
        nombre_archivo="archivo.xlsx",
        hash_sha256="a" * 64,
        ruta_objeto="motored-cargas/x.xlsx",
        bytes=1234,
        estado="PENDIENTE",
    )
    defaults.update(overrides)
    return CargaArchivo(**defaults)


# ---------------------------------------------------------------------------
# Claim atómico (ADR-1): "WHERE id=:id AND estado='PENDIENTE' ... RETURNING id"
# ---------------------------------------------------------------------------


async def test_claim_by_id_of_two_attempts_on_the_same_row_exactly_one_wins(
    sqlite_session_maker,
):
    carga_id = uuid.uuid4()
    async with sqlite_session_maker() as session:
        session.add(_make_carga(id=carga_id))
        await session.commit()

    now = datetime(2026, 9, 21, 12, 0, 0, tzinfo=timezone.utc)

    async with sqlite_session_maker() as session_a:
        first = await supervisor._claim_by_id(session_a, carga_id, now)

    async with sqlite_session_maker() as session_b:
        second = await supervisor._claim_by_id(session_b, carga_id, now)

    assert first == carga_id
    assert second is None

    async with sqlite_session_maker() as session:
        row = (
            await session.execute(sa.select(CargaArchivo).where(CargaArchivo.id == carga_id))
        ).scalar_one()
        assert row.estado == "PROCESANDO"
        # SQLite (a diferencia del Postgres real de Motored) no conserva
        # tzinfo en un DateTime(timezone=True) -- comparamos el valor
        # naive, el punto bajo prueba es QUÉ instante se guardó, no el
        # tzinfo del driver de test.
        assert row.latido_en.replace(tzinfo=timezone.utc) == now


async def test_claim_by_id_does_not_claim_a_row_that_is_not_pendiente(sqlite_session_maker):
    carga_id = uuid.uuid4()
    async with sqlite_session_maker() as session:
        session.add(_make_carga(id=carga_id, estado="VALIDADO"))
        await session.commit()

    async with sqlite_session_maker() as session:
        claimed = await supervisor._claim_by_id(session, carga_id, datetime.now(timezone.utc))

    assert claimed is None


async def test_claim_next_pendiente_returns_id_and_tipo_and_sets_procesando(
    sqlite_session_maker,
):
    carga_id = uuid.uuid4()
    async with sqlite_session_maker() as session:
        # INVENTARIO declara período (ADR-9) -- sin `periodo_desde` este
        # candidato no sería reclamable, ver la sección "ADR-9" más abajo.
        session.add(
            _make_carga(id=carga_id, tipo="INVENTARIO", periodo_desde=date(2026, 9, 15))
        )
        await session.commit()

    async with sqlite_session_maker() as session:
        result = await supervisor.claim_next_pendiente(session)

    assert result == (carga_id, "INVENTARIO")


async def test_claim_next_pendiente_returns_none_when_nothing_is_pendiente(
    sqlite_session_maker,
):
    async with sqlite_session_maker() as session:
        session.add(_make_carga(estado="APLICADO"))
        await session.commit()

    async with sqlite_session_maker() as session:
        result = await supervisor.claim_next_pendiente(session)

    assert result is None


# ---------------------------------------------------------------------------
# ADR-9 — el claim gana un predicado: `tipo` resuelto y, para los tipos que
# declaran período (VENTAS/INVENTARIO/BACKORDER/DEMANDA_PERDIDA),
# `periodo_desde` presente. Ningún estado ni tabla nueva -- ver design
# "Gating: how a load waits for its period (no new state)".
# ---------------------------------------------------------------------------


async def test_claim_next_pendiente_no_reclama_un_tipo_que_declara_sin_periodo(
    sqlite_session_maker,
):
    async with sqlite_session_maker() as session:
        session.add(_make_carga(tipo="VENTAS", periodo_desde=None))
        await session.commit()

    async with sqlite_session_maker() as session:
        result = await supervisor.claim_next_pendiente(session)

    assert result is None


async def test_claim_next_pendiente_reclama_un_tipo_que_no_declara_sin_periodo(
    sqlite_session_maker,
):
    carga_id = uuid.uuid4()
    async with sqlite_session_maker() as session:
        session.add(
            _make_carga(id=carga_id, tipo="FACTURAS_PEDIDOS", periodo_desde=None)
        )
        await session.commit()

    async with sqlite_session_maker() as session:
        result = await supervisor.claim_next_pendiente(session)

    assert result == (carga_id, "FACTURAS_PEDIDOS")


async def test_claim_next_pendiente_no_reclama_un_tipo_sin_resolver(sqlite_session_maker):
    async with sqlite_session_maker() as session:
        session.add(_make_carga(tipo=None, periodo_desde=None))
        await session.commit()

    async with sqlite_session_maker() as session:
        result = await supervisor.claim_next_pendiente(session)

    assert result is None


async def test_claim_next_pendiente_reclama_un_tipo_que_declara_con_periodo_presente(
    sqlite_session_maker,
):
    carga_id = uuid.uuid4()
    async with sqlite_session_maker() as session:
        session.add(
            _make_carga(id=carga_id, tipo="VENTAS", periodo_desde=date(2026, 9, 1))
        )
        await session.commit()

    async with sqlite_session_maker() as session:
        result = await supervisor.claim_next_pendiente(session)

    assert result == (carga_id, "VENTAS")


# ---------------------------------------------------------------------------
# Sweep de heartbeat (ADR-1b) — tabla de decisión, con reloj fijo inyectado.
# ---------------------------------------------------------------------------


async def test_sweep_leaves_a_fresh_heartbeat_untouched(sqlite_session_maker):
    now = datetime(2026, 9, 21, 12, 0, 0, tzinfo=timezone.utc)
    carga_id = uuid.uuid4()
    async with sqlite_session_maker() as session:
        session.add(
            _make_carga(id=carga_id, estado="PROCESANDO", latido_en=now - timedelta(minutes=1))
        )
        await session.commit()

    async with sqlite_session_maker() as session:
        await supervisor.sweep_heartbeats(session, now=now)

    async with sqlite_session_maker() as session:
        row = (
            await session.execute(sa.select(CargaArchivo).where(CargaArchivo.id == carga_id))
        ).scalar_one()
        assert row.estado == "PROCESANDO"


async def test_sweep_transitions_stale_procesando_to_con_errores(sqlite_session_maker):
    now = datetime(2026, 9, 21, 12, 0, 0, tzinfo=timezone.utc)
    carga_id = uuid.uuid4()
    async with sqlite_session_maker() as session:
        session.add(
            _make_carga(id=carga_id, estado="PROCESANDO", latido_en=now - timedelta(minutes=20))
        )
        await session.commit()

    async with sqlite_session_maker() as session:
        await supervisor.sweep_heartbeats(session, now=now)

    async with sqlite_session_maker() as session:
        row = (
            await session.execute(sa.select(CargaArchivo).where(CargaArchivo.id == carga_id))
        ).scalar_one()
        assert row.estado == "CON_ERRORES"


async def test_sweep_transitions_stale_aplicando_back_to_validado(sqlite_session_maker):
    now = datetime(2026, 9, 21, 12, 0, 0, tzinfo=timezone.utc)
    carga_id = uuid.uuid4()
    async with sqlite_session_maker() as session:
        session.add(
            _make_carga(id=carga_id, estado="APLICANDO", latido_en=now - timedelta(minutes=20))
        )
        await session.commit()

    async with sqlite_session_maker() as session:
        await supervisor.sweep_heartbeats(session, now=now)

    async with sqlite_session_maker() as session:
        row = (
            await session.execute(sa.select(CargaArchivo).where(CargaArchivo.id == carga_id))
        ).scalar_one()
        assert row.estado == "VALIDADO"


async def test_sweep_ignores_pendiente_rows_with_no_heartbeat_yet(sqlite_session_maker):
    """Una fila `PENDIENTE` nunca tiene `latido_en` (se setea recién al
    reclamarla) -- el sweep no debe tocarla nunca."""
    now = datetime(2026, 9, 21, 12, 0, 0, tzinfo=timezone.utc)
    carga_id = uuid.uuid4()
    async with sqlite_session_maker() as session:
        session.add(_make_carga(id=carga_id, estado="PENDIENTE", latido_en=None))
        await session.commit()

    async with sqlite_session_maker() as session:
        await supervisor.sweep_heartbeats(session, now=now)

    async with sqlite_session_maker() as session:
        row = (
            await session.execute(sa.select(CargaArchivo).where(CargaArchivo.id == carga_id))
        ).scalar_one()
        assert row.estado == "PENDIENTE"


# ---------------------------------------------------------------------------
# ensure_started() — arranque perezoso e idempotente (ADR-1).
# ---------------------------------------------------------------------------


async def test_ensure_started_does_nothing_when_motored_is_disabled(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", False)

    supervisor.ensure_started()

    assert supervisor._task is None


async def test_ensure_started_is_idempotent(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    # Evita que el tick real pegue contra una URL de base de datos vacía
    # mientras el task queda vivo entre los dos `ensure_started()`.
    monkeypatch.setattr(supervisor, "run_tick", _hang_forever)

    supervisor.ensure_started()
    first_task = supervisor._task
    assert first_task is not None
    assert not first_task.done()

    supervisor.ensure_started()
    second_task = supervisor._task

    assert second_task is first_task


async def _hang_forever():
    await asyncio.Event().wait()


# ---------------------------------------------------------------------------
# SIGTERM — flush de mejor esfuerzo (ADR-1b).
# ---------------------------------------------------------------------------


async def test_run_forever_marks_the_in_flight_carga_as_interrupted_on_cancel(monkeypatch):
    interrupted = []

    async def _fake_mark_interrupted(carga_id):
        interrupted.append(carga_id)

    monkeypatch.setattr(supervisor, "_mark_interrupted", _fake_mark_interrupted)

    in_flight_id = uuid.uuid4()

    async def _hang_with_carga_in_flight():
        supervisor._current_carga_id = in_flight_id
        await asyncio.Event().wait()

    monkeypatch.setattr(supervisor, "run_tick", _hang_with_carga_in_flight)

    task = asyncio.get_event_loop().create_task(supervisor._run_forever())
    await asyncio.sleep(0)  # deja que el tick arranque y quede colgado
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert interrupted == [in_flight_id]


async def test_run_forever_does_not_mark_anything_when_nothing_is_in_flight(monkeypatch):
    interrupted = []

    async def _fake_mark_interrupted(carga_id):
        interrupted.append(carga_id)

    monkeypatch.setattr(supervisor, "_mark_interrupted", _fake_mark_interrupted)
    monkeypatch.setattr(supervisor, "run_tick", _hang_forever)

    task = asyncio.get_event_loop().create_task(supervisor._run_forever())
    await asyncio.sleep(0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert interrupted == []


# ---------------------------------------------------------------------------
# Fase 12 "Retention Purge" (ADR-3) — run_tick invoca el due-check de
# retención en la MISMA sesión, después del sweep+claim. Ningún mecanismo
# nuevo: el propio tick del supervisor es lo que la hace correr.
# ---------------------------------------------------------------------------


async def test_run_tick_invoca_el_due_check_de_retencion_con_la_sesion_del_tick(
    sqlite_session_maker, monkeypatch
):
    llamadas = []

    async def _fake_ejecutar_si_corresponde(session, now=None):
        llamadas.append(session)
        return None

    monkeypatch.setattr(retencion, "ejecutar_si_corresponde", _fake_ejecutar_si_corresponde)

    await supervisor.run_tick()

    assert len(llamadas) == 1


# ---------------------------------------------------------------------------
# POOL_INGESTA — thread pool dedicado (ADR-1).
# ---------------------------------------------------------------------------


def test_pool_ingesta_is_a_dedicated_single_worker_pool():
    assert supervisor.POOL_INGESTA._max_workers == 1


async def test_dispatch_leaves_current_carga_id_set_when_cancelled_mid_handler(monkeypatch):
    """Real bug found in review: `_dispatch`'s original `finally: _current_
    carga_id = None` ran to completion BEFORE a CancelledError raised
    inside `handler` could reach `_run_forever`'s outer handler -- so the
    SIGTERM flush's `if _current_carga_id is not None` check always saw
    `None`, even though a job WAS genuinely in flight. This drives
    `_dispatch` directly (not a mocked `run_tick`, unlike the tests above)
    so the real `try/except/else` structure is what's under test, not a
    stand-in for it."""
    carga_id = uuid.uuid4()

    async def _hanging_handler(_carga_id):
        await asyncio.Event().wait()

    jobs.JOB_HANDLERS["VENTAS_HANG_TEST"] = _hanging_handler

    task = asyncio.get_event_loop().create_task(
        supervisor._dispatch(carga_id, "VENTAS_HANG_TEST")
    )
    await asyncio.sleep(0)  # let _dispatch set _current_carga_id and await the handler
    assert supervisor._current_carga_id == carga_id

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # The whole point of the fix: _current_carga_id must STILL be set after
    # the cancellation propagates out of _dispatch, so _run_forever's outer
    # handler can see it and call _mark_interrupted.
    assert supervisor._current_carga_id == carga_id


async def test_dispatch_clears_current_carga_id_on_successful_completion(monkeypatch):
    carga_id = uuid.uuid4()

    async def _quick_handler(_carga_id):
        return None

    jobs.JOB_HANDLERS["VENTAS_QUICK_TEST"] = _quick_handler

    await supervisor._dispatch(carga_id, "VENTAS_QUICK_TEST")

    assert supervisor._current_carga_id is None


async def test_run_forever_marks_interrupted_via_the_real_dispatch_path(monkeypatch):
    """End-to-end regression for the bug above, through the REAL run_tick
    (not a mock of it): a claimed carga_archivo whose handler hangs, then
    the whole supervisor task is cancelled -- the flush must fire."""
    interrupted = []

    async def _fake_mark_interrupted(cid):
        interrupted.append(cid)

    monkeypatch.setattr(supervisor, "_mark_interrupted", _fake_mark_interrupted)

    carga_id = uuid.uuid4()

    async def _fake_run_tick():
        await supervisor._dispatch(carga_id, "VENTAS_E2E_HANG")

    async def _hanging_handler(_carga_id):
        await asyncio.Event().wait()

    jobs.JOB_HANDLERS["VENTAS_E2E_HANG"] = _hanging_handler
    monkeypatch.setattr(supervisor, "run_tick", _fake_run_tick)

    task = asyncio.get_event_loop().create_task(supervisor._run_forever())
    await asyncio.sleep(0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert interrupted == [carga_id]
