"""
Inventory counts, leader API against a real Postgres (opt-in,
`MOTORED_TEST_PG_URL`, database migrated to head;
odd/motored-conteos-inventario, WU6/WU7).

Runs the real routes inside one outer transaction that is rolled back,
with sessions in savepoint mode: a route's `commit()` releases a
savepoint, so the next request sees it while nothing survives the test.
The user seam is overridden (role + id); every query is real.

The fixtures here are shared with `test_publico_conteos_pg.py`.
"""
import uuid

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine,
)

from app.config import settings
from app.core.limiter import limiter
from app.main import app
from app.motored.database import get_motored_db
from app.motored.models.conteo import Conteo
from app.motored.models.conteo_sesion import ConteoIntegrante, ConteoSesion
from app.motored.models.usuario import MotoredRole
from app.motored.services.auth import MotoredUser
from app.motored.services.conteos import acceso
from app.motored.services.trabajos import supervisor
from tests.motored.conftest import override_motored_user
from tests.motored.pg_real.test_conteos_snapshot_pg import (  # noqa: F401
    AYER, HOY, URL, Mundo, pytestmark,
)

BASE = "/api/motored/conteos"
PUBLICO = "/api/motored/publico/conteos"
PUBLICA = "https://motored.prueba"
CEDULAS = ("1130124821", "79123193")


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
def _app_lista(monkeypatch, fabrica):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "conteos-pg")
    monkeypatch.setattr(settings, "SECRET_KEY", "conteos-pg-asc360")
    monkeypatch.setattr(settings, "MOTORED_PUBLIC_URL", PUBLICA)
    monkeypatch.setattr(supervisor, "ensure_started", lambda: None)
    limiter.reset()

    async def dependencia():
        async with fabrica() as db:
            try:
                yield db
            except Exception:
                await db.rollback()
                raise

    app.dependency_overrides[get_motored_db] = dependencia
    yield
    limiter.reset()
    app.dependency_overrides.clear()


async def llamar(metodo, ruta, usuario=None, **kwargs):
    """One request; `usuario` = (role, id) for the leader API."""
    if usuario is not None:
        rol, usuario_id = usuario
        override_motored_user(
            MotoredUser(user_id=str(usuario_id), role=rol))
    async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://prueba") as cliente:
        return await cliente.request(metodo, ruta, **kwargs)


def integrantes():
    return [{"nombre": "Ana Ruiz", "cedula": "1.130.124.821"},
            {"nombre": "Luis Gil", "cedula": CEDULAS[1]}]


@pytest.fixture
async def mundo(fabrica):
    """Two leaders, one store with a fresh inventory, one PROGRAMADO
    conteo per leader. Committed (into the outer transaction)."""
    async with fabrica() as db:
        mundo = await Mundo(db).base()
        mundo.otro_lider = await mundo.usuario(MotoredRole.LIDER_INVENTARIOS)
        mundo.sucursal = await mundo.tienda()
        referencia = await mundo.referencia()
        await mundo.carga(HOY, [(mundo.sucursal, referencia, "B01", 5, 10)])
        mundo.propio = await mundo.programado(mundo.sucursal)
        mundo.ajeno = await mundo.programado(mundo.sucursal)
        mundo.ajeno.lider_id = mundo.otro_lider.id
        await db.commit()
    return mundo


def _rol(mundo, nombre):
    ids = {"ADMIN": mundo.admin.id, "LIDER_INVENTARIOS": mundo.lider.id,
           "OTRO": mundo.otro_lider.id, "GERENCIA": uuid.uuid4()}
    rol = "LIDER_INVENTARIOS" if nombre == "OTRO" else nombre
    return rol, ids[nombre]


async def _ids_listados(mundo, nombre):
    r = await llamar(
        "GET", f"{BASE}?sucursal_id={mundo.sucursal.id}",
        _rol(mundo, nombre))
    assert r.status_code == 200, r.text
    return {c["id"] for c in r.json()}


async def test_leader_scoping_on_real_rows(mundo):
    propio, ajeno = str(mundo.propio.id), str(mundo.ajeno.id)

    assert await _ids_listados(mundo, "LIDER_INVENTARIOS") == {propio}
    assert await _ids_listados(mundo, "OTRO") == {ajeno}
    assert await _ids_listados(mundo, "ADMIN") == {propio, ajeno}
    assert await _ids_listados(mundo, "GERENCIA") == {propio, ajeno}
    lider = _rol(mundo, "LIDER_INVENTARIOS")
    for ruta in ("", "/sesiones"):
        r = await llamar("GET", f"{BASE}/{ajeno}{ruta}", lider)
        assert r.status_code == 404, r.text
    r = await llamar("POST", f"{BASE}/{ajeno}/iniciar", lider)
    assert r.status_code == 404, r.text
    r = await llamar(
        "POST", f"{BASE}/{propio}/iniciar", _rol(mundo, "GERENCIA"))
    assert r.status_code == 403, r.text


async def test_admin_schedules_the_leader_starts_and_a_pair_joins(
        mundo, fabrica):
    admin, lider = _rol(mundo, "ADMIN"), _rol(mundo, "LIDER_INVENTARIOS")
    r = await llamar("POST", BASE, admin, json={
        "sucursal_id": str(mundo.sucursal.id),
        "lider_id": str(mundo.lider.id), "fecha_programada": str(AYER)})
    assert r.status_code == 201, r.text
    conteo_id = r.json()["id"]

    r = await llamar("POST", f"{BASE}/{conteo_id}/iniciar", lider)

    assert r.status_code == 200, r.text
    inicio = r.json()
    codigo, slug = inicio["codigo"], inicio["conteo"]["acceso"]["slug"]
    assert inicio["conteo"]["acceso"]["url"] == (
        f"{PUBLICA}/motored/c/{slug}")
    assert inicio["conteo"]["snapshot"]["lineas"] == 1
    async with fabrica() as db:
        conteo = await db.get(Conteo, uuid.UUID(conteo_id))
    assert conteo.codigo_hash not in r.text
    assert acceso.verificar_codigo(conteo.id, codigo, conteo.codigo_hash)
    r = await llamar("GET", f"{BASE}/{conteo_id}", lider)
    assert codigo not in r.text
    r = await llamar("GET", f"{BASE}/{conteo_id}/qr.png", lider)
    assert r.content.startswith(b"\x89PNG")

    r = await llamar("POST", f"{PUBLICO}/{slug}/unirse", json={
        "codigo": codigo, "integrantes": integrantes()})
    assert r.status_code == 201, r.text

    r = await llamar("GET", f"{BASE}/{conteo_id}/sesiones", lider)
    assert r.status_code == 200, r.text
    assert [s["etiqueta"] for s in r.json()] == [
        "Pareja 1 · Ana R. y Luis G."]
    assert CEDULAS[0] not in r.text and CEDULAS[1] not in r.text


async def test_rotating_the_code_keeps_the_pairs_session(mundo, fabrica):
    lider = _rol(mundo, "LIDER_INVENTARIOS")
    r = await llamar("POST", f"{BASE}/{mundo.propio.id}/iniciar", lider)
    codigo, slug = r.json()["codigo"], r.json()["conteo"]["acceso"]["slug"]
    r = await llamar("POST", f"{PUBLICO}/{slug}/unirse", json={
        "codigo": codigo, "integrantes": integrantes()})
    token = r.json()["sesion_token"]

    r = await llamar(
        "POST", f"{BASE}/{mundo.propio.id}/codigo/rotar", lider)

    assert r.status_code == 200, r.text
    nuevo = r.json()["codigo"]
    async with fabrica() as db:
        conteo = await db.get(Conteo, mundo.propio.id)
    assert acceso.verificar_codigo(conteo.id, nuevo, conteo.codigo_hash)
    assert not acceso.verificar_codigo(conteo.id, codigo, conteo.codigo_hash)
    r = await llamar("GET", f"{PUBLICO}/{slug}/sesion", headers={
        "Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text


async def test_annul_closes_every_pair_session(mundo, fabrica):
    lider, admin = _rol(mundo, "LIDER_INVENTARIOS"), _rol(mundo, "ADMIN")
    r = await llamar("POST", f"{BASE}/{mundo.propio.id}/iniciar", lider)
    codigo, slug = r.json()["codigo"], r.json()["conteo"]["acceso"]["slug"]
    r = await llamar("POST", f"{PUBLICO}/{slug}/unirse", json={
        "codigo": codigo, "integrantes": integrantes()})
    token = r.json()["sesion_token"]

    r = await llamar(
        "POST", f"{BASE}/{mundo.propio.id}/anular", admin,
        json={"motivo": "Se fue la luz"})

    assert r.status_code == 200, r.text
    assert r.json()["acceso"] is None
    r = await llamar("GET", f"{PUBLICO}/{slug}/sesion", headers={
        "Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    async with fabrica() as db:
        estados = (await db.scalars(select(ConteoSesion.estado).where(
            ConteoSesion.conteo_id == mundo.propio.id))).all()
        personas = (await db.scalars(select(ConteoIntegrante).join(
            ConteoSesion, ConteoSesion.id == ConteoIntegrante.sesion_id
        ).where(ConteoSesion.conteo_id == mundo.propio.id))).all()
    assert estados == ["CERRADA"]
    assert sorted(p.cedula for p in personas) == sorted(CEDULAS)
