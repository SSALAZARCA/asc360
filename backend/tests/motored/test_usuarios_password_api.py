"""
`POST /usuarios/{id}/password` -- reseteo de contraseña de un usuario web
de Motored por un ADMIN (feature odd/motored-salir-y-cambio-password, T2).

Cubre: ADMIN OK, no-ADMIN 403, usuario inexistente 404, usuario sin acceso
web 422 (`SIN_ACCESO_WEB`), contraseña demasiado corta 422, la propia
contraseña del ADMIN, y que la contraseña jamás se devuelva ni quede en la
auditoría. Mismas convenciones que `test_usuarios_api.py`.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.core.security import verify_password
from app.main import app
from app.motored.models.usuario import Usuario
from app.motored.services.auth import MotoredUser
from tests.motored.conftest import FakeAsyncSession, override_motored_db, override_motored_user

ALL_ROLES = ["ADMIN", "COMPRAS", "SUCURSAL", "CONSULTA"]
USUARIOS_URL = "/api/motored/usuarios"
NUEVA_PASSWORD = "nueva-clave-segura1"


@pytest.fixture(autouse=True)
def _motored_ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "usuarios-test-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "usuarios-test-asc360-secret")
    yield
    app.dependency_overrides.clear()


def _usuario(**overrides) -> Usuario:
    base = dict(
        id=uuid.uuid4(), nombre="Carla Compras", email="carla@motoredcolombia.com.co",
        hashed_password="hash-viejo", role="COMPRAS", activo=True, status="approved",
    )
    base.update(overrides)
    return Usuario(**base)


def _post_as(role, execute_queue, usuario_id, body, user_id=None):
    """Devuelve `(response, session)`. El `[[]]` inicial es el `SELECT 1`
    de `get_motored_db_or_503` (mismo criterio que `test_usuarios_api.py`)."""
    override_motored_user(MotoredUser(user_id=user_id or str(uuid.uuid4()), role=role))
    session = FakeAsyncSession(execute_queue=[[]] + list(execute_queue))
    override_motored_db(session)
    response = TestClient(app).post(f"{USUARIOS_URL}/{usuario_id}/password", json=body)
    return response, session


@pytest.mark.parametrize("role", ALL_ROLES)
def test_reset_password_restricted_to_admin_only(role):
    usuario = _usuario()
    queue = [[usuario]] if role == "ADMIN" else [[]]

    response, _ = _post_as(role, queue, usuario.id, {"password": NUEVA_PASSWORD})

    assert response.status_code == (200 if role == "ADMIN" else 403), response.text


def test_reset_password_stores_a_hash_and_never_returns_the_password():
    usuario = _usuario()

    response, session = _post_as("ADMIN", [[usuario]], usuario.id, {"password": NUEVA_PASSWORD})

    assert response.status_code == 200, response.text
    assert usuario.hashed_password != "hash-viejo"
    assert usuario.hashed_password != NUEVA_PASSWORD
    assert verify_password(NUEVA_PASSWORD, usuario.hashed_password)
    assert session.committed is True
    assert NUEVA_PASSWORD not in response.text
    assert "password" not in response.json()


def test_reset_password_audit_row_does_not_contain_the_password_or_hash():
    usuario = _usuario()

    _, session = _post_as("ADMIN", [[usuario]], usuario.id, {"password": NUEVA_PASSWORD})

    filas = [a for a in session.added if a.entidad == "usuario"]
    assert len(filas) == 1
    assert filas[0].campo == "password"
    assert filas[0].valor_anterior is None and filas[0].valor_nuevo is None


def test_admin_can_reset_their_own_password():
    admin = _usuario(role="ADMIN")

    response, _ = _post_as(
        "ADMIN", [[admin]], admin.id, {"password": NUEVA_PASSWORD}, user_id=str(admin.id)
    )

    assert response.status_code == 200, response.text
    assert verify_password(NUEVA_PASSWORD, admin.hashed_password)


def test_reset_password_unknown_user_returns_404():
    response, session = _post_as("ADMIN", [[]], uuid.uuid4(), {"password": NUEVA_PASSWORD})

    assert response.status_code == 404
    assert session.committed is False


@pytest.mark.parametrize(
    "overrides",
    [
        dict(email=None, hashed_password=None, role="ASESOR_MOSTRADOR"),
        dict(email=None),
        dict(role="ASESOR_MOSTRADOR"),
    ],
)
def test_reset_password_user_without_web_access_returns_422_sin_acceso_web(overrides):
    usuario = _usuario(**overrides)

    response, session = _post_as("ADMIN", [[usuario]], usuario.id, {"password": NUEVA_PASSWORD})

    assert response.status_code == 422
    assert "SIN_ACCESO_WEB" in response.json()["detail"]
    assert session.committed is False
    assert usuario.hashed_password in (None, "hash-viejo")


def test_reset_password_too_short_returns_422_and_changes_nothing():
    usuario = _usuario()

    response, session = _post_as("ADMIN", [[usuario]], usuario.id, {"password": "corta"})

    assert response.status_code == 422
    assert usuario.hashed_password == "hash-viejo"
    assert session.committed is False


def test_reset_password_too_short_error_does_not_echo_the_password():
    usuario = _usuario()

    response, _ = _post_as("ADMIN", [[usuario]], usuario.id, {"password": "corta"})

    assert "corta" not in response.text


def _create_as_admin(password):
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN"))
    session = FakeAsyncSession(execute_queue=[[]])
    override_motored_db(session)
    body = dict(nombre="Nuevo", email="nuevo@x.com", password=password, role="CONSULTA")
    return TestClient(app).post(USUARIOS_URL, json=body), session


def test_create_usuario_rejects_a_password_shorter_than_the_minimum():
    response, session = _create_as_admin("corta")

    assert response.status_code == 422
    assert "corta" not in response.text
    assert session.committed is False


def test_create_usuario_accepts_a_password_of_the_minimum_length():
    response, session = _create_as_admin("abcdefghi1")

    assert response.status_code == 201, response.text
    assert session.committed is True


# --- bcrypt only hashes the first 72 BYTES; bcrypt 5 raises above that -------
MSG_TOO_LONG = "La contraseña es demasiado larga (máximo 72 caracteres; tildes y emojis cuentan doble)."
PASSWORD_72_BYTES = "a" * 71 + "1"
PASSWORD_80_BYTES = "a" * 80


def test_reset_password_over_72_bytes_returns_422_with_message():
    usuario = _usuario()

    response, session = _post_as("ADMIN", [[usuario]], usuario.id, {"password": PASSWORD_80_BYTES})

    assert response.status_code == 422, response.text
    assert response.json()["detail"] == MSG_TOO_LONG
    assert PASSWORD_80_BYTES not in response.text
    assert usuario.hashed_password == "hash-viejo"
    assert session.committed is False


def test_reset_password_counts_bytes_not_characters():
    usuario = _usuario()
    # 40 chars but 80 UTF-8 bytes.
    response, _ = _post_as("ADMIN", [[usuario]], usuario.id, {"password": "ñ" * 40})

    assert response.status_code == 422
    assert response.json()["detail"] == MSG_TOO_LONG


def test_reset_password_accepts_exactly_72_bytes():
    usuario = _usuario()

    response, _ = _post_as("ADMIN", [[usuario]], usuario.id, {"password": PASSWORD_72_BYTES})

    assert response.status_code == 200, response.text
    assert verify_password(PASSWORD_72_BYTES, usuario.hashed_password)


def test_create_usuario_over_72_bytes_returns_422_with_message():
    response, session = _create_as_admin(PASSWORD_80_BYTES)

    assert response.status_code == 422, response.text
    assert response.json()["detail"] == MSG_TOO_LONG
    assert session.committed is False


def test_create_usuario_accepts_exactly_72_bytes():
    response, session = _create_as_admin(PASSWORD_72_BYTES)

    assert response.status_code == 201, response.text
    assert session.committed is True
