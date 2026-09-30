"""
Login lockout + event log against a real Postgres (opt-in, `MOTORED_TEST_PG_URL`,
database migrated to head): concurrent wrong guesses are all counted (the atomic
UPDATE), the lock survives a brand new DB session, and events are persisted and
queryable through the ADMIN endpoint.
"""
import asyncio
import os
import uuid

import httpx
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import settings
from app.core.limiter import limiter
from app.core.security import get_password_hash
from app.main import app
from app.motored.auth import create_motored_token
from app.motored.database import get_motored_db
from app.motored.models.login_evento import LoginEvento
from app.motored.models.usuario import MotoredRole, Usuario
from app.motored.services import login_bloqueo

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

GOOD = "clave-correcta-2468"
LOGIN = "/api/motored/auth/login"


@pytest.fixture
async def http(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "pg-lockout-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "pg-lockout-asc360-secret")
    limiter.enabled = False  # 8 parallel attempts would trip the per-IP limit first
    login_bloqueo.reiniciar()
    motor = create_async_engine(URL)

    async def _db():
        async with AsyncSession(motor, expire_on_commit=False) as db:
            yield db

    app.dependency_overrides[get_motored_db] = _db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        yield client
    app.dependency_overrides.pop(get_motored_db, None)
    limiter.enabled = True
    await motor.dispose()


async def _seed(role=MotoredRole.COMPRAS) -> Usuario:
    motor = create_async_engine(URL)
    async with AsyncSession(motor, expire_on_commit=False) as db:
        usuario = Usuario(
            id=uuid.uuid4(), nombre="Lock PG", role=role, activo=True,
            email=f"lock{uuid.uuid4().hex[:10]}@test.co", hashed_password=get_password_hash(GOOD),
        )
        db.add(usuario)
        await db.commit()
    await motor.dispose()
    return usuario


async def _row(usuario_id):
    motor = create_async_engine(URL)
    async with AsyncSession(motor) as db:
        row = (await db.execute(sa.select(Usuario).where(Usuario.id == usuario_id))).scalars().one()
        results = (await db.execute(
            sa.select(LoginEvento.resultado).where(LoginEvento.usuario_id == usuario_id)
        )).scalars().all()
    await motor.dispose()
    return row, results


async def test_parallel_wrong_logins_are_all_counted_and_lock(http):
    usuario = await _seed()

    responses = await asyncio.gather(*[
        http.post(LOGIN, json={"email": usuario.email, "password": f"mala-{i}-clave"}) for i in range(8)
    ])

    codes = sorted(r.status_code for r in responses)
    assert set(codes) <= {401, 429} and codes.count(429) >= 1
    row, results = await _row(usuario.id)
    # Every attempt is logged; every one that got past the lock check was counted
    # (none lost to a race), so the counter equals the FALLO rows.
    assert len(results) == 8
    assert row.login_fallidos == results.count("FALLO") >= 5
    assert row.bloqueado_hasta is not None


async def test_lock_survives_a_new_session_and_blocks_the_right_password(http):
    usuario = await _seed()
    for i in range(5):
        await http.post(LOGIN, json={"email": usuario.email, "password": f"mala-{i}-clave"})

    response = await http.post(LOGIN, json={"email": usuario.email, "password": GOOD})

    assert response.status_code == 429
    row, _results = await _row(usuario.id)  # fresh engine/session
    assert row.login_fallidos == 5 and row.bloqueado_hasta is not None


async def test_events_are_persisted_and_queryable_by_an_admin(http):
    usuario = await _seed()
    admin = await _seed(MotoredRole.ADMIN)
    await http.post(LOGIN, json={"email": usuario.email, "password": GOOD})
    await http.post(LOGIN, json={"email": usuario.email, "password": "mala-clave-1"})
    token = create_motored_token(sub=str(admin.id), role="ADMIN")

    response = await http.get(
        "/api/motored/usuarios/ingresos", params={"usuario_id": str(usuario.id)},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 2
    assert {i["resultado"] for i in body["items"]} == {"EXITO", "FALLO"}
    assert all(i["usuario_nombre"] == "Lock PG" for i in body["items"])
