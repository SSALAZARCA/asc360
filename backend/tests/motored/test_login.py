"""
Phase 4 "API + Integration" — `POST /api/motored/auth/login`
(sdd/motored-pedidos-cimientos, ADR-1, spec "Login and token issuance" /
"Invalid credentials are rejected generically").

Mirrors `app/api/v1/auth.py`'s password-verification mechanism
(`app.core.security.verify_password`/`get_password_hash`, bcrypt) but issues
a `create_motored_token`, never `create_access_token`. Uses the REAL
`TestClient(app)` with only `get_motored_db` overridden (via
`tests/motored/conftest.py`'s `override_motored_db`) -- the actual login
route, actual bcrypt verification, actual token issuance all run for real.
"""
import uuid

from fastapi.testclient import TestClient

from app.config import settings
from app.core.security import get_password_hash
from app.main import app
from app.motored.models.usuario import MotoredRole, Usuario
from tests.motored.conftest import FakeAsyncSession, override_motored_db

LOGIN_URL = "/api/motored/auth/login"


def _make_usuario(password: str, role: MotoredRole = MotoredRole.ADMIN, activo: bool = True) -> Usuario:
    usuario = Usuario(
        id=uuid.uuid4(),
        nombre="Ana Salazar",
        email="ana@motoredcolombia.com.co",
        hashed_password=get_password_hash(password),
        role=role,
        activo=activo,
    )
    usuario.sucursales = []
    return usuario


def test_valid_credentials_issue_a_motored_token(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "login-test-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "login-test-asc360-secret")
    usuario = _make_usuario("correcta123")
    override_motored_db(FakeAsyncSession(execute_queue=[[], [usuario]]))

    with TestClient(app) as client:
        response = client.post(LOGIN_URL, json={"email": usuario.email, "password": "correcta123"})

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["email"] == usuario.email
    assert body["user"]["role"] == "ADMIN"

    app.dependency_overrides.clear()


def test_wrong_password_returns_generic_401(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "login-test-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "login-test-asc360-secret")
    usuario = _make_usuario("correcta123")
    override_motored_db(FakeAsyncSession(execute_queue=[[], [usuario]]))

    with TestClient(app) as client:
        response = client.post(LOGIN_URL, json={"email": usuario.email, "password": "incorrecta"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Credenciales incorrectas"

    app.dependency_overrides.clear()


def test_unknown_email_returns_the_same_generic_401(monkeypatch):
    """Never leak whether the user exists -- unknown email and wrong
    password must be indistinguishable to the client (spec 'Invalid
    credentials are rejected generically')."""
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "login-test-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "login-test-asc360-secret")
    override_motored_db(FakeAsyncSession(execute_queue=[[], []]))

    with TestClient(app) as client:
        response = client.post(LOGIN_URL, json={"email": "nadie@x.com", "password": "cualquiera"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Credenciales incorrectas"

    app.dependency_overrides.clear()


def test_inactive_user_returns_the_same_generic_401(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "login-test-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "login-test-asc360-secret")
    usuario = _make_usuario("correcta123", activo=False)
    override_motored_db(FakeAsyncSession(execute_queue=[[], [usuario]]))

    with TestClient(app) as client:
        response = client.post(LOGIN_URL, json={"email": usuario.email, "password": "correcta123"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Credenciales incorrectas"

    app.dependency_overrides.clear()


def test_login_advisor_account_with_null_password_returns_401_not_a_crash(monkeypatch):
    """Task 3.9/3.10 (sdd/motored-ventas-perdidas-bot): `ASESOR_MOSTRADOR`
    rows (Phase 1) have `hashed_password IS NULL` -- they never get web
    credentials. Before the guard, this would reach
    `verify_password(payload.password, None)`, which crashes calling
    `.encode()` on `None` (bcrypt.checkpw) instead of cleanly rejecting."""
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "login-test-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "login-test-asc360-secret")
    usuario = Usuario(
        id=uuid.uuid4(),
        nombre="Carlos Asesor",
        email=None,
        hashed_password=None,
        role=MotoredRole.ASESOR_MOSTRADOR,
        activo=True,
    )
    usuario.sucursales = []
    override_motored_db(FakeAsyncSession(execute_queue=[[], [usuario]]))

    with TestClient(app) as client:
        response = client.post(
            LOGIN_URL, json={"email": "carlos@x.com", "password": "cualquiera"}
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Credenciales incorrectas"

    app.dependency_overrides.clear()


def test_pending_status_account_with_valid_password_returns_401_at_login(monkeypatch):
    """Review finding #4 (post-Phase-3): `status`'s `pending -> approved|
    rejected` flow is schema-wide per `Usuario`'s own docstring, not
    bot-exclusive -- a self-registered web account (any role) with a REAL
    password and `status='pending'`/`'rejected'` currently still gets a
    200 + valid JWT from `/login` (it only 401s later, one request after,
    via `get_current_motored_user`). Reject it HERE too, at login itself,
    with the same generic 401 -- defense-in-depth and a consistent,
    non-information-leaking rejection surface."""
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "login-test-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "login-test-asc360-secret")
    usuario = _make_usuario("correcta123")
    usuario.status = "pending"
    override_motored_db(FakeAsyncSession(execute_queue=[[], [usuario]]))

    with TestClient(app) as client:
        response = client.post(
            LOGIN_URL, json={"email": usuario.email, "password": "correcta123"}
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Credenciales incorrectas"

    app.dependency_overrides.clear()


def test_login_returns_503_when_motored_disabled(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", False)

    with TestClient(app) as client:
        response = client.post(LOGIN_URL, json={"email": "x@x.com", "password": "y"})

    assert response.status_code == 503
