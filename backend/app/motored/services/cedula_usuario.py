"""
Motored -- the usuario's cédula: the link Telegram -> usuario -> vendedor
master that the daily asesor report relies on
(odd/motored-reporte-diario-asesor, T1).

Every path goes through `validar_cedula`:

- Lore self-registration stores the cédula PENDING (`para_aprobar=False`):
  only the format is enforced. A cédula no active vendedor holds is still
  stored; Gestión de usuarios flags it (`cedulas_en_maestro`) and the bot
  never tells the asesor whether it was found.
- An ADMIN set/edit (`fijar_por_admin`) and an ADMIN approval (`aprobar`)
  use `para_aprobar=True`: an ACTIVE vendedor must hold the cédula (several
  vendedor rows may share it, any active one counts) and no OTHER approved
  usuario may hold it. Pending holders never block an approval, so an
  impostor cannot lock the real owner out.

The partial unique index `uq_usuario_cedula_aprobada` backs the last rule
when two approvals race. Personal data (Ley 1581): the value is never
logged, and `enmascarar` hides all but the last 4 digits for audit rows.
"""
import uuid
from dataclasses import dataclass
from typing import Iterable, Optional, Set

from sqlalchemy import select

from app.motored.models.usuario import Usuario
from app.motored.models.vendedor import Vendedor
from app.motored.schemas.vendedor import limpiar_cedula

CEDULA_MAX_DIGITOS = 20
INDICE_UNICO = "uq_usuario_cedula_aprobada"
MSG_NO_EN_MAESTRO = (
    "La cédula no corresponde a ningún vendedor activo del maestro de "
    "Vendedores."
)
MSG_SIN_PENDIENTE = "El usuario no tiene una cédula pendiente de aprobación."
MSG_CHOQUE = "La cédula ya está aprobada para otro usuario."


class CedulaInvalida(ValueError):
    """Bad format, or not held by an active vendedor (HTTP 422)."""


class CedulaDuplicada(Exception):
    """Another usuario already holds the cédula approved (HTTP 409)."""


class CedulaSinPendiente(Exception):
    """Approve/reject with no pending cédula on the usuario (HTTP 409)."""


@dataclass(frozen=True)
class CedulaValidada:
    cedula: str
    en_maestro: bool


def normalizar_cedula(valor) -> str:
    """Same cleaning as the vendedor master, plus the column's length."""
    try:
        cedula = limpiar_cedula(valor)
    except ValueError as exc:
        raise CedulaInvalida(str(exc)) from exc
    if len(cedula) > CEDULA_MAX_DIGITOS:
        raise CedulaInvalida(
            f"La cédula no puede tener más de {CEDULA_MAX_DIGITOS} dígitos")
    return cedula


def enmascarar(cedula: Optional[str]) -> Optional[str]:
    if not cedula:
        return None
    if len(cedula) <= 4:
        # A short value would be shown whole; hide every digit.
        return "*" * len(cedula)
    return "*" * (len(cedula) - 4) + cedula[-4:]


async def _vendedor_activo(db, cedula: str) -> bool:
    stmt = (
        select(Vendedor.id)
        .where(Vendedor.cedula == cedula, Vendedor.activo.is_(True))
        .limit(1)
    )
    return (await db.execute(stmt)).scalars().first() is not None


async def _otro_aprobado(db, cedula: str, usuario_id) -> Optional[str]:
    stmt = (
        select(Usuario.nombre)
        .where(
            Usuario.cedula == cedula,
            Usuario.cedula_aprobada.is_(True),
            Usuario.id != usuario_id,
        )
        .limit(1)
    )
    return (await db.execute(stmt)).scalars().first()


async def validar_cedula(
    db, valor, usuario_id: uuid.UUID, *, para_aprobar: bool,
) -> CedulaValidada:
    """The single validation used by Lore, ADMIN set and ADMIN approve."""
    cedula = normalizar_cedula(valor)
    en_maestro = await _vendedor_activo(db, cedula)
    if not para_aprobar:
        return CedulaValidada(cedula, en_maestro)
    if not en_maestro:
        raise CedulaInvalida(MSG_NO_EN_MAESTRO)
    otro = await _otro_aprobado(db, cedula, usuario_id)
    if otro is not None:
        raise CedulaDuplicada(
            f"La cédula ya está aprobada para el usuario {otro}.")
    return CedulaValidada(cedula, en_maestro)


async def fijar_por_admin(db, usuario: Usuario, valor) -> None:
    """ADMIN set/edit: validated as an approval and approved directly."""
    validada = await validar_cedula(db, valor, usuario.id, para_aprobar=True)
    usuario.cedula = validada.cedula
    usuario.cedula_aprobada = True


async def aprobar(db, usuario: Usuario) -> None:
    if not usuario.cedula:
        raise CedulaSinPendiente(MSG_SIN_PENDIENTE)
    await validar_cedula(db, usuario.cedula, usuario.id, para_aprobar=True)
    usuario.cedula_aprobada = True


def rechazar(usuario: Usuario) -> None:
    """Reject a PENDING cédula: it is cleared, the asesor can be asked
    again. An approved one is removed with `quitar` instead."""
    if not usuario.cedula or usuario.cedula_aprobada:
        raise CedulaSinPendiente(MSG_SIN_PENDIENTE)
    quitar(usuario)


def quitar(usuario: Usuario) -> None:
    usuario.cedula = None
    usuario.cedula_aprobada = False


async def cedulas_en_maestro(db, cedulas: Iterable[str]) -> Set[str]:
    """Which of `cedulas` an active vendedor holds (one query)."""
    buscadas = sorted({c for c in cedulas if c})
    if not buscadas:
        return set()
    stmt = select(Vendedor.cedula).where(
        Vendedor.cedula.in_(buscadas), Vendedor.activo.is_(True))
    return set((await db.execute(stmt)).scalars().all())


def es_choque_unico(exc: Exception) -> bool:
    return INDICE_UNICO in str(getattr(exc, "orig", exc))
