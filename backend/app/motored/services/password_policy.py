"""Shared password rules and stamping for Motored web users."""
from datetime import datetime

from fastapi import HTTPException, status

from app.core.security import get_password_hash
from app.motored.models.usuario import Usuario
from app.motored.schemas.usuario import PASSWORD_MAX_BYTES, PASSWORD_MIN_LENGTH


def validar_password(password: str) -> None:
    """422 with a fixed message: never includes the received password."""
    if len(password) < PASSWORD_MIN_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"La contraseña debe tener al menos {PASSWORD_MIN_LENGTH} caracteres",
        )
    if len(password.encode("utf-8")) > PASSWORD_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"La contraseña es demasiado larga (máximo {PASSWORD_MAX_BYTES} caracteres; tildes y emojis cuentan doble).",
        )


def aplicar_password(usuario: Usuario, password: str) -> None:
    """Store the hash and stamp `password_changed_at` (naive UTC), which cuts
    every session issued before now."""
    usuario.hashed_password = get_password_hash(password)
    usuario.password_changed_at = datetime.utcnow()
