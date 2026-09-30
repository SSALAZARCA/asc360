"""
Motored T9 + T10: per-account lockout after failed logins and the login event log.

Runs the REAL login route against a throwaway aiosqlite database (same
precedent as `test_bootstrap_admin.py`) so the atomic counter UPDATE, the
savepoint around the event insert and the admin queries execute for real. The
clock is injected through `login_bloqueo.ahora`. Concurrency against real
Postgres lives in `pg_real/test_login_lockout_pg.py`.
"""
import uuid
from datetime import datetime, timedelta

import httpx
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.core.limiter import limiter
from app.core.security import get_password_hash
from app.main import app
from app.motored.database import get_motored_db
from app.motored.models.auditoria_maestro import AuditoriaMaestro
from app.motored.models.login_evento import LoginEvento
from app.motored.models.usuario import MotoredRole, Usuario
from app.motored.services import login_bloqueo
from tests.motored.conftest import override_motored_user
from app.motored.services.auth import MotoredUser

LOGIN = "/api/motored/auth/login"
GOOD = "clave-correcta-2468"
LOCK_DETAIL = "Demasiados intentos fallidos. Tu cuenta quedó bloqueada por 15 minutos."
T0 = datetime(2026, 9, 30, 12, 0, 0)


class Clock:
    def __init__(self):
        self.now = T0

    def __call__(self):
        return self.now

    def advance(self, **kw):
        self.now += timedelta(**kw)


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(login_bloqueo, "ahora", c)
    return c


@pytest.fixture
async def maker(tmp_path, monkeypatch, clock):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "lockout-test-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "lockout-test-asc360-secret")
    limiter.reset()
    login_bloqueo.reiniciar()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'lockout.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(
            Usuario.metadata.create_all,
            tables=[Usuario.__table__, LoginEvento.__table__, AuditoriaMaestro.__table__],
        )
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)

    async def _db():
        async with session_maker() as db:
            yield db

    app.dependency_overrides[get_motored_db] = _db
    yield session_maker
    app.dependency_overrides.clear()
    await engine.dispose()
    limiter.reset()
    login_bloqueo.reiniciar()


@pytest.fixture
async def http(maker):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        yield client


async def _seed(maker, email="ana@motoredcolombia.com.co", role=MotoredRole.COMPRAS, **kw) -> Usuario:
    fields = dict(activo=True, status="approved")
    fields.update(kw)
    usuario = Usuario(
        id=uuid.uuid4(), nombre="Ana Salazar", email=email, hashed_password=get_password_hash(GOOD),
        role=role, **fields,
    )
    async with maker() as db:
        db.add(usuario)
        await db.commit()
    return usuario


async def _attempt(http, email, password="mala-clave-1", **kw):
    return await http.post(LOGIN, json={"email": email, "password": password}, **kw)


async def _fail_n(http, email, n):
    return [await _attempt(http, email) for _ in range(n)]


async def _events(maker):
    async with maker() as db:
        rows = await db.execute(sa.select(LoginEvento).order_by(sa.text("rowid")))
        return list(rows.scalars().all())


# --- T9 lockout ---------------------------------------------------------------
async def test_fifth_failure_locks_with_429(http, maker):
    await _seed(maker)
    responses = await _fail_n(http, "ana@motoredcolombia.com.co", 5)

    assert [r.status_code for r in responses] == [401, 401, 401, 401, 429]
    assert responses[4].json()["detail"] == LOCK_DETAIL


async def test_locked_account_rejects_even_the_correct_password(http, maker):
    await _seed(maker)
    await _fail_n(http, "ana@motoredcolombia.com.co", 5)

    response = await _attempt(http, "ana@motoredcolombia.com.co", GOOD)

    assert response.status_code == 429
    assert response.json()["detail"] == LOCK_DETAIL
    assert "access_token" not in response.text


async def test_lock_expires_fifteen_minutes_after_the_fifth_failure(http, maker, clock):
    await _seed(maker)
    await _fail_n(http, "ana@motoredcolombia.com.co", 5)

    clock.advance(minutes=14, seconds=59)
    assert (await _attempt(http, "ana@motoredcolombia.com.co", GOOD)).status_code == 429
    clock.advance(seconds=2)
    assert (await _attempt(http, "ana@motoredcolombia.com.co", GOOD)).status_code == 200


async def test_failures_outside_the_window_do_not_add_up(http, maker, clock):
    await _seed(maker)
    await _fail_n(http, "ana@motoredcolombia.com.co", 4)
    clock.advance(minutes=15, seconds=1)

    responses = await _fail_n(http, "ana@motoredcolombia.com.co", 4)

    assert [r.status_code for r in responses] == [401, 401, 401, 401]


async def test_success_resets_the_counter(http, maker):
    await _seed(maker)
    await _fail_n(http, "ana@motoredcolombia.com.co", 4)
    assert (await _attempt(http, "ana@motoredcolombia.com.co", GOOD)).status_code == 200

    responses = await _fail_n(http, "ana@motoredcolombia.com.co", 4)

    assert [r.status_code for r in responses] == [401, 401, 401, 401]


async def test_unknown_email_is_counted_and_locked_with_the_same_response(http, maker):
    await _seed(maker)
    known = await _fail_n(http, "ana@motoredcolombia.com.co", 5)
    unknown = await _fail_n(http, "nadie@motoredcolombia.com.co", 5)

    assert [r.status_code for r in unknown] == [r.status_code for r in known]
    assert unknown[4].json() == known[4].json()
    assert unknown[0].json() == known[0].json()


async def test_email_is_normalized_for_counting(http, maker):
    responses = []
    for email in ("Nadie@x.co", " nadie@x.co", "NADIE@x.co", "nadie@X.co", "nadie@x.co"):
        responses.append(await _attempt(http, email))

    assert responses[4].status_code == 429


async def test_unknown_tracker_is_bounded(monkeypatch):
    monkeypatch.setattr(login_bloqueo, "MAX_TRACKED", 3)
    login_bloqueo.reiniciar()
    for i in range(10):
        login_bloqueo.registrar_fallo_desconocido(f"u{i}@x.co")

    assert login_bloqueo.cantidad_rastreada() == 3


async def test_admin_password_reset_clears_the_lock(http, maker):
    usuario = await _seed(maker)
    await _fail_n(http, usuario.email, 5)
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN"))

    reset = await http.post(f"/api/motored/usuarios/{usuario.id}/password", json={"password": "otra-clave-9753"})
    assert reset.status_code == 200, reset.text

    assert (await _attempt(http, usuario.email, "otra-clave-9753")).status_code == 200


async def test_desbloquear_clears_the_lock_and_is_audited(http, maker):
    usuario = await _seed(maker)
    await _fail_n(http, usuario.email, 5)
    admin_id = uuid.uuid4()
    override_motored_user(MotoredUser(user_id=str(admin_id), role="ADMIN"))

    response = await http.post(f"/api/motored/usuarios/{usuario.id}/desbloquear")

    assert response.status_code == 200, response.text
    assert response.json()["bloqueado_hasta"] is None
    assert (await _attempt(http, usuario.email, GOOD)).status_code == 200
    async with maker() as db:
        rows = (await db.execute(sa.select(AuditoriaMaestro))).scalars().all()
    audit = [r for r in rows if r.campo == "bloqueado_hasta"]
    assert len(audit) == 1 and audit[0].entidad_id == usuario.id and audit[0].usuario_id == admin_id


@pytest.mark.parametrize("role", ["COMPRAS", "CONSULTA", "SERVICIO_CLIENTE"])
async def test_desbloquear_is_admin_only(http, maker, role):
    usuario = await _seed(maker)
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role=role))

    response = await http.post(f"/api/motored/usuarios/{usuario.id}/desbloquear")

    assert response.status_code == 403


async def test_desbloquear_unknown_user_is_404(http, maker):
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN"))
    assert (await http.post(f"/api/motored/usuarios/{uuid.uuid4()}/desbloquear")).status_code == 404


async def test_usuarios_list_shows_bloqueado_hasta_only_while_locked(http, maker, clock):
    usuario = await _seed(maker)
    await _fail_n(http, usuario.email, 5)
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN"))

    locked = (await http.get("/api/motored/usuarios")).json()[0]
    assert locked["bloqueado_hasta"].startswith("2026-09-30T12:15:00")
    clock.advance(minutes=16)
    assert (await http.get("/api/motored/usuarios")).json()[0]["bloqueado_hasta"] is None


# --- T10 event log ----------------------------------------------------------------
async def test_every_attempt_is_logged_with_motive_and_no_password(http, maker):
    usuario = await _seed(maker)
    await _attempt(http, usuario.email, "secreto-equivocado-1", headers={"User-Agent": "Mozilla/5.0 Test"})
    await _attempt(http, usuario.email, GOOD)
    await _fail_n(http, usuario.email, 5)
    await _attempt(http, usuario.email, GOOD)

    events = await _events(maker)

    assert [(e.resultado, e.motivo) for e in events] == [
        ("FALLO", "CREDENCIALES"), ("EXITO", None),
        ("FALLO", "CREDENCIALES"), ("FALLO", "CREDENCIALES"), ("FALLO", "CREDENCIALES"),
        ("FALLO", "CREDENCIALES"), ("FALLO", "CREDENCIALES"),
        ("BLOQUEADO", "CUENTA_BLOQUEADA"),
    ]
    first = events[0]
    assert first.email_intentado == usuario.email and first.usuario_id == usuario.id
    assert first.ip == "127.0.0.1" and first.user_agent == "Mozilla/5.0 Test"
    assert "secreto-equivocado-1" not in repr([vars(e) for e in events])
    assert GOOD not in repr([vars(e) for e in events])


async def test_unknown_inactive_and_pending_motives(http, maker):
    await _seed(maker, email="off@x.co", activo=False)
    await _seed(maker, email="pend@x.co", status="pending")

    await _attempt(http, "nadie@x.co")
    await _attempt(http, "off@x.co", GOOD)
    await _attempt(http, "pend@x.co", GOOD)

    events = await _events(maker)
    assert [(e.email_intentado, e.resultado, e.motivo) for e in events] == [
        ("nadie@x.co", "FALLO", "CREDENCIALES"),
        ("off@x.co", "FALLO", "INACTIVO"),
        ("pend@x.co", "FALLO", "PENDIENTE"),
    ]
    assert events[0].usuario_id is None
    # The caller never sees the internal motive.
    assert "INACTIVO" not in (await _attempt(http, "off@x.co", GOOD)).text


async def test_user_agent_is_truncated(http, maker):
    await _attempt(http, "nadie@x.co", headers={"User-Agent": "A" * 600})

    assert len((await _events(maker))[0].user_agent) == 255


async def test_event_write_failure_does_not_break_login_or_counting(http, maker):
    usuario = await _seed(maker)
    async with maker() as db:
        await db.execute(sa.text("DROP TABLE login_evento"))
        await db.commit()

    ok = await _attempt(http, usuario.email, GOOD)
    assert ok.status_code == 200
    bad = await _fail_n(http, usuario.email, 5)

    assert [r.status_code for r in bad] == [401, 401, 401, 401, 429]


# --- T10 admin endpoint ---------------------------------------------------------------
EVENTOS = "/api/motored/usuarios/ingresos"


async def _seed_events(maker, usuario_id=None):
    rows = [
        ("ana@x.co", "EXITO", None, datetime(2026, 9, 30, 15, 0)),
        ("ana@x.co", "FALLO", "CREDENCIALES", datetime(2026, 9, 30, 16, 0)),
        ("otra@x.co", "BLOQUEADO", "CUENTA_BLOQUEADA", datetime(2026, 9, 29, 4, 0)),
        ("100%_raro@x.co", "FALLO", "CREDENCIALES", datetime(2026, 9, 28, 12, 0)),
    ]
    async with maker() as db:
        for email, resultado, motivo, when in rows:
            db.add(LoginEvento(
                id=uuid.uuid4(), created_at=when, email_intentado=email, resultado=resultado,
                motivo=motivo, ip="10.0.0.1", user_agent="UA", usuario_id=usuario_id if email == "ana@x.co" else None,
            ))
        await db.commit()


async def test_eventos_newest_first_with_contract_fields(http, maker):
    usuario = await _seed(maker, email="ana@x.co")
    await _seed_events(maker, usuario.id)
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN"))

    body = (await http.get(EVENTOS)).json()

    assert body["total"] == 4 and body["page"] == 1 and body["page_size"] == 50
    assert [i["resultado"] for i in body["items"]] == ["FALLO", "EXITO", "BLOQUEADO", "FALLO"]
    top = body["items"][0]
    assert set(top) == {"id", "fecha", "email", "usuario_id", "usuario_nombre", "resultado", "motivo", "ip", "user_agent"}
    assert top["usuario_nombre"] == "Ana Salazar" and top["fecha"].startswith("2026-09-30T16:00:00")


async def test_eventos_filters(http, maker):
    usuario = await _seed(maker, email="ana@x.co")
    await _seed_events(maker, usuario.id)
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN"))

    async def emails(**params):
        return [i["email"] for i in (await http.get(EVENTOS, params=params)).json()["items"]]

    assert await emails(resultado="BLOQUEADO") == ["otra@x.co"]
    assert len(await emails(texto="ANA")) == 2
    assert await emails(texto="100%") == ["100%_raro@x.co"]  # LIKE wildcards are escaped
    assert len(await emails(usuario_id=str(usuario.id))) == 2
    # Dates are Colombia days (UTC-5): 2026-09-29 04:00 UTC is still 09-28 there.
    assert await emails(desde="2026-09-29", hasta="2026-09-29") == []
    assert await emails(desde="2026-09-30", hasta="2026-09-30") == ["ana@x.co", "ana@x.co"]
    assert (await http.get(EVENTOS, params={"resultado": "NADA"})).status_code == 422


async def test_eventos_pagination(http, maker):
    await _seed_events(maker)
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN"))

    page2 = (await http.get(EVENTOS, params={"page": 2, "page_size": 3})).json()

    assert page2["total"] == 4 and len(page2["items"]) == 1
    assert (await http.get(EVENTOS, params={"page_size": 201})).status_code == 422


@pytest.mark.parametrize("role", ["COMPRAS", "CONSULTA", "SUCURSAL", "SERVICIO_CLIENTE"])
async def test_eventos_is_admin_only(http, maker, role):
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role=role))

    assert (await http.get(EVENTOS)).status_code == 403
