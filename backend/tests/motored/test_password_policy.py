"""
Motored T7: stricter rules for NEW web passwords (min 10, a letter and a
digit, not a common password, no email local part). Checked on the pure
policy and through the three entry points (admin create, admin reset, own
change). Login never re-validates, so an old 8-character password still works.
"""
import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import settings
from app.core.limiter import limiter
from app.core.security import get_password_hash
from app.main import app
from app.motored.models.usuario import Usuario
from app.motored.services.auth import MotoredUser
from app.motored.services.password_policy import validar_password
from tests.motored.conftest import FakeAsyncSession, override_motored_db, override_motored_user

EMAIL = "carolina.perez@motoredcolombia.com.co"
MSG_MIN = "La contraseña debe tener al menos 10 caracteres"
MSG_LETTER = "La contraseña debe incluir al menos una letra."
MSG_DIGIT = "La contraseña debe incluir al menos un número."
MSG_COMMON = "Esa contraseña es demasiado común. Elige otra."
MSG_EMAIL = "La contraseña no puede contener la parte inicial de tu correo electrónico."
MSG_LONG = "La contraseña es demasiado larga (máximo 72 caracteres; tildes y emojis cuentan doble)."


def _detail(password, email=EMAIL):
    with pytest.raises(HTTPException) as exc:
        validar_password(password, email)
    assert exc.value.status_code == 422
    return exc.value.detail


def test_nine_characters_is_too_short_and_ten_is_accepted():
    assert _detail("abcdefgh1") == MSG_MIN
    validar_password("abcdefghi1", EMAIL)


def test_a_password_without_a_digit_is_rejected():
    assert _detail("soloLetrasAqui") == MSG_DIGIT


def test_a_password_without_a_letter_is_rejected():
    assert _detail("8675309421") == MSG_LETTER


def test_common_passwords_are_rejected_case_insensitively():
    assert _detail("contraseña123") == MSG_COMMON
    assert _detail("Password123") == MSG_COMMON
    assert _detail("MOTORED2026") == MSG_COMMON


def test_password_containing_the_email_local_part_is_rejected_case_insensitively():
    assert _detail("XX-Carolina.Perez-99") == MSG_EMAIL


def test_short_email_local_part_is_not_checked():
    validar_password("abcdefghi1zzz", "ab@x.com")
    validar_password("abcdefghi1zzz", "abc@x.com")
    assert _detail("xxabcdxx1zzzz", "abcd@x.com") == MSG_EMAIL


def test_email_is_optional():
    validar_password("abcdefghi1")


def test_max_72_bytes_is_still_enforced_with_its_message():
    assert _detail("a1" * 37) == MSG_LONG
    validar_password("a1" * 36)


def test_first_failing_rule_wins():
    assert _detail("abc") == MSG_MIN
    assert _detail("a" * 80) == MSG_LONG


def test_the_rejected_password_is_never_echoed():
    assert "soloLetrasAqui" not in _detail("soloLetrasAqui")


# --- entry points -----------------------------------------------------------
@pytest.fixture(autouse=True)
def _ready(monkeypatch):
    monkeypatch.setattr(settings, "MOTORED_ENABLED", True)
    monkeypatch.setattr(settings, "MOTORED_SECRET_KEY", "policy-test-motored-secret")
    monkeypatch.setattr(settings, "SECRET_KEY", "policy-test-asc360-secret")
    limiter.reset()
    yield
    limiter.reset()
    app.dependency_overrides.clear()


def _admin_post(path, body, queue):
    override_motored_user(MotoredUser(user_id=str(uuid.uuid4()), role="ADMIN"))
    session = FakeAsyncSession(execute_queue=[[]] + queue)
    override_motored_db(session)
    return TestClient(app).post(path, json=body), session


def _target() -> Usuario:
    return Usuario(
        id=uuid.uuid4(), nombre="Carolina", email=EMAIL, hashed_password="hash-viejo",
        role="COMPRAS", activo=True, status="approved",
    )


@pytest.mark.parametrize("password,message", [
    ("abcdefgh1", MSG_MIN), ("soloLetrasAqui", MSG_DIGIT), ("8675309421", MSG_LETTER),
    ("contraseña123", MSG_COMMON), ("zzcarolina.perez9", MSG_EMAIL),
])
def test_admin_create_applies_the_policy_with_the_email(password, message):
    body = dict(nombre="C", email=EMAIL, password=password, role="CONSULTA")

    response, session = _admin_post("/api/motored/usuarios", body, [])

    assert response.status_code == 422
    assert response.json()["detail"] == message
    assert session.committed is False


@pytest.mark.parametrize("password,message", [
    ("abcdefgh1", MSG_MIN), ("soloLetrasAqui", MSG_DIGIT), ("contraseña123", MSG_COMMON),
    ("zzcarolina.perez9", MSG_EMAIL),
])
def test_admin_reset_applies_the_policy_with_the_target_email(password, message):
    usuario = _target()

    response, session = _admin_post(
        f"/api/motored/usuarios/{usuario.id}/password", {"password": password}, [[usuario]]
    )

    assert response.status_code == 422
    assert response.json()["detail"] == message
    assert usuario.hashed_password == "hash-viejo" and session.committed is False


def _own_change(nueva, email=EMAIL):
    from app.motored.auth import create_motored_token
    usuario = Usuario(
        id=uuid.uuid4(), nombre="Carolina", email=email,
        hashed_password=get_password_hash("clave-actual-123"), role="COMPRAS", activo=True,
        status="approved",
    )
    override_motored_db(FakeAsyncSession(execute_queue=[[], [usuario], [usuario]]))
    token = create_motored_token(sub=str(usuario.id), role="COMPRAS")
    response = TestClient(app).post(
        "/api/motored/auth/password", json={"actual": "clave-actual-123", "nueva": nueva},
        headers={"Authorization": f"Bearer {token}"},
    )
    return response


@pytest.mark.parametrize("nueva,message", [
    ("abcdefgh1", MSG_MIN), ("soloLetrasAqui", MSG_DIGIT), ("8675309421", MSG_LETTER),
    ("Password123", MSG_COMMON), ("zzcarolina.perez9", MSG_EMAIL),
])
def test_own_change_applies_the_policy_with_the_users_email(nueva, message):
    response = _own_change(nueva)

    assert response.status_code == 422
    assert response.json()["detail"] == message


def test_login_still_accepts_an_old_eight_character_password():
    usuario = Usuario(
        id=uuid.uuid4(), nombre="Vieja", email="vieja@motoredcolombia.com.co",
        hashed_password=get_password_hash("abc12345"), role="COMPRAS", activo=True, status="approved",
    )
    usuario.sucursales = []
    override_motored_db(FakeAsyncSession(execute_queue=[[], [usuario]]))

    response = TestClient(app).post(
        "/api/motored/auth/login", json={"email": usuario.email, "password": "abc12345"}
    )

    assert response.status_code == 200, response.text
    assert response.json()["user"]["must_change_password"] is False
