"""
Motored -- the asesor's personal report link
(odd/motored-reporte-diario-asesor, T3a).

One secret, permanent link per asesor (`models/reporte_asesor_link.py`).
An ADMIN generates it in Gestión de usuarios and Lore sends it; the asesor
opens it and types the cédula to see the report.

Invariant: an ACTIVE link exists only while its usuario is active, its
registration approved, its cédula approved and its Telegram linked
(`motivo_no_permitido`). Every write path that can break one of those
calls `revocar_si_cambio` with the `huella` taken before the change, so
the link dies with the condition. The Telegram link through a one-time
code (bot `/admin/vincular`) uses `revocar_por_telegram_nuevo`.

The token is a credential: no function here logs it, and `estado` (what
the ADMIN endpoints return) never carries it.
"""
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update

from app.config import settings
from app.motored.models.reporte_asesor_link import ReporteAsesorLink
from app.motored.models.usuario import Usuario

TOKEN_BYTES = 32
RUTA_PUBLICA = "/motored/informe/"

MOTIVO_REGENERADO = "regenerado"
MOTIVO_ANULADO = "anulado por admin"
MOTIVO_DESACTIVADO = "usuario desactivado"
MOTIVO_CEDULA = "cédula cambiada"
MOTIVO_TELEGRAM = "telegram cambiado"
MOTIVO_REGISTRO = "registro no aprobado"

MSG_INACTIVO = "El usuario está inactivo: no puede tener enlace del informe."
MSG_REGISTRO = "El registro del usuario no está aprobado."
MSG_SIN_CEDULA = "El usuario no tiene una cédula aprobada."
MSG_SIN_TELEGRAM = "El usuario no tiene Telegram vinculado."
MSG_SIN_URL = (
    "Falta configurar MOTORED_PUBLIC_URL: no se puede armar el enlace del "
    "informe.")


class EnlaceNoPermitido(ValueError):
    """The usuario cannot hold a link (HTTP 422)."""


class FaltaConfiguracion(RuntimeError):
    """A required setting is empty (HTTP 409)."""


@dataclass(frozen=True)
class Huella:
    """The usuario fields an active link depends on."""

    activo: bool
    status: Optional[str]
    cedula: Optional[str]
    cedula_aprobada: bool
    telegram_id: Optional[int]


def huella(usuario: Usuario) -> Huella:
    return Huella(
        activo=bool(usuario.activo),
        status=usuario.status,
        cedula=usuario.cedula,
        cedula_aprobada=bool(usuario.cedula_aprobada),
        telegram_id=usuario.telegram_id,
    )


def motivo_no_permitido(usuario) -> Optional[str]:
    """Why `usuario` (a `Usuario` or a `Huella`) cannot hold a link; None
    when it can."""
    if not usuario.activo:
        return MSG_INACTIVO
    if (usuario.status or "approved") != "approved":
        return MSG_REGISTRO
    if not (usuario.cedula and usuario.cedula_aprobada):
        return MSG_SIN_CEDULA
    if usuario.telegram_id is None:
        return MSG_SIN_TELEGRAM
    return None


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


async def link_activo(db, usuario_id) -> Optional[ReporteAsesorLink]:
    stmt = select(ReporteAsesorLink).where(
        ReporteAsesorLink.usuario_id == usuario_id,
        ReporteAsesorLink.revocado_en.is_(None),
    )
    return (await db.execute(stmt)).scalars().first()


async def anular_link(db, usuario_id, motivo: str) -> None:
    """Revoke the usuario's active link, if any (one UPDATE)."""
    await db.execute(
        update(ReporteAsesorLink)
        .where(
            ReporteAsesorLink.usuario_id == usuario_id,
            ReporteAsesorLink.revocado_en.is_(None),
        )
        .values(revocado_en=_ahora(), motivo_revocacion=motivo)
    )


async def generar_link(
    db, usuario: Usuario, admin_id: Optional[uuid.UUID],
) -> ReporteAsesorLink:
    """Revoke any active link and add a new one. Not committed: the caller
    commits only once Lore delivered it, or rolls back."""
    motivo = motivo_no_permitido(usuario)
    if motivo is not None:
        raise EnlaceNoPermitido(motivo)
    await anular_link(db, usuario.id, MOTIVO_REGENERADO)
    link = ReporteAsesorLink(
        id=uuid.uuid4(),
        usuario_id=usuario.id,
        cedula=usuario.cedula,
        token=secrets.token_urlsafe(TOKEN_BYTES),
        creado_en=_ahora(),
        creado_por=admin_id,
        intentos_fallidos=0,
    )
    db.add(link)
    return link


def _motivo_cambio(antes: Huella, ahora: Huella) -> str:
    if not ahora.activo:
        return MOTIVO_DESACTIVADO
    if (antes.cedula, antes.cedula_aprobada) != (
            ahora.cedula, ahora.cedula_aprobada):
        return MOTIVO_CEDULA
    if antes.telegram_id != ahora.telegram_id:
        return MOTIVO_TELEGRAM
    return MOTIVO_REGISTRO


async def revocar_si_cambio(db, usuario: Usuario, antes: Huella) -> bool:
    """Revoke the active link when `usuario` could hold one before the
    change (`antes`) and any field it depends on changed. A usuario that
    could not hold one has no active link, so no query runs."""
    ahora = huella(usuario)
    if motivo_no_permitido(antes) is not None or ahora == antes:
        return False
    await anular_link(db, usuario.id, _motivo_cambio(antes, ahora))
    return True


async def revocar_por_telegram_nuevo(db, usuario: Usuario) -> bool:
    """A one-time code just linked a NEW Telegram to `usuario` (the bot
    refuses a Telegram already in use), so any link it held is stale."""
    if not usuario.cedula_aprobada:
        return False
    await anular_link(db, usuario.id, MOTIVO_TELEGRAM)
    return True


def base_publica() -> str:
    base = (settings.MOTORED_PUBLIC_URL or "").strip().rstrip("/")
    if not base:
        raise FaltaConfiguracion(MSG_SIN_URL)
    return base


def url_del_link(token: str) -> str:
    return f"{base_publica()}{RUTA_PUBLICA}{token}"


def texto_mensaje(nombre: str, url: str) -> str:
    return (
        f"Hola {nombre}, este es tu enlace personal al informe de ventas y "
        "comisión. Ábrelo y escribe tu cédula para verlo: "
        f"{url}\nNo lo compartas."
    )


def _iso(valor: Optional[datetime]) -> Optional[str]:
    return valor.isoformat() if valor is not None else None


def estado(link: Optional[ReporteAsesorLink]) -> dict:
    """What the ADMIN sees: never the token nor the URL."""
    if link is None:
        return {"activo": False, "creado_en": None, "ultimo_acceso_en": None}
    return {
        "activo": True,
        "creado_en": _iso(link.creado_en),
        "ultimo_acceso_en": _iso(link.ultimo_acceso_en),
    }
