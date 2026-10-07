"""
Public asesor report against a real Postgres (opt-in, `MOTORED_TEST_PG_URL`,
database migrated to head; odd/motored-reporte-diario-asesor, T3b).

Runs the real route inside one outer transaction that is rolled back, with
sessions in savepoint mode: a `commit()` in the route releases a savepoint,
so the lock counter is visible to the NEXT request (proving it was committed
before the 401) while nothing survives the test.

World: the 2097 asesores of `test_tablero_asesor_detalle_pg` (2097 is the
latest year with sales, so "year to date" is 2097-01..2097-03).
"""
import datetime
import json
import uuid

import httpx
import pytest
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.main import app
from app.motored.database import get_motored_db
from app.motored.models.reporte_asesor_link import ReporteAsesorLink
from app.motored.models.usuario import MotoredRole, Usuario
from app.motored.services import tablero_asesores_consultas as q
from app.motored.services import tablero_kpis as k
from app.motored.services.trabajos import supervisor
from tests.motored.pg_real.test_tablero_asesor_detalle_pg import MESES, Mundo
from tests.motored.pg_real.test_tablero_asesores_pg import URL, pytestmark  # noqa: F401

CIEN = "Enlace o cédula no válidos."


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


@pytest.fixture(autouse=True)
def _app_lista(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "informe-pg-motored")
    monkeypatch.setattr(settings, "SECRET_KEY", "informe-pg-asc360")
    monkeypatch.setattr(settings, "SONIA_BOT_SECRET", "informe-pg-sonia")
    monkeypatch.setattr(supervisor, "ensure_started", lambda: None)
    yield
    app.dependency_overrides.clear()


@pytest.fixture
async def escenario(fabrica):
    async with fabrica() as db:
        mundo = await Mundo().crear(db)
        usuario = Usuario(
            id=uuid.uuid4(), nombre=f"Ana {mundo.sfx}",
            role=MotoredRole.ASESOR_MOSTRADOR, activo=True, status="approved",
            cedula=mundo.cedulas["ana"], cedula_aprobada=True,
            telegram_id=int(str(uuid.uuid4().int)[:9]))
        db.add(usuario)
        await db.flush()
        link = ReporteAsesorLink(
            id=uuid.uuid4(), usuario_id=usuario.id, cedula=usuario.cedula,
            token=uuid.uuid4().hex + uuid.uuid4().hex)
        db.add(link)
        await db.commit()

    async def dependencia():
        async with fabrica() as db:
            try:
                yield db
            except Exception:
                await db.rollback()
                raise

    app.dependency_overrides[get_motored_db] = dependencia

    class Escenario:
        pass
    e = Escenario()
    e.fabrica, e.mundo, e.token, e.cedula = (
        fabrica, mundo, link.token, usuario.cedula)
    e.link_id = link.id
    return e


def _post(e, cedula, token=None):
    async def llamar():
        async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://prueba") as cliente:
            return await cliente.post(
                f"/api/motored/publico/informe/{token or e.token}",
                json={"cedula": cedula})
    return llamar()


async def _link(e):
    async with e.fabrica() as db:
        return (await db.execute(select(ReporteAsesorLink).where(
            ReporteAsesorLink.id == e.link_id))).scalar_one()


async def _actualizar(e, **campos):
    async with e.fabrica() as db:
        link = (await db.execute(select(ReporteAsesorLink).where(
            ReporteAsesorLink.id == e.link_id))).scalar_one()
        for campo, valor in campos.items():
            setattr(link, campo, valor)
        await db.commit()


async def test_five_wrong_cedulas_lock_the_link_even_for_the_right_one(
        escenario):
    for _ in range(5):
        r = await _post(escenario, "1234567")
        assert (r.status_code, r.json()) == (401, {"detail": CIEN})

    r = await _post(escenario, escenario.cedula)

    assert r.status_code == 429  # the failures were COMMITTED despite the 401
    assert r.headers["cache-control"] == "no-store"
    link = await _link(escenario)
    assert link.bloqueado_hasta is not None and link.intentos_fallidos == 0


async def test_after_the_lock_expires_the_right_cedula_gets_the_detail(
        escenario):
    for _ in range(5):
        await _post(escenario, "1234567")
    await _actualizar(
        escenario, bloqueado_hasta=datetime.datetime(
            2020, 1, 1, tzinfo=datetime.timezone.utc))

    r = await _post(escenario, escenario.cedula)

    assert r.status_code == 200
    async with escenario.fabrica() as db:
        filtro = await q.cargar_filtro(db, MESES, "incluir", None)
        esperado = await k.calcular_kpis_asesor_detalle(
            db, filtro, escenario.cedula)
    assert r.json() == json.loads(json.dumps(jsonable_encoder(esperado)))
    assert r.headers["x-robots-tag"] == "noindex, nofollow"
    link = await _link(escenario)
    assert (link.intentos_fallidos, link.bloqueado_hasta) == (0, None)
    assert link.ultimo_acceso_en is not None


async def test_a_revoked_token_gets_the_generic_401(escenario):
    await _actualizar(
        escenario, revocado_en=datetime.datetime.now(datetime.timezone.utc),
        motivo_revocacion="admin")

    r = await _post(escenario, escenario.cedula)

    assert (r.status_code, r.json()) == (401, {"detail": CIEN})
