"""bcrypt 5 raises ValueError above 72 bytes; verify_password must not crash."""
from app.core.security import get_password_hash, verify_password


def test_verify_password_returns_false_for_an_80_byte_password():
    hashed = get_password_hash("correcta123")

    assert verify_password("a" * 80, hashed) is False


def test_verify_password_returns_false_when_multibyte_exceeds_72_bytes():
    hashed = get_password_hash("correcta123")

    assert verify_password("ñ" * 40, hashed) is False  # 80 bytes


def test_verify_password_behaviour_is_unchanged_for_normal_passwords():
    hashed = get_password_hash("correcta123")

    assert verify_password("correcta123", hashed) is True
    assert verify_password("incorrecta", hashed) is False


def test_verify_password_accepts_a_72_byte_password():
    password = "a" * 72
    assert verify_password(password, get_password_hash(password)) is True
