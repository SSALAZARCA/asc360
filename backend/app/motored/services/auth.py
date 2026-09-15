"""
Motored Pedidos — resolución REAL del usuario autenticado (sdd/motored-
pedidos-cimientos, Fase 3, ADR-2). Reemplaza el seam `_unwired_user_lookup`
de la Fase 2 (`app/motored/deps.py`), que fallaba cerrado con 503 porque la
tabla `usuario` todavía no existía. Ahora que el modelo `Usuario` existe
(task 3.1), esta es la consulta ORM real: `usuario` + sus filas
`usuario_sucursal` (para poblar `MotoredUser.sucursal_ids`, requerido por el
scoping server-side del rol `SUCURSAL`).

`MotoredUser` vive AQUÍ (no en `deps.py`) a propósito: `deps.py` depende de
este módulo (`Depends(get_motored_db_or_503)` para poder consultar la BD),
así que si `MotoredUser` viviera en `deps.py` se produciría un import
circular. `deps.py` re-exporta `MotoredUser` con
`from app.motored.services.auth import MotoredUser`, así que
`from app.motored.deps import MotoredUser` (usado por los tests de la Fase
2) sigue funcionando sin cambios.
"""
import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.motored.models.usuario import Usuario


@dataclass
class MotoredUser:
    """Resultado de `get_current_motored_user`. Independiente del modelo
    ORM `Usuario` -- solo lleva lo que las dependencias de autorización
    necesitan."""

    user_id: str
    role: str
    sucursal_ids: List[str] = field(default_factory=list)
    activo: bool = True


MotoredUserLookup = Callable[[str], Awaitable[Optional[MotoredUser]]]


async def obtener_usuario_motored(db: AsyncSession, user_id: str) -> Optional[MotoredUser]:
    """Consulta real: `usuario` por PK, con sus `usuario_sucursal` cargadas
    (`selectinload`) para poblar `sucursal_ids`. `user_id` llega como texto
    desde el claim `sub` del JWT -- un valor no-UUID es simplemente "no
    encontrado", nunca un error 500."""
    try:
        uid = uuid.UUID(str(user_id))
    except (ValueError, TypeError, AttributeError):
        return None

    result = await db.execute(
        select(Usuario).options(selectinload(Usuario.sucursales)).where(Usuario.id == uid)
    )
    usuario = result.scalars().first()
    if usuario is None:
        return None

    role_value = usuario.role.value if hasattr(usuario.role, "value") else usuario.role
    sucursal_ids = [str(rel.sucursal_id) for rel in (usuario.sucursales or [])]

    return MotoredUser(
        user_id=str(usuario.id),
        role=role_value,
        sucursal_ids=sucursal_ids,
        activo=usuario.activo,
    )


def crear_lookup_real(db: AsyncSession) -> MotoredUserLookup:
    """Fábrica: liga la consulta real a la sesión de ESTA request. Es lo que
    `app/motored/deps.py::get_motored_user_lookup` retorna ahora que
    `usuario` existe -- reemplaza por completo el seam
    `_unwired_user_lookup` de la Fase 2."""

    async def _lookup(user_id: str) -> Optional[MotoredUser]:
        return await obtener_usuario_motored(db, user_id)

    return _lookup
