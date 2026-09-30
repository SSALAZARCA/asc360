"""Shared password rules and stamping for Motored web users.

Rules apply to NEW passwords only (admin create, admin reset, own change,
bootstrap script); login never re-validates, so stored passwords keep working.
"""
import re
from datetime import datetime
from typing import Optional

from fastapi import HTTPException, status

from app.core.security import get_password_hash
from app.motored.models.usuario import Usuario
from app.motored.schemas.usuario import PASSWORD_MAX_BYTES, PASSWORD_MIN_LENGTH
from app.motored.services import login_bloqueo
from app.motored.services.common_passwords import COMMON_PASSWORDS

EMAIL_LOCAL_PART_MIN = 4

MSG_MIN = f"La contraseña debe tener al menos {PASSWORD_MIN_LENGTH} caracteres"
MSG_MAX = f"La contraseña es demasiado larga (máximo {PASSWORD_MAX_BYTES} caracteres; tildes y emojis cuentan doble)."
MSG_LETTER = "La contraseña debe incluir al menos una letra."
MSG_DIGIT = "La contraseña debe incluir al menos un número."
MSG_COMMON = "Esa contraseña es demasiado común. Elige otra."
MSG_EMAIL = "La contraseña no puede contener la parte inicial de tu correo electrónico."


def _contains_email_local_part(password: str, email: Optional[str]) -> bool:
    local = (email or "").split("@", 1)[0].strip().lower()
    return len(local) >= EMAIL_LOCAL_PART_MIN and local in password.lower()


def primera_violacion(password: str, email: Optional[str] = None) -> Optional[str]:
    """Message of the first broken rule, or None. Never includes the password."""
    checks = (
        (len(password) < PASSWORD_MIN_LENGTH, MSG_MIN),
        (len(password.encode("utf-8")) > PASSWORD_MAX_BYTES, MSG_MAX),
        (not any(c.isalpha() for c in password), MSG_LETTER),
        (not re.search(r"[0-9]", password), MSG_DIGIT),
        (password.lower() in COMMON_PASSWORDS, MSG_COMMON),
        (_contains_email_local_part(password, email), MSG_EMAIL),
    )
    return next((message for broken, message in checks if broken), None)


def validar_password(password: str, email: Optional[str] = None) -> None:
    """422 with a fixed message: never includes the received password."""
    message = primera_violacion(password, email)
    if message:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=message)


def aplicar_password(usuario: Usuario, password: str, must_change: bool = False) -> None:
    """Store the hash and stamp `password_changed_at` (naive UTC), which cuts
    every session issued before now. `must_change` is True when an admin chose
    the password (the user must pick their own on the next login)."""
    usuario.hashed_password = get_password_hash(password)
    usuario.password_changed_at = datetime.utcnow()
    usuario.must_change_password = must_change
    login_bloqueo.limpiar_bloqueo(usuario)  # a new password also lifts a lockout
