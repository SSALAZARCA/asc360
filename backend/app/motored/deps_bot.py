"""
Motored Pedidos — bot Lore: autenticación por secreto compartido y
resolución de actor (sdd/motored-ventas-perdidas-bot, Phase 5 "Bot auth +
core router", design D5).

Deliberadamente AISLADO de `deps.py` (JWT, roles ADMIN/COMPRAS/SUCURSAL/
CONSULTA): el bot Lore NUNCA emite ni valida un JWT de Motored. Cada
llamada del bot trae un secreto compartido (`X-Lore-Secret`) más el
`telegram_id` de quien le está hablando al bot (`X-Lore-Telegram-Id`), y
`get_bot_actor` resuelve QUIÉN es ese `telegram_id` contra la base de
datos EN CADA LLAMADA -- ADR-2 (nunca solo-claims, nunca cacheado
server-side), el mismo criterio que `get_current_motored_user` aplica a su
JWT.

`LORE_BOT_SECRET` es un secreto PROPIO, distinto de `SONIA_BOT_SECRET`
(constraint del proyecto: Lore no comparte código/secretos/tokens con
Sonia/UM) y también distinto de `MOTORED_SECRET_KEY`/`SECRET_KEY` (mismo
criterio fail-closed que `motored_secret_is_safe()` en `app/motored/
auth.py`). Ese guard vive DIRECTAMENTE acá (no en un módulo hermano
separado, a diferencia de `MotoredUser`/`services/auth.py`): no hay riesgo
de import circular como el que forzó esa separación, porque `deps_bot.py`
es una hoja nueva que depende de `deps.py` (para `get_motored_db_or_503`),
nunca al revés.

ADR-4 (fail-closed sin tumbar el proceso compartido): una mala
configuración de Lore (`LORE_BOT_SECRET` vacío o inseguro) responde 503
LORE_UNAVAILABLE en la request afectada -- jamás un crash de arranque del
`backend` compartido. Esto es una desviación DELIBERADA de la redacción
literal del spec ("backend startup fails"); ver design D5, que ya deja
esto como open question para el dueño del spec.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Tuple

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.core.security import verify_sonia_secret as verify_shared_secret
from app.motored.deps import get_motored_db_or_503
from app.motored.models.usuario import Usuario

LORE_UNAVAILABLE_DETAIL = {"code": "LORE_UNAVAILABLE"}

# Máximo de un `BigInteger` con signo de Postgres (columna real de
# `Usuario.telegram_id`) -- post-review fix #3: `int(x_lore_telegram_id)`
# nunca levanta por sí solo para un valor arbitrariamente grande (los
# enteros de Python no tienen límite), pero ese valor SÍ rompe en algún
# punto río abajo (la consulta de `get_bot_actor` o el chequeo de duplicado
# de `/registro`) con un error de encoding/driver sin manejar -- un 500, no
# el 400 limpio que el docstring de `get_bot_telegram_id` promete. Un
# `telegram_id` real de Telegram tampoco es nunca negativo ni cero.
_TELEGRAM_ID_MAXIMO = 9223372036854775807


def lore_bot_secret_is_safe() -> bool:
    """True solo si `LORE_BOT_SECRET` no está vacío Y es distinto de
    `SONIA_BOT_SECRET`, `MOTORED_SECRET_KEY` y `SECRET_KEY` -- constraint
    del proyecto (Lore no comparte secretos con Sonia/UM ni con el resto
    de Motored/asc360). Reutilizada por `require_lore_ready`."""
    secret = settings.LORE_BOT_SECRET
    if not secret:
        return False
    return secret not in (
        settings.SONIA_BOT_SECRET,
        settings.MOTORED_SECRET_KEY,
        settings.SECRET_KEY,
    )


async def require_lore_ready() -> None:
    """503 LORE_UNAVAILABLE si `LORE_BOT_SECRET` está vacío o es inseguro
    -- NUNCA un crash de arranque (ver docstring del módulo). Se usa como
    dependencia a nivel de router del bot, junto a `require_motored_ready`
    (que ya cubre el apagado general del módulo Motored)."""
    if not lore_bot_secret_is_safe():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=LORE_UNAVAILABLE_DETAIL,
        )


async def get_bot_telegram_id(
    x_lore_secret: Optional[str] = Header(None),
    x_lore_telegram_id: Optional[str] = Header(None),
) -> int:
    """Valida el secreto compartido -- `app.core.security.verify_sonia_
    secret` es, pese al nombre, un comparador GENÉRICO resistente a timing
    attacks (`hmac.compare_digest`) sin nada Sonia-específico en su
    implementación; se reutiliza acá bajo el alias local `verify_shared_
    secret` (post-review fix #6) en vez de duplicarlo, precisamente para
    que ESTE módulo nunca lea/mencione "sonia" en su propio código -- el
    nombre real de la función en `security.py` queda sin tocar para no
    arrastrar el rename a los ~7 call sites de Sonia fuera de Motored (gga
    bloqueó ese rename cross-cutting por deuda preexistente masiva, ajena a
    este cambio, en esos archivos). Y parsea `X-Lore-Telegram-Id` como
    entero. Un secreto que no matchea (incluido ausente) es 401; un id no
    numérico (incluido ausente), fuera del rango de un `BigInteger` con
    signo (post-review fix #3 -- `int()` de Python no tiene límite
    superior, pero la columna real sí), negativo o cero es 400. Nunca un
    500."""
    if not verify_shared_secret(x_lore_secret, settings.LORE_BOT_SECRET):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "SECRETO_INVALIDO"},
        )
    try:
        telegram_id = int(x_lore_telegram_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "TELEGRAM_ID_INVALIDO"},
        )
    if not (1 <= telegram_id <= _TELEGRAM_ID_MAXIMO):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "TELEGRAM_ID_INVALIDO"},
        )
    return telegram_id


@dataclass
class BotActor:
    """Resultado de `get_bot_actor` -- análogo a `MotoredUser` (`services/
    auth.py`), pero resuelto por `telegram_id`, no por el claim `sub` de un
    JWT (el bot Lore no emite JWTs)."""

    usuario_id: str
    nombre: str
    role: str
    status: str
    activo: bool
    telegram_id: int
    sucursal_ids: List[str] = field(default_factory=list)


async def get_bot_actor(
    telegram_id: int = Depends(get_bot_telegram_id),
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> Optional[BotActor]:
    """Búsqueda REAL por `telegram_id` en CADA llamada -- nunca cacheada
    server-side (ADR-2), igual que `obtener_usuario_motored` hace por PK
    para el JWT. `None` significa "ningún `Usuario` tiene este
    `telegram_id` todavía" -- el caso esperado antes de completar
    `POST /registro`, no un error."""
    result = await db.execute(
        select(Usuario)
        .options(selectinload(Usuario.sucursales))
        .where(Usuario.telegram_id == telegram_id)
    )
    usuario = result.scalars().first()
    if usuario is None:
        return None

    role_value = usuario.role.value if hasattr(usuario.role, "value") else usuario.role
    sucursal_ids = [str(rel.sucursal_id) for rel in (usuario.sucursales or [])]
    return BotActor(
        usuario_id=str(usuario.id),
        nombre=usuario.nombre,
        role=role_value,
        # Mismo fallback que `obtener_usuario_motored` (services/auth.py):
        # una fila `Usuario(...)` armada a mano sin `status=` (fixtures de
        # test) tiene `status is None` a nivel Python, no el
        # `server_default` real de la base.
        status=usuario.status or "approved",
        activo=usuario.activo,
        telegram_id=telegram_id,
        sucursal_ids=sucursal_ids,
    )


def _require_bot_roles(roles: Iterable[str]):
    """Fábrica compartida por `require_bot_asesor`/`require_bot_admin`/
    `require_bot_asesor_o_admin`: las tres exigen exactamente la misma
    cascada de chequeos (existencia, rol, status, activo), difiriendo
    únicamente en QUÉ rol(es) aceptan -- evita duplicar los 4 códigos 403.
    Generalizada (post-Phase-10, pedido directo del dueño del producto: un
    ADMIN también puede registrar ventas perdidas) de "un único rol exacto"
    a "cualquiera de N roles", sin tocar el contrato de las dos fábricas
    single-role ya existentes.

    Fix-up finding #3 (SUGGESTION, resilience): un `roles` vacío bloquearía
    a CUALQUIER actor con el mismo 403 `NO_REGISTRADO` que un rol
    inexistente -- un error de uso silencioso y engañoso en tiempo de
    REQUEST. Falla fuerte acá, en tiempo de DEFINICIÓN de la fábrica (import
    time), en vez de eso."""
    roles_permitidos: Tuple[str, ...] = tuple(roles)
    if not roles_permitidos:
        raise ValueError("_require_bot_roles requiere al menos un rol permitido")

    async def _check(actor: Optional[BotActor] = Depends(get_bot_actor)) -> BotActor:
        if actor is None or actor.role not in roles_permitidos:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail={"code": "NO_REGISTRADO"}
            )
        if actor.status == "pending":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail={"code": "PENDIENTE"}
            )
        if actor.status == "rejected":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail={"code": "RECHAZADO"}
            )
        if not actor.activo:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail={"code": "INACTIVO"}
            )
        return actor

    return _check


require_bot_asesor = _require_bot_roles(("ASESOR_MOSTRADOR",))
require_bot_admin = _require_bot_roles(("ADMIN",))

# Ad-hoc addition (post-Phase-10, product-owner request, NOT a numbered SDD
# task): gates the demanda-perdida bot surface (`api/bot_demanda_perdida.py`)
# for EITHER role, now that an ADMIN can also register lost sales -- for a
# sucursal it picks explicitly, since (unlike an advisor) it has no
# `usuario_sucursal` rows of its own. See that router's `registrar_demanda_
# perdida` for the role-conditional sucursal-ownership check this pairs with.
require_bot_asesor_o_admin = _require_bot_roles(("ASESOR_MOSTRADOR", "ADMIN"))
