"""
Phase 5 "Bootstrap" — `backend/scripts/create_motored_admin.py`
(sdd/motored-pedidos-cimientos).

Mirrors `backend/scripts/create_superadmin.py`'s idempotency pattern
(check-by-email, create only if absent, never reset an existing password)
but targets Motored's own isolated `Usuario` model/database.

This exercises the ACTUAL script entrypoint end-to-end against a real
throwaway `aiosqlite` engine — not `FakeAsyncSession` — because the thing
under test IS the script's own session/engine wiring (it calls
`motored_session_maker()` itself, it isn't handed a session via DI like the
API routers are). This mirrors the precedent already set by
`tests/motored/test_database.py` for exercising real engine/session
contracts with a throwaway SQLite database.
"""
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.core.security import verify_password
from app.motored import database as motored_database
from app.motored.models.usuario import MotoredRole, Usuario

from scripts import create_motored_admin


@pytest.fixture
async def motored_sqlite_engine(tmp_path, monkeypatch):
    """Real throwaway aiosqlite engine with the full Motored schema, wired
    in through the same `MOTORED_DATABASE_URL` + lazy-engine seam the script
    itself reads (`app.motored.database.get_motored_engine`)."""
    db_path = tmp_path / "motored_bootstrap.db"
    monkeypatch.setattr(settings, "MOTORED_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    motored_database.get_motored_engine.cache_clear()

    # Solo la tabla `usuario` -- el resto del schema Motored (p.ej.
    # `parametro_metodologia.valor`, tipado JSONB) no es representable en
    # SQLite y no hace falta para este script, que únicamente toca `Usuario`.
    engine = motored_database.get_motored_engine()
    async with engine.begin() as conn:
        await conn.run_sync(
            motored_database.MotoredBase.metadata.create_all, tables=[Usuario.__table__]
        )

    yield engine

    await engine.dispose()
    motored_database.get_motored_engine.cache_clear()


async def _fetch_admin(engine) -> Usuario | None:
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        result = await session.execute(
            sa.select(Usuario).where(Usuario.email == create_motored_admin.ADMIN_EMAIL)
        )
        return result.scalars().first()


async def test_missing_database_url_fails_clearly(monkeypatch, capsys):
    monkeypatch.setattr(settings, "MOTORED_DATABASE_URL", "")

    with pytest.raises(SystemExit) as exc_info:
        await create_motored_admin.create_motored_admin()

    assert exc_info.value.code != 0
    captured = capsys.readouterr()
    assert "MOTORED_DATABASE_URL" in captured.out


async def test_first_run_creates_admin(motored_sqlite_engine, monkeypatch):
    monkeypatch.setenv("MOTORED_ADMIN_PASSWORD", "un-password-de-prueba1")

    await create_motored_admin.create_motored_admin()

    admin = await _fetch_admin(motored_sqlite_engine)
    assert admin is not None
    assert admin.nombre == "asalazar"
    assert admin.email == "asalazarc@motoredcolombia.com.co"
    assert admin.role == MotoredRole.ADMIN
    assert admin.activo is True
    assert verify_password("un-password-de-prueba1", admin.hashed_password)


async def test_second_run_is_noop_and_never_resets_password(motored_sqlite_engine, monkeypatch):
    monkeypatch.setenv("MOTORED_ADMIN_PASSWORD", "primera-contraseña1")
    await create_motored_admin.create_motored_admin()

    first_admin = await _fetch_admin(motored_sqlite_engine)
    first_id = first_admin.id
    first_hash = first_admin.hashed_password

    # Segunda corrida con una contraseña DISTINTA -- no debe pisar nada.
    monkeypatch.setenv("MOTORED_ADMIN_PASSWORD", "segunda-contraseña-distinta1")
    await create_motored_admin.create_motored_admin()

    session_maker = async_sessionmaker(
        motored_sqlite_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_maker() as session:
        result = await session.execute(
            sa.select(Usuario).where(Usuario.email == create_motored_admin.ADMIN_EMAIL)
        )
        rows = result.scalars().all()

    assert len(rows) == 1
    assert rows[0].id == first_id
    assert rows[0].hashed_password == first_hash
    assert verify_password("primera-contraseña1", rows[0].hashed_password)
    assert not verify_password("segunda-contraseña-distinta1", rows[0].hashed_password)


@pytest.mark.parametrize("bad", ["corta", "a" * 73])
def test_resolve_password_rejects_out_of_range_without_printing_it(monkeypatch, capsys, bad):
    monkeypatch.setenv("MOTORED_ADMIN_PASSWORD", bad)

    with pytest.raises(SystemExit) as exc_info:
        create_motored_admin._resolve_password()

    assert exc_info.value.code != 0
    out = capsys.readouterr()
    assert bad not in out.out + out.err
    assert "contraseña" in (out.out + out.err).lower()


@pytest.mark.parametrize("bad", ["abcdefgh1", "soloLetrasAqui", "8675309421", "Password123", "xxasalazarc99"])
def test_resolve_password_applies_the_same_policy_as_the_api(monkeypatch, capsys, bad):
    monkeypatch.setenv("MOTORED_ADMIN_PASSWORD", bad)

    with pytest.raises(SystemExit):
        create_motored_admin._resolve_password()

    out = capsys.readouterr()
    assert bad not in out.out + out.err


def test_resolve_password_accepts_a_compliant_password(monkeypatch):
    monkeypatch.setenv("MOTORED_ADMIN_PASSWORD", "una-clave-valida-2026x")

    assert create_motored_admin._resolve_password() == "una-clave-valida-2026x"
