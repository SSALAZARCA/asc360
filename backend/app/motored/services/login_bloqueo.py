"""
Account lockout for Motored web login (T9).

Rule: MAX_FAILED failed logins for the same normalized email inside WINDOW lock
the account for LOCK_FOR, counted from the last failure that tripped it. While
locked the login answers 429 even with the right password. A success resets
the counter.

Two stores, one rule, so the response never reveals whether an email exists:
- Existing accounts: columns on `usuario`, updated with ONE atomic
  `UPDATE ... RETURNING` (Postgres serializes concurrent updates on the row, so
  parallel wrong guesses can never undercount). Survives restarts.
- Unknown emails: a small in-memory tracker with the same thresholds. It is
  per process and resets on deploy (uvicorn runs a single process here); it is
  bounded by evicting expired entries and capping tracked emails.

Times are naive UTC (like every other datetime in Motored); `ahora` is the
clock, replaceable in tests.
"""
import threading
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import case, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.models.usuario import Usuario

MAX_FAILED = 5
WINDOW = timedelta(minutes=15)
LOCK_FOR = timedelta(minutes=15)
MAX_TRACKED = 10_000
LOCKED_DETAIL = "Demasiados intentos fallidos. Tu cuenta quedó bloqueada por 15 minutos."


def ahora() -> datetime:
    return datetime.utcnow()


def normalizar_email(email: str) -> str:
    return email.strip().lower()[:255]


def limpiar_bloqueo(usuario: Usuario) -> None:
    usuario.login_fallidos = 0
    usuario.login_ventana_inicio = None
    usuario.bloqueado_hasta = None


def bloqueado_hasta_vigente(usuario: Usuario, now: datetime) -> Optional[datetime]:
    until = usuario.bloqueado_hasta
    return until if until is not None and until > now else None


async def registrar_fallo(db: AsyncSession, usuario_id, now: datetime) -> Optional[datetime]:
    """Count one failure atomically; returns the lock expiry if the account is
    locked after it (this failure included), else None. Does not commit."""
    ventana_vencida = (Usuario.login_ventana_inicio.is_(None)) | (Usuario.login_ventana_inicio <= now - WINDOW)
    nuevo_conteo = case((ventana_vencida, 1), else_=Usuario.login_fallidos + 1)
    sin_bloqueo_vigente = (Usuario.bloqueado_hasta.is_(None)) | (Usuario.bloqueado_hasta <= now)
    stmt = (
        update(Usuario)
        .where(Usuario.id == usuario_id)
        .values(
            login_fallidos=nuevo_conteo,
            login_ventana_inicio=case((ventana_vencida, now), else_=Usuario.login_ventana_inicio),
            bloqueado_hasta=case(
                ((nuevo_conteo >= MAX_FAILED) & sin_bloqueo_vigente, now + LOCK_FOR),
                else_=Usuario.bloqueado_hasta,
            ),
        )
        .returning(Usuario.bloqueado_hasta)
        .execution_options(synchronize_session=False)
    )
    until = (await db.execute(stmt)).scalars().first()
    return until if until is not None and until > now else None


# --- unknown emails: in-memory, same thresholds --------------------------------
# email -> [window_start, failures, locked_until]; insertion order ~ window start.
_unknown: "OrderedDict[str, list]" = OrderedDict()
_lock = threading.Lock()


def _vencimiento(entry: list) -> datetime:
    return max(entry[0] + WINDOW, entry[2] or entry[0])


def _descartar_vencidos(now: datetime) -> None:
    while _unknown:
        oldest = next(iter(_unknown))
        if _vencimiento(_unknown[oldest]) > now:
            break
        del _unknown[oldest]


def bloqueado_desconocido(email: str, now: datetime) -> Optional[datetime]:
    with _lock:
        entry = _unknown.get(normalizar_email(email))
        return entry[2] if entry and entry[2] and entry[2] > now else None


def registrar_fallo_desconocido(email: str) -> Optional[datetime]:
    """Count a failure for an email with no account; returns the lock expiry
    when locked after it."""
    key = normalizar_email(email)
    now = ahora()
    with _lock:
        _descartar_vencidos(now)
        entry = _unknown.get(key)
        if entry is None or entry[0] <= now - WINDOW:
            entry = [now, 0, None]
            _unknown.pop(key, None)
        entry[1] += 1
        if entry[1] >= MAX_FAILED and not (entry[2] and entry[2] > now):
            entry[2] = now + LOCK_FOR
        _unknown[key] = entry
        while len(_unknown) > MAX_TRACKED:
            _unknown.popitem(last=False)
        return entry[2] if entry[2] and entry[2] > now else None


def cantidad_rastreada() -> int:
    with _lock:
        return len(_unknown)


def reiniciar() -> None:
    """Test helper: forget every in-memory counter."""
    with _lock:
        _unknown.clear()
