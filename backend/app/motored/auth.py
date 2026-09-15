"""
Motored Pedidos — capa de autenticación (sdd/motored-pedidos-cimientos,
Fase 2, ADR-1).

Módulo hermano de `app.core.security`, completamente aislado: secreto
propio (`MOTORED_SECRET_KEY`), claims `iss`/`aud` propios (`"motored"`).
NUNCA reutiliza `create_access_token`/`decode_access_token` de asc360 --
eso reintroduciría exactamente el cruce de identidades que este módulo
existe para impedir.

Guardia fail-closed (defensa en profundidad, ADR-1): si `MOTORED_SECRET_KEY`
está vacío O es igual a `settings.SECRET_KEY`, tanto `create_motored_token`
como `decode_motored_token` se niegan a operar. Este es el único caso que
la sola firma HS256 no cubriría por sí sola (un operador configurando el
mismo valor en ambos secretos por error).
"""
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt

from app.config import settings

ALGORITHM = "HS256"
ISSUER = "motored"
AUDIENCE = "motored"
DEFAULT_EXPIRES = timedelta(hours=8)  # Igual al TTL de asc360 (480 min, ver app/core/security.py)


class MotoredAuthUnavailable(Exception):
    """Se lanza cuando `MOTORED_SECRET_KEY` está vacío o coincide con
    `settings.SECRET_KEY` -- Motored debe fallar cerrado, nunca operar con
    un secreto inseguro o compartido con asc360."""


def motored_secret_is_safe() -> bool:
    """True solo si hay un `MOTORED_SECRET_KEY` no vacío y distinto del
    `SECRET_KEY` de asc360. Reutilizada por `deps.require_motored_ready`."""
    secret = settings.MOTORED_SECRET_KEY
    return bool(secret) and secret != settings.SECRET_KEY


def create_motored_token(sub: str, role: str, expires_delta: Optional[timedelta] = None) -> str:
    """Crea un JWT de Motored. Lanza `MotoredAuthUnavailable` si el secreto
    no es seguro -- nunca firma un token con un secreto vacío o compartido."""
    if not motored_secret_is_safe():
        raise MotoredAuthUnavailable(
            "MOTORED_SECRET_KEY vacío o igual a SECRET_KEY: no se puede emitir un token de Motored."
        )
    expire = datetime.utcnow() + (expires_delta or DEFAULT_EXPIRES)
    to_encode = {
        "sub": sub,
        "role": role,
        "iss": ISSUER,
        "aud": AUDIENCE,
        "exp": expire,
    }
    return jwt.encode(to_encode, settings.MOTORED_SECRET_KEY, algorithm=ALGORITHM)


def decode_motored_token(token: str) -> Optional[dict]:
    """Decodifica y valida un JWT de Motored. Retorna el payload o `None`
    si es inválido, expirado, tiene `iss`/`aud` incorrectos, o si el
    secreto no es seguro (guardia fail-closed evaluada ANTES de intentar
    verificar la firma)."""
    if not motored_secret_is_safe():
        return None
    try:
        return jwt.decode(
            token,
            settings.MOTORED_SECRET_KEY,
            algorithms=[ALGORITHM],
            issuer=ISSUER,
            audience=AUDIENCE,
        )
    except JWTError:
        return None
