"""
Own password change end to end against a real Postgres (opt-in,
`MOTORED_TEST_PG_URL`, database migrated to head): the old token is rejected
after the change and the fresh one is accepted, through the real
`get_current_motored_user` lookup and the real `password_changed_at` column.
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

ACTUAL = "clave-actual-123"
NUEVA = "clave-nueva-456"


@pytest.fixture
async def http(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "pg-password-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "pg-password-asc360-secret")
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


async def _seed_user() -> Usuario:
    motor = create_async_engine(URL)
    async with AsyncSession(motor, expire_on_commit=False) as db:
        usuario = Usuario(
            id=uuid.uuid4(), nombre="Pwd Test", role=MotoredRole.SERVICIO_CLIENTE, activo=True,
            email=f"pwd{uuid.uuid4().hex[:10]}@test.co", hashed_password=get_password_hash(ACTUAL),
        )
        db.add(usuario)
        await db.commit()
    await motor.dispose()
    return usuario


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_old_token_rejected_and_new_token_accepted_after_own_change(http):
    usuario = await _seed_user()
    old = create_motored_token(sub=str(usuario.id), role="SERVICIO_CLIENTE")
    await asyncio.sleep(1.1)  # the change must land in a later second than the old token

    changed = await http.post(
        "/api/motored/auth/password", json={"actual": ACTUAL, "nueva": NUEVA}, headers=_auth(old)
    )
    assert changed.status_code == 200, changed.text
    fresh = changed.json()["access_token"]

    again = await http.post(
        "/api/motored/auth/password", json={"actual": NUEVA, "nueva": "otra-clave-789"}, headers=_auth(old)
    )
    assert again.status_code == 401
    ok = await http.post(
        "/api/motored/auth/password", json={"actual": NUEVA, "nueva": "otra-clave-789"}, headers=_auth(fresh)
    )
    assert ok.status_code == 200, ok.text
