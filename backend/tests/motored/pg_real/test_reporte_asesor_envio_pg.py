"""
reporte_asesor_envio against a real Postgres (opt-in, `MOTORED_TEST_PG_URL`,
database migrated to head; odd/motored-reporte-diario-asesor, T3b).

- The partial unique index lets the automatic send go out once per asesor
  and data date; resends and failures may repeat.
- The migration's downgrade and upgrade run inside a rolled-back
  transaction.
- The advisory lock: a second connection cannot take it while the first
  holds it.
- One end-to-end tick on the hand-computed world of the asesor detail
  (year 2097), with Telegram faked: every session joins one outer
  transaction through savepoints, so the per-send commits are real and the
  whole test still rolls back. On one connection the lock session's
  savepoint would roll the work back when it closes, so the e2e tests
  replace the lock by a no-op (the lock has its own test above).
"""
import datetime
import importlib.util
import os
import uuid
from datetime import date, timezone
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine,
)

from app.config import settings
from app.motored.models.parametro_metodologia import ParametroMetodologia
from app.motored.models.reporte_asesor_envio import ReporteAsesorEnvio
from app.motored.models.reporte_asesor_link import ReporteAsesorLink
from app.motored.models.usuario import MotoredRole, Usuario
from app.motored.services import avisos_telegram
from app.motored.services import reporte_asesor_envio as envio
from app.motored.services.trabajos import supervisor_reporte_asesor as sup
from tests.motored.pg_real.test_tablero_asesor_detalle_pg import Mundo

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

_MIGRACIONES = (
    Path(__file__).resolve().parents[3] / "alembic_motored" / "versions")
FECHA = date(2097, 3, 20)
# 2097-03-21 07:00 in Bogotá: after the minimum hour, before the deadline.
AHORA = datetime.datetime(2097, 3, 21, 12, tzinfo=timezone.utc)


@pytest.fixture
async def sesion():
    motor = create_async_engine(URL)
    async with AsyncSession(motor, expire_on_commit=False) as db:
        yield db
        await db.rollback()
    await motor.dispose()


@pytest.fixture
async def fabrica():
    """Sessions that commit to savepoints of one outer transaction."""
    motor = create_async_engine(URL)
    conexion = await motor.connect()
    externa = await conexion.begin()
    yield async_sessionmaker(
        bind=conexion, expire_on_commit=False,
        join_transaction_mode="create_savepoint")
    await externa.rollback()
    await conexion.close()
    await motor.dispose()


def _asesor(cedula=None, nombre=None):
    return Usuario(
        id=uuid.uuid4(), nombre=nombre or f"Asesor {uuid.uuid4().hex[:6]}",
        role=MotoredRole.ASESOR_MOSTRADOR, activo=True, status="approved",
        cedula=cedula or str(uuid.uuid4().int)[:12], cedula_aprobada=True,
        telegram_id=int(str(uuid.uuid4().int)[:9]))


def _fila(usuario, estado=envio.ENVIADO, reenvio=False):
    return ReporteAsesorEnvio(
        id=uuid.uuid4(), usuario_id=usuario.id, cedula=usuario.cedula,
        fecha_datos=FECHA, enviado_en=AHORA, estado=estado,
        detalle=None, reenvio=reenvio)


async def _usuario(sesion):
    usuario = _asesor()
    sesion.add(usuario)
    await sesion.flush()
    return usuario


async def test_the_partial_unique_index_definition(sesion):
    definicion = (await sesion.execute(text(
        "SELECT indexdef FROM pg_indexes "
        "WHERE indexname = 'uq_reporte_asesor_envio_diario'"))).scalar_one()

    assert "UNIQUE" in definicion
    assert "(usuario_id, fecha_datos)" in definicion
    assert "NOT reenvio" in definicion
    assert "'enviado'" in definicion


async def test_the_automatic_send_goes_out_once_per_date(sesion):
    usuario = await _usuario(sesion)
    sesion.add_all([_fila(usuario), _fila(usuario)])

    with pytest.raises(
            IntegrityError, match="uq_reporte_asesor_envio_diario"):
        await sesion.flush()


async def test_resends_and_failures_may_repeat(sesion):
    usuario = await _usuario(sesion)
    sesion.add_all([
        _fila(usuario),
        _fila(usuario, reenvio=True), _fila(usuario, reenvio=True),
        _fila(usuario, envio.FALLIDO), _fila(usuario, envio.FALLIDO),
        _fila(usuario, envio.BLOQUEADO),
    ])

    await sesion.flush()


async def test_an_unknown_estado_is_refused(sesion):
    usuario = await _usuario(sesion)
    sesion.add(_fila(usuario, estado="perdido"))

    with pytest.raises(IntegrityError, match="ck_reporte_asesor_envio_estado"):
        await sesion.flush()


async def test_deleting_the_usuario_cascades(sesion):
    usuario = await _usuario(sesion)
    sesion.add(_fila(usuario))
    await sesion.flush()

    await sesion.execute(
        text("DELETE FROM usuario WHERE id = :id"), {"id": usuario.id})

    restantes = await sesion.execute(
        select(ReporteAsesorEnvio).where(
            ReporteAsesorEnvio.usuario_id == usuario.id))
    assert restantes.scalars().all() == []


def _migracion():
    archivo = next(_MIGRACIONES.glob("*_reporte_asesor_envio.py"))
    spec = importlib.util.spec_from_file_location("envio_mig", archivo)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _bajar_y_subir(conexion_sync):
    modulo = _migracion()
    contexto = MigrationContext.configure(conexion_sync)
    with Operations.context(contexto):
        modulo.downgrade()
        existe_tras_bajar = conexion_sync.execute(text(
            "SELECT to_regclass('reporte_asesor_envio')")).scalar()
        modulo.upgrade()
    existe_tras_subir = conexion_sync.execute(text(
        "SELECT to_regclass('reporte_asesor_envio')")).scalar()
    return existe_tras_bajar, existe_tras_subir


async def test_the_migration_downgrades_and_upgrades():
    motor = create_async_engine(URL)
    async with motor.connect() as conexion:
        transaccion = await conexion.begin()
        bajada, subida = await conexion.run_sync(_bajar_y_subir)
        await transaccion.rollback()
    await motor.dispose()

    assert bajada is None
    assert subida is not None


async def test_the_send_lock_is_exclusive_between_connections():
    motor = create_async_engine(URL)
    fabrica = async_sessionmaker(motor, expire_on_commit=False)
    async with fabrica() as uno, fabrica() as otro:
        assert await envio.tomar_candado(uno, envio.LOCK_ENVIO) is True
        assert await envio.tomar_candado(otro, envio.LOCK_ENVIO) is False
        assert await envio.esperar_candado(
            otro, envio.LOCK_ENVIO, 1) is False
        await otro.rollback()
        await uno.rollback()
        assert await envio.tomar_candado(otro, envio.LOCK_ENVIO) is True
        await otro.rollback()
    await motor.dispose()


# --- end-to-end tick ------------------------------------------------------

async def _sembrar(fabrica):
    async with fabrica() as db:
        mundo = await Mundo().crear(db)
        mundo.carga.periodo_hasta = FECHA
        ana = _asesor(mundo.cedulas["ana"], "Ana Pérez")
        beto = _asesor(mundo.cedulas["beto"], "Beto Ruiz")
        sin_link = _asesor(mundo.cedulas["cami"], "Cami Sin Enlace")
        db.add_all([ana, beto, sin_link])
        await db.flush()
        db.add_all([
            ReporteAsesorLink(
                id=uuid.uuid4(), usuario_id=u.id, cedula=u.cedula,
                token=uuid.uuid4().hex + uuid.uuid4().hex)
            for u in (ana, beto)])
        db.add(ParametroMetodologia(
            id=uuid.uuid4(), clave=envio.CLAVE_ACTIVO, valor=True,
            vigente_desde=date(2097, 3, 1)))
        await db.commit()
    return ana, beto, sin_link


@pytest.fixture
def telegram_falso(monkeypatch):
    monkeypatch.setattr(settings, "LORE_BOT_TOKEN", "1:tok-pg")
    monkeypatch.setattr(settings, "MOTORED_PUBLIC_URL", "https://m.co")
    monkeypatch.setattr(settings, "MOTORED_KPI_RESUMEN_ENABLED", False)
    mensajes = []

    async def enviar_mensaje(token, chat_id, texto, cliente=None):
        mensajes.append((chat_id, texto))
        return True

    monkeypatch.setattr(avisos_telegram, "enviar_mensaje", enviar_mensaje)

    async def tomar(db, clave):
        return True

    async def esperar(db, clave, segundos):
        return True

    monkeypatch.setattr(envio, "tomar_candado", tomar)
    monkeypatch.setattr(envio, "esperar_candado", esperar)
    return mensajes


async def _sin_pausa(_):
    return None


async def _ledger(fabrica):
    async with fabrica() as db:
        filas = await db.execute(select(ReporteAsesorEnvio))
        return filas.scalars().all()


async def test_a_tick_sends_once_per_asesor_and_date(
        fabrica, telegram_falso):
    ana, beto, sin_link = await _sembrar(fabrica)

    primero = await sup.run_tick(
        session_factory=fabrica, ahora=AHORA, dormir=_sin_pausa)
    segundo = await sup.run_tick(
        session_factory=fabrica, ahora=AHORA, dormir=_sin_pausa)

    assert primero == envio.Conteo(enviados=2)
    assert segundo is None
    assert {c for c, _ in telegram_falso} == {
        ana.telegram_id, beto.telegram_id}
    texto_ana = dict(telegram_falso)[ana.telegram_id]
    assert texto_ana.startswith(
        "Hola Ana Pérez, tu informe con ventas al 20/03/2097: "
        "cumplimiento 87,5%")
    assert "https://m.co/motored/informe/" in texto_ana
    filas = await _ledger(fabrica)
    propias = [f for f in filas if f.usuario_id in {ana.id, beto.id}]
    assert len(propias) == 2
    assert all(f.estado == envio.ENVIADO and not f.reenvio
               for f in propias)
    assert all(f.fecha_datos == FECHA for f in propias)
    assert sin_link.id not in {f.usuario_id for f in filas}


async def test_the_resend_bypasses_the_daily_rule(fabrica, telegram_falso):
    ana, beto, _ = await _sembrar(fabrica)
    await sup.run_tick(
        session_factory=fabrica, ahora=AHORA, dormir=_sin_pausa)
    admin = _asesor()
    async with fabrica() as db:
        db.add(admin)
        await db.commit()
        destinos = await envio.preparar_destinos(db, FECHA)

    conteo = await sup.ejecutar_reenvio(
        destinos, FECHA, admin.id, session_factory=fabrica,
        dormir=_sin_pausa)

    assert conteo == envio.Conteo(enviados=2)
    assert len(telegram_falso) == 4
    reenvios = [f for f in await _ledger(fabrica) if f.reenvio]
    assert {f.usuario_id for f in reenvios} == {ana.id, beto.id}
    assert all(f.solicitado_por == admin.id for f in reenvios)


async def test_estado_lists_the_skipped_asesores(fabrica, telegram_falso):
    await _sembrar(fabrica)
    await sup.run_tick(
        session_factory=fabrica, ahora=AHORA, dormir=_sin_pausa)

    async with fabrica() as db:
        estado = await envio.estado_envio(db, date(2097, 3, 21))

    assert estado["envio_activo"] is True
    assert estado["ultimo_envio"]["fecha_datos"] == FECHA.isoformat()
    assert estado["ultimo_envio"]["enviados"] == 2
    assert estado["fecha_disponible"] == FECHA.isoformat()
    assert estado["elegibles"] == 2
    assert estado["sin_enlace"] == ["Cami Sin Enlace"]
    assert "token" not in str(estado)
