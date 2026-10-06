"""
Forced password change end to end against a real Postgres (opt-in,
`MOTORED_TEST_PG_URL`, database migrated to head): an ADMIN creates a user
through the API, the user logs in, every other endpoint answers 403
PASSWORD_CHANGE_REQUIRED, the own password change works, and afterwards the
user reaches the other endpoints.
"""
import asyncio
import os
import uuid

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import settings
from app.core.limiter import limiter
from app.core.security import get_password_hash
from app.main import app
from app.motored.auth import create_motored_token
from app.motored.database import get_motored_db
from app.motored.models.usuario import MotoredRole, Usuario

URL = os.environ.get("MOTORED_TEST_PG_URL")
pytestmark = [
    pytest.mark.pg_real,
    pytest.mark.skipif(not URL, reason="MOTORED_TEST_PG_URL no definida"),
]

INITIAL = "clave-inicial-2468"
CHOSEN = "mi-propia-clave-1357"
BLOCKED = {"code": "PASSWORD_CHANGE_REQUIRED"}


@pytest.fixture
async def http(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "pg-forced-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "pg-forced-asc360-secret")
    limiter.reset()
    motor = create_async_engine(URL)

    async def _db():
        async with AsyncSession(motor, expire_on_commit=False) as db:
            yield db

    app.dependency_overrides[get_motored_db] = _db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        yield client
    app.dependency_overrides.pop(get_motored_db, None)
    await motor.dispose()


async def _seed_admin() -> Usuario:
    motor = create_async_engine(URL)
    async with AsyncSession(motor, expire_on_commit=False) as db:
        admin = Usuario(
            id=uuid.uuid4(), nombre="Admin PG", role=MotoredRole.ADMIN, activo=True,
            email=f"adm{uuid.uuid4().hex[:10]}@test.co", hashed_password=get_password_hash(INITIAL),
        )
        db.add(admin)
        await db.commit()
    await motor.dispose()
    return admin


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _create_and_login(http):
    admin = await _seed_admin()
    admin_token = create_motored_token(sub=str(admin.id), role="ADMIN")
    email = f"nuevo{uuid.uuid4().hex[:10]}@test.co"
    created = await http.post(
        "/api/motored/usuarios", headers=_auth(admin_token),
        json={"nombre": "Nuevo", "email": email, "password": INITIAL, "role": "COMPRAS"},
    )
    assert created.status_code == 201, created.text
    login = await http.post("/api/motored/auth/login", json={"email": email, "password": INITIAL})
    assert login.status_code == 200, login.text
    return login.json()


async def test_created_user_is_forced_to_change_then_reaches_other_endpoints(http):
    session = await _create_and_login(http)
    assert session["user"]["must_change_password"] is True
    token = session["access_token"]

    blocked = await http.get("/api/motored/maestros/sucursales", headers=_auth(token))
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == BLOCKED

    await asyncio.sleep(1.1)  # the change must land in a later second than the old token
    changed = await http.post(
        "/api/motored/auth/password", json={"actual": INITIAL, "nueva": CHOSEN}, headers=_auth(token)
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["user"]["must_change_password"] is False

    ok = await http.get(
        "/api/motored/maestros/sucursales", headers=_auth(changed.json()["access_token"])
    )
    assert ok.status_code == 200, ok.text


async def test_admin_reset_forces_a_change_on_an_existing_user(http):
    session = await _create_and_login(http)
    admin = await _seed_admin()
    admin_token = create_motored_token(sub=str(admin.id), role="ADMIN")
    await asyncio.sleep(1.1)
    await http.post(
        "/api/motored/auth/password", json={"actual": INITIAL, "nueva": CHOSEN},
        headers=_auth(session["access_token"]),
    )
    reset = await http.post(
        f"/api/motored/usuarios/{session['user']['id']}/password",
        json={"password": "reseteada-por-admin-99"}, headers=_auth(admin_token),
    )
    assert reset.status_code == 200, reset.text
    login = await http.post(
        "/api/motored/auth/login",
        json={"email": session["user"]["email"], "password": "reseteada-por-admin-99"},
    )
    assert login.json()["user"]["must_change_password"] is True
