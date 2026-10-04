"""
Motored Pedidos F3 "Motor", S6b (sdd/motored-pedidos-motor, tasks S6b-6/
S6b-8): el job de corridas contra un Postgres real (opt-in).

Corre sólo con `MOTORED_TEST_PG_URL` (`postgresql+asyncpg://...`) apuntando a
una base ya migrada con `alembic -c alembic_motored.ini upgrade head`. El
test de la tabla ausente necesita además `MOTORED_TEST_PG_URL_SIN_TABLA`:
una base VACÍA (sin migrar).

Casi todo trabaja sobre una única conexión dentro de una transacción que se
revierte al final (`join_transaction_mode="create_savepoint"`: cada commit
del job sólo libera un savepoint). Las pruebas de concurrencia necesitan
conexiones distintas y filas confirmadas: siembran sólo un proveedor y sus
corridas y las borran al terminar.
"""
import asyncio
import datetime
import logging
import os
import threading
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
from app.motored import database as motored_database
from app.motored.models.corrida import Corrida
from app.motored.models.corrida_linea import CorridaLinea
from app.motored.models.corrida_sucursal import CorridaSucursal
from app.motored.models.parametro_metodologia import (
    ParametroMetodologia,
)
from app.motored.models.proveedor import Proveedor
from app.motored.models.retencion_ejecucion import RetencionEjecucion
from app.motored.services.corridas import ejecucion as ej
from app.motored.services.corridas import retencion_corridas as rc
from app.motored.services.corridas import servicio as sv
from app.motored.services.trabajos import supervisor_corridas as sc
from tests.motored.pg_real.test_corrida_pg import CORTE, _sembrar

URL = os.environ.get("MOTORED_TEST_PG_URL")
URL_SIN_TABLA = os.environ.get("MOTORED_TEST_PG_URL_SIN_TABLA")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

UTC = datetime.timezone.utc


class Muerte(BaseException):
    """Simula un proceso que muere sin cleanup (ni `except Exception`)."""


class Dormir:
    def __init__(self, cortar_en):
        self.esperas = []
        self.cortar_en = cortar_en

    async def __call__(self, segundos):
        self.esperas.append(segundos)
        if len(self.esperas) >= self.cortar_en:
            raise asyncio.CancelledError


def _mas(minutos=0, segundos=0):
    """Reloj que marca "ahora" + un desplazamiento."""
    delta = datetime.timedelta(minutes=minutos, seconds=segundos)
    return lambda: ej.ahora_utc() + delta


# --- Una conexión con rollback final -----------------------------------------


@pytest.fixture
async def fabrica():
    motor = create_async_engine(URL)
    async with motor.connect() as conexion:
        transaccion = await conexion.begin()
        yield async_sessionmaker(
            bind=conexion, class_=AsyncSession, expire_on_commit=False,
            autoflush=False, join_transaction_mode="create_savepoint")
        await transaccion.rollback()
    await motor.dispose()


@pytest.fixture
async def escenario(fabrica):
    """Datos sintéticos de S6a y una corrida PENDIENTE recién creada."""
    async with fabrica() as db:
        datos = await _sembrar(db)
        corrida = await sv.crear_corrida(db, fecha_corte=CORTE, hoy=CORTE)
        await db.commit()
    return SimpleNamespace(
        fabrica=fabrica, datos=datos, corrida_id=corrida.id)


async def _corrida(fabrica, corrida_id):
    async with fabrica() as db:
        resultado = await db.execute(
            select(Corrida).where(Corrida.id == corrida_id)
            .execution_options(populate_existing=True))
        return resultado.scalars().one()


async def _estados_sucursal(fabrica, corrida_id):
    async with fabrica() as db:
        filas = await db.execute(
            select(CorridaSucursal.estado)
            .where(CorridaSucursal.corrida_id == corrida_id)
            .order_by(CorridaSucursal.orden))
        return list(filas.scalars().all())


async def _cantidad_lineas(fabrica, corrida_id):
    async with fabrica() as db:
        filas = await db.execute(
            select(CorridaLinea.sucursal_id, CorridaLinea.referencia_id)
            .where(CorridaLinea.corrida_id == corrida_id))
        return filas.all()


# --- El loop reclama una PENDIENTE y la completa -----------------------------


async def test_a_tick_claims_a_pending_corrida_and_completes_it(escenario):
    resultado = await sc.run_tick(session_factory=escenario.fabrica)

    corrida = await _corrida(escenario.fabrica, escenario.corrida_id)
    assert resultado == escenario.corrida_id
    assert corrida.estado == "BORRADOR"
    assert corrida.intentos == 1
    assert corrida.sucursales_procesadas == 3
    assert corrida.terminado_en is not None
    assert [e["evento"] for e in corrida.log] == ["CREADA", "FINALIZADA"]
    assert await _estados_sucursal(
        escenario.fabrica, escenario.corrida_id) == ["OK", "OMITIDA", "OK"]


async def test_the_completed_corrida_has_the_pattern_row(escenario):
    await sc.run_tick(session_factory=escenario.fabrica)

    async with escenario.fabrica() as db:
        filas = await db.execute(
            select(CorridaLinea).where(
                CorridaLinea.corrida_id == escenario.corrida_id,
                CorridaLinea.sucursal_id == escenario.datos.uno.id))
        (linea,) = filas.scalars().all()
    assert linea.demanda_ponderada == Decimal("85.428571")
    assert linea.pedido_sugerido == Decimal("53.00")


async def test_a_second_tick_finds_nothing_left_to_claim(escenario):
    await sc.run_tick(session_factory=escenario.fabrica)

    assert await sc.run_tick(session_factory=escenario.fabrica) is None


async def test_the_compute_ran_in_the_shared_thread_pool(
        escenario, monkeypatch):
    hilos = []
    original = sv.calcular_sucursal

    def _anotar(*args):
        hilos.append(threading.current_thread().name)
        return original(*args)

    monkeypatch.setattr(sv, "calcular_sucursal", _anotar)

    await sc.run_tick(session_factory=escenario.fabrica)

    assert len(hilos) == 3
    assert all(h.startswith("motored-ingesta") for h in hilos)
    assert threading.current_thread().name not in hilos


# --- Reanudar tras una caída -------------------------------------------------


async def test_a_crashed_run_is_swept_and_resumed_without_duplicates(
        escenario, monkeypatch):
    original = sv.procesar_sucursal
    procesadas = []

    async def _muere_en_la_segunda(db, corrida, sucursal_id, *resto):
        if len(procesadas) == 1:
            raise Muerte
        procesadas.append(sucursal_id)
        return await original(db, corrida, sucursal_id, *resto)

    monkeypatch.setattr(sv, "procesar_sucursal", _muere_en_la_segunda)
    with pytest.raises(Muerte):
        await sc.run_tick(session_factory=escenario.fabrica)
    tras_la_caida = await _corrida(escenario.fabrica, escenario.corrida_id)
    assert tras_la_caida.estado == "CALCULANDO"
    assert await _estados_sucursal(
        escenario.fabrica, escenario.corrida_id) == [
            "OK", "PENDIENTE", "PENDIENTE"]
    monkeypatch.setattr(sv, "procesar_sucursal", original)

    sin_vencer = await sc.run_tick(
        session_factory=escenario.fabrica, reloj=_mas(minutos=5))
    assert sin_vencer is None
    barrida = await sc.run_tick(
        session_factory=escenario.fabrica, reloj=_mas(minutos=11))
    assert barrida is None
    corrida = await _corrida(escenario.fabrica, escenario.corrida_id)
    assert corrida.estado == "PENDIENTE"
    assert corrida.reintentar_despues_de is not None

    retomada = await sc.run_tick(
        session_factory=escenario.fabrica, reloj=_mas(minutos=12))

    assert retomada == escenario.corrida_id
    corrida = await _corrida(escenario.fabrica, escenario.corrida_id)
    assert corrida.estado == "BORRADOR" and corrida.intentos == 2
    lineas = await _cantidad_lineas(escenario.fabrica, escenario.corrida_id)
    assert len(lineas) == len(set(lineas))
    assert await _estados_sucursal(
        escenario.fabrica, escenario.corrida_id) == ["OK", "OMITIDA", "OK"]


async def test_a_preparation_that_keeps_failing_ends_fallida_e031(escenario):
    async with escenario.fabrica() as db:
        await db.execute(
            text("UPDATE corrida SET parametros_snapshot = '{}'::jsonb "
                 "WHERE id = :id"), {"id": escenario.corrida_id})
        await db.commit()

    primera = await sc.run_tick(
        session_factory=escenario.fabrica, reloj=_mas())
    corrida = await _corrida(escenario.fabrica, escenario.corrida_id)
    assert primera == escenario.corrida_id
    assert corrida.estado == "PENDIENTE" and corrida.intentos == 1

    demasiado_pronto = await sc.run_tick(
        session_factory=escenario.fabrica, reloj=_mas(segundos=10))
    assert demasiado_pronto is None

    await sc.run_tick(
        session_factory=escenario.fabrica, reloj=_mas(segundos=40))
    corrida = await _corrida(escenario.fabrica, escenario.corrida_id)
    assert corrida.estado == "PENDIENTE" and corrida.intentos == 2

    await sc.run_tick(
        session_factory=escenario.fabrica, reloj=_mas(segundos=200))
    corrida = await _corrida(escenario.fabrica, escenario.corrida_id)
    assert corrida.estado == "FALLIDA" and corrida.intentos == 3
    assert corrida.log[-1]["codigo"] == "E-CORRIDA-031"


# --- Concurrencia: dos claimers nunca toman la misma -------------------------


@pytest.fixture
async def comprometida():
    """Proveedor y 12 corridas PENDIENTE CONFIRMADAS (se borran al final)."""
    motor = create_async_engine(URL)
    maker = async_sessionmaker(motor, expire_on_commit=False, autoflush=False)
    sufijo = uuid.uuid4().hex[:6]
    proveedor = Proveedor(
        id=uuid.uuid4(), codigo=f"CLAIM-{sufijo}", nombre="claim",
        es_principal=False, dias_empaque_default=1, dias_transito_default=1,
        dias_seguridad_default=Decimal("1"))
    base = datetime.datetime(2020, 1, 1)
    corridas = [
        Corrida(
            id=uuid.uuid4(), codigo=f"TST-{sufijo}-{n:02d}",
            proveedor_id=proveedor.id, fecha_corte=CORTE, estado="PENDIENTE",
            created_at=base + datetime.timedelta(minutes=n))
        for n in range(12)]
    async with maker() as db:
        db.add(proveedor)
        await db.flush()
        db.add_all(corridas)
        await db.commit()
    yield SimpleNamespace(maker=maker, ids=[c.id for c in corridas])
    async with maker() as db:
        await db.execute(delete(Corrida).where(
            Corrida.id.in_([c.id for c in corridas])))
        await db.execute(delete(Proveedor).where(
            Proveedor.id == proveedor.id))
        await db.commit()
    await motor.dispose()


async def _reclamar_todo(maker, barrera):
    tomadas = []
    await barrera.wait()
    while True:
        async with maker() as db:
            corrida_id = await ej.reclamar_siguiente(db, ej.ahora_utc())
        if corrida_id is None:
            return tomadas
        tomadas.append(corrida_id)


async def test_concurrent_claimers_never_take_the_same_corrida(comprometida):
    barrera = asyncio.Barrier(6)

    resultados = await asyncio.gather(*[
        _reclamar_todo(comprometida.maker, barrera) for _ in range(6)])

    tomadas = [i for lote in resultados for i in lote]
    mias = [i for i in tomadas if i in set(comprometida.ids)]
    assert len(mias) == len(set(mias)) == 12
    async with comprometida.maker() as db:
        filas = await db.execute(
            select(Corrida.estado, Corrida.intentos)
            .where(Corrida.id.in_(comprometida.ids)))
        assert set(filas.all()) == {("CALCULANDO", 1)}


async def test_a_claimer_skips_the_row_another_claimer_has_locked(
        comprometida):
    async with comprometida.maker() as bloqueadora:
        (primera,) = (await bloqueadora.execute(
            select(Corrida.id)
            .where(Corrida.id.in_(comprometida.ids))
            .order_by(Corrida.created_at).limit(1)
            .with_for_update())).scalars().all()
        async with comprometida.maker() as db:
            reclamada = await asyncio.wait_for(
                ej.reclamar_siguiente(db, ej.ahora_utc()), timeout=5)
        await bloqueadora.rollback()

    assert reclamada is not None and reclamada != primera


async def test_a_claim_never_touches_carga_archivo(comprometida):
    async with comprometida.maker() as db:
        antes = (await db.execute(
            text("SELECT count(*) FROM carga_archivo"))).scalar_one()
        await ej.reclamar_siguiente(db, ej.ahora_utc())
        despues = (await db.execute(
            text("SELECT count(*) FROM carga_archivo"))).scalar_one()
    assert antes == despues


# --- Barrido sobre Postgres real ---------------------------------------------


async def _corrida_calculando(db, proveedor_id, *, latido, intentos):
    corrida = Corrida(
        id=uuid.uuid4(), codigo=f"SW-{uuid.uuid4().hex[:8]}",
        proveedor_id=proveedor_id, fecha_corte=CORTE, estado="CALCULANDO",
        latido_en=latido, intentos=intentos)
    db.add(corrida)
    await db.flush()
    return corrida.id


async def _proveedor(db):
    proveedor = Proveedor(
        id=uuid.uuid4(), codigo=f"SW-{uuid.uuid4().hex[:6]}", nombre="sw",
        es_principal=False, dias_empaque_default=1, dias_transito_default=1,
        dias_seguridad_default=Decimal("1"))
    db.add(proveedor)
    await db.flush()
    return proveedor.id


async def test_the_sweep_recovers_only_the_stuck_corridas(fabrica):
    ahora = ej.ahora_utc()
    async with fabrica() as db:
        proveedor_id = await _proveedor(db)
        vieja = ahora - datetime.timedelta(minutes=11)
        una = await _corrida_calculando(
            db, proveedor_id, latido=vieja, intentos=1)
        agotada = await _corrida_calculando(
            db, proveedor_id, latido=vieja, intentos=3)
        viva = await _corrida_calculando(
            db, proveedor_id, latido=ahora, intentos=1)
        await db.commit()

    async with fabrica() as db:
        movidas = await ej.barrer_estancadas(
            db, ahora, timeout_min=10, max_intentos=3)

    assert dict(movidas) == {una: "PENDIENTE", agotada: "FALLIDA"}
    reintenta = await _corrida(fabrica, una)
    assert reintenta.reintentar_despues_de == ahora + datetime.timedelta(
        seconds=30)
    assert (await _corrida(fabrica, agotada)).terminado_en is not None
    assert (await _corrida(fabrica, viva)).estado == "CALCULANDO"


async def test_a_swept_corrida_waits_for_its_backoff_before_a_new_claim(
        fabrica):
    ahora = ej.ahora_utc()
    async with fabrica() as db:
        proveedor_id = await _proveedor(db)
        corrida_id = await _corrida_calculando(
            db, proveedor_id, latido=ahora - datetime.timedelta(minutes=11),
            intentos=1)
        await db.commit()
    async with fabrica() as db:
        await ej.barrer_estancadas(db, ahora, timeout_min=10, max_intentos=3)

    async with fabrica() as db:
        pronto = await ej.reclamar_siguiente(
            db, ahora + datetime.timedelta(seconds=10))
    async with fabrica() as db:
        despues = await ej.reclamar_siguiente(
            db, ahora + datetime.timedelta(seconds=31))

    assert pronto is None
    assert despues == corrida_id
    reclamada = await _corrida(fabrica, corrida_id)
    assert reclamada.intentos == 2
    assert reclamada.reintentar_despues_de is None


async def test_the_sweep_skips_a_corrida_a_live_worker_has_locked(
        comprometida):
    ahora = ej.ahora_utc()
    async with comprometida.maker() as db:
        proveedor_id = (await db.execute(
            select(Corrida.proveedor_id)
            .where(Corrida.id == comprometida.ids[0]))).scalar_one()
        estancada = await _corrida_calculando(
            db, proveedor_id, latido=ahora - datetime.timedelta(minutes=30),
            intentos=1)
        await db.commit()
    try:
        async with comprometida.maker() as trabajadora:
            await trabajadora.execute(
                select(Corrida.id).where(Corrida.id == estancada)
                .with_for_update())
            async with comprometida.maker() as db:
                movidas = await asyncio.wait_for(
                    ej.barrer_estancadas(
                        db, ahora, timeout_min=10, max_intentos=3),
                    timeout=5)
            await trabajadora.rollback()
        assert [i for i, _ in movidas if i == estancada] == []
        async with comprometida.maker() as db:
            liberada = await ej.barrer_estancadas(
                db, ahora, timeout_min=10, max_intentos=3)
        assert dict(liberada)[estancada] == "PENDIENTE"
    finally:
        async with comprometida.maker() as db:
            await db.execute(delete(Corrida).where(Corrida.id == estancada))
            await db.commit()


# --- Retención sobre Postgres real -------------------------------------------


async def _sin_estado_de_retencion(db):
    """La purga debe decidir por el respaldo de entorno, no por filas
    `retencion_*` ni por un ledger de hoy que dejó otra corrida en una base
    reutilizada. El borrado vive en la transacción del test: se revierte."""
    await db.execute(delete(ParametroMetodologia).where(
        ParametroMetodologia.clave.startswith(
            "retencion_", autoescape=True)))
    await db.execute(delete(RetencionEjecucion).where(
        RetencionEjecucion.tabla == rc.TABLA_CORRIDA))


async def test_the_retention_purges_only_old_annulled_failed_or_draft(
        fabrica, monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_CORRIDA_RETENCION_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_CORRIDA_RETENCION_DIAS", 45)
    ahora = ej.ahora_utc()
    vieja = (ahora - datetime.timedelta(days=60)).replace(tzinfo=None)
    reciente = (ahora - datetime.timedelta(days=5)).replace(tzinfo=None)
    async with fabrica() as db:
        await _sin_estado_de_retencion(db)
        proveedor_id = await _proveedor(db)
        ids = {}
        for estado, creada in [
                ("ANULADA", vieja), ("FALLIDA", vieja), ("BORRADOR", vieja),
                ("CERRADA", vieja), ("PENDIENTE", vieja),
                ("ANULADA", reciente)]:
            corrida = Corrida(
                id=uuid.uuid4(), codigo=f"RT-{uuid.uuid4().hex[:8]}",
                proveedor_id=proveedor_id, fecha_corte=CORTE, estado=estado,
                created_at=creada)
            db.add(corrida)
            ids[(estado, creada is vieja)] = corrida.id
        await db.commit()

    async with fabrica() as db:
        borradas = await rc.ejecutar_si_corresponde(db, ahora, tamano=2)
    async with fabrica() as db:
        vivas = set((await db.execute(
            select(Corrida.id).where(Corrida.id.in_(list(ids.values())))
        )).scalars().all())

    assert borradas == 3
    assert vivas == {
        ids[("CERRADA", True)], ids[("PENDIENTE", True)],
        ids[("ANULADA", False)]}


# --- S6b-8: la tabla `corrida` no existe -------------------------------------


@pytest.fixture
async def base_sin_tabla(monkeypatch):
    if not URL_SIN_TABLA:
        pytest.skip("MOTORED_TEST_PG_URL_SIN_TABLA no definida")
    monkeypatch.setattr(settings, "MOTORED_DATABASE_URL", URL_SIN_TABLA)
    motored_database.get_motored_engine.cache_clear()
    yield
    await motored_database.get_motored_engine().dispose()
    motored_database.get_motored_engine.cache_clear()


async def test_the_real_driver_error_is_recognised_as_a_missing_table(
        base_sin_tabla):
    with pytest.raises(Exception) as error:
        await sc.run_tick()

    assert sc.es_tabla_ausente(error.value) is True


async def test_the_loop_idles_on_a_database_without_the_corrida_table(
        base_sin_tabla, monkeypatch, caplog):
    monkeypatch.setattr(sc, "_aviso_tabla_ausente", False)
    dormir = Dormir(cortar_en=3)

    with caplog.at_level(logging.INFO, logger=sc.logger.name):
        with pytest.raises(asyncio.CancelledError):
            await sc._run_forever(dormir=dormir)

    avisos = [r for r in caplog.records if r.levelno == logging.WARNING]
    errores = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(avisos) == 1 and errores == []
    assert dormir.esperas == [sc.ESPERA_SIN_TABLA_SEGUNDOS] * 3
