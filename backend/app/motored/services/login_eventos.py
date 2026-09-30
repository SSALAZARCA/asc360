"""
Login event log (T10): write and query `login_evento`.

`registrar` inserts inside a SAVEPOINT of the caller's transaction: when the
insert works it commits atomically with the lockout counter; when it fails
(e.g. the table is missing during a deploy) only the savepoint rolls back, the
error is logged and the login carries on. Never stores the password.
"""
import logging
import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.models.login_evento import LoginEvento
from app.motored.models.usuario import Usuario
from app.motored.services import login_bloqueo

logger = logging.getLogger(__name__)

USER_AGENT_MAX = 255
BOGOTA_OFFSET = timedelta(hours=-5)


async def registrar(
    db: AsyncSession, request: Request, email: str, usuario_id: Optional[uuid.UUID],
    resultado: str, motivo: Optional[str] = None,
) -> None:
    try:
        await db.flush()  # pending counter changes stay outside the savepoint
        async with db.begin_nested():
            db.add(LoginEvento(
                id=uuid.uuid4(),
                created_at=login_bloqueo.ahora(),
                email_intentado=login_bloqueo.normalizar_email(email),
                usuario_id=usuario_id,
                resultado=resultado,
                motivo=motivo,
                ip=(request.client.host if request.client else None),
                user_agent=(request.headers.get("user-agent") or "")[:USER_AGENT_MAX] or None,
            ))
    except Exception:
        logger.exception("login_evento write failed; continuing without the log row")


def _dia_bogota_a_utc(dia: date) -> datetime:
    return datetime.combine(dia, time.min) - BOGOTA_OFFSET


def _condiciones(desde, hasta, resultado, texto, usuario_id) -> list:
    conds = []
    if desde:
        conds.append(LoginEvento.created_at >= _dia_bogota_a_utc(desde))
    if hasta:  # inclusive day: strictly before the next midnight
        conds.append(LoginEvento.created_at < _dia_bogota_a_utc(hasta + timedelta(days=1)))
    if resultado:
        conds.append(LoginEvento.resultado == resultado)
    if texto:
        conds.append(func.lower(LoginEvento.email_intentado).contains(texto.strip().lower(), autoescape=True))
    if usuario_id:
        conds.append(LoginEvento.usuario_id == usuario_id)
    return conds


def _item(evento: LoginEvento, nombre: Optional[str]) -> Dict[str, Any]:
    return {
        "id": str(evento.id),
        "fecha": evento.created_at.replace(tzinfo=timezone.utc).isoformat(),
        "email": evento.email_intentado,
        "usuario_id": str(evento.usuario_id) if evento.usuario_id else None,
        "usuario_nombre": nombre,
        "resultado": evento.resultado,
        "motivo": evento.motivo,
        "ip": evento.ip,
        "user_agent": evento.user_agent,
    }


async def listar(
    db: AsyncSession, *, page: int, page_size: int, desde=None, hasta=None,
    resultado=None, texto=None, usuario_id=None,
) -> Dict[str, Any]:
    conds = _condiciones(desde, hasta, resultado, texto, usuario_id)
    total = (await db.execute(select(func.count(LoginEvento.id)).where(*conds))).scalar_one()
    stmt = (
        select(LoginEvento, Usuario.nombre)
        .outerjoin(Usuario, Usuario.id == LoginEvento.usuario_id)
        .where(*conds)
        .order_by(LoginEvento.created_at.desc(), LoginEvento.id)
        .limit(page_size).offset((page - 1) * page_size)
    )
    rows = (await db.execute(stmt)).all()
    return {"items": [_item(e, n) for e, n in rows], "total": total, "page": page, "page_size": page_size}
