"""
Motored Pedidos — router del bot Lore, auto-registro y aprobación admin
(sdd/motored-ventas-perdidas-bot, Phase 5 "Bot auth + core router", design
D5).

Monta `/api/motored/bot/*` -- la superficie HTTP que un futuro proceso Lore
(`lore-bot/`, Fase 9) llamará. Este Phase NO incluye ningún proceso de bot
de Telegram; es únicamente el backend que ese proceso consumirá, autenticado
por secreto compartido (`deps_bot.py`), nunca por el JWT de `deps.py` (el
bot Lore no tiene ni emite JWTs de Motored).

`POST /admin/vincular` y `POST /admin/solicitudes/{id}/aprobar|rechazar`
delegan TODA su lógica de dominio en funciones ya construidas y probadas en
Fase 4 (`services/vinculacion.py::consumir_codigo_vinculacion`,
`services/solicitudes.py::resolver_solicitud`) -- la MISMA `resolver_
solicitud` que la pantalla web Usuarios ya llama (design D5: nunca una
segunda implementación de la transición). El `actor_id` que se le pasa
viene SIEMPRE de `require_bot_admin` (resuelto vía `telegram_id` -> `Usuario`
real, verificado role=ADMIN + status=approved + activo) -- NUNCA de un id
en el cuerpo del request, porque este router es el primer llamador de
`resolver_solicitud` que no tiene un JWT autenticado detrás.

Fix-up finding #6 (CRITICAL): la superficie de Phase 6 "Demanda perdida —
bot write path" (`/referencias/resolver`, `/demanda-perdida`, `/demanda-
perdida/hoy`, `PATCH .../lineas/{id}`, `POST .../{carga_id}/anular`) vivía
acá mismo, haciendo de este archivo ~850 líneas con 2 concerns sin relación
entre sí. Se movió a su propio router, `api/bot_demanda_perdida.py`
(mismo prefix `/bot`, mismas dependencias de disponibilidad, montado por
separado en `router.py`) -- ver el docstring de ese módulo para el detalle
completo. Puro reordenamiento de archivos, sin cambio de comportamiento."""
from __future__ import annotations

import re
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.limiter import limiter
from app.motored.deps import get_motored_db_or_503, require_motored_ready
from app.motored.deps_bot import (
    BotActor,
    get_bot_actor,
    get_bot_telegram_id,
    require_bot_admin,
    require_lore_ready,
)
from app.motored.models.sucursal import Sucursal
from app.motored.models.usuario import MotoredRole, Usuario
from app.motored.models.usuario_sucursal import UsuarioSucursal
from app.motored.services import solicitudes, vinculacion

router = APIRouter(
    prefix="/bot",
    tags=["motored-bot"],
    dependencies=[Depends(require_motored_ready), Depends(require_lore_ready)],
)

_PHONE_PATTERN = re.compile(r"^\d{7,15}$")


class RegistroBotRequest(BaseModel):
    nombre: str
    phone: str
    sucursal_id: uuid.UUID

    @field_validator("nombre")
    @classmethod
    def _nombre_minimo(cls, value: str) -> str:
        if len(value.strip()) < 3:
            raise ValueError("nombre debe tener al menos 3 caracteres")
        return value

    @field_validator("phone")
    @classmethod
    def _phone_solo_digitos(cls, value: str) -> str:
        if not _PHONE_PATTERN.fullmatch(value):
            raise ValueError("phone debe tener entre 7 y 15 dígitos")
        return value


class VincularBotRequest(BaseModel):
    codigo: str


def _role_value(usuario: Usuario) -> str:
    return usuario.role.value if hasattr(usuario.role, "value") else usuario.role


@router.get("/yo")
async def yo(actor: Optional[BotActor] = Depends(get_bot_actor)) -> dict:
    """El bot consulta quién es (asesor o admin) el `telegram_id` que le
    está hablando -- 404 si ese `telegram_id` no tiene ningún `Usuario`
    todavía (el caso esperado antes de `/registro`)."""
    if actor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "NO_REGISTRADO"})
    return {
        "id": actor.usuario_id,
        "nombre": actor.nombre,
        "role": actor.role,
        "status": actor.status,
        "activo": actor.activo,
        "sucursales": actor.sucursal_ids,
    }


@router.get("/sucursales")
async def sucursales_activas(
    _telegram_id: int = Depends(get_bot_telegram_id),
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> List[dict]:
    """Picker de sucursales para el flujo de auto-registro del bot -- solo
    valida el secreto compartido (no requiere que el `telegram_id` ya
    tenga un `Usuario`, design D5: "secret, no actor")."""
    result = await db.execute(select(Sucursal).where(Sucursal.activa.is_(True)))
    return [{"id": str(s.id), "nombre": s.nombre} for s in result.scalars().all()]


@router.post("/registro", status_code=status.HTTP_201_CREATED)
async def registrarse(
    payload: RegistroBotRequest,
    telegram_id: int = Depends(get_bot_telegram_id),
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> dict:
    """Auto-registro (spec "Self-registration with status-aware re-entry"):
    crea un `Usuario` `pending` con rol `ASESOR_MOSTRADOR` + su vínculo
    `usuario_sucursal`. 409 si el `telegram_id` ya tiene un `Usuario`
    (cualquier rol/status) -- el flujo de re-entrada (`GET /yo`) es lo que
    el bot debe usar en ese caso, no un segundo `/registro`.

    El `SELECT` de arriba es un fast-path de cortesía, NO una garantía
    (post-review fix #1, BLOCKER): dos llamadas casi simultáneas con el
    MISMO `telegram_id` pueden pasar ambas ese chequeo antes de que
    cualquiera haga `commit()` -- la segunda viola de verdad
    `uq_usuario_telegram_id`. Separadamente, un `sucursal_id` que no existe
    (o que se desactivó entre `GET /sucursales` y esta llamada) viola la FK
    de `UsuarioSucursal`. Ambos casos son un `IntegrityError` real de
    Postgres en el `commit()`, nunca antes -- se traducen acá al mismo 4xx
    limpio que ya devuelve el chequeo secuencial, en vez de dejar escapar
    un 500 sin manejar (mismo criterio que `app/api/v1/vehicle_models.py`/
    `parts_manual.py::create_reference`)."""
    existing = await db.execute(select(Usuario).where(Usuario.telegram_id == telegram_id))
    if existing.scalars().first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "YA_REGISTRADO"})

    usuario = Usuario(
        id=uuid.uuid4(),
        nombre=payload.nombre,
        role=MotoredRole.ASESOR_MOSTRADOR,
        activo=True,
        status="pending",
        telegram_id=telegram_id,
        phone=payload.phone,
    )
    db.add(usuario)
    db.add(UsuarioSucursal(id=uuid.uuid4(), usuario_id=usuario.id, sucursal_id=payload.sucursal_id))
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if "uq_usuario_telegram_id" in str(exc.orig):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "YA_REGISTRADO"})
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail={"code": "SUCURSAL_NO_ENCONTRADA"}
        )

    admin_ids_result = await db.execute(
        select(Usuario.telegram_id).where(
            Usuario.role == MotoredRole.ADMIN,
            Usuario.telegram_id.is_not(None),
            Usuario.activo.is_(True),
        )
    )
    admin_telegram_ids = admin_ids_result.scalars().all()

    return {
        "usuario": {
            "id": str(usuario.id),
            "nombre": usuario.nombre,
            "role": _role_value(usuario),
            "status": usuario.status,
        },
        "admin_telegram_ids": list(admin_telegram_ids),
    }


@router.post("/admin/vincular")
@limiter.limit("5/minute")
async def vincular_admin(
    request: Request,
    payload: VincularBotRequest,
    telegram_id: int = Depends(get_bot_telegram_id),
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> dict:
    """Consume el código de un solo uso generado por `POST /usuarios/me/
    telegram/codigo` (Fase 4) -- delega TODA la lógica de hashing/expiración
    /single-use en `services/vinculacion.py::consumir_codigo_vinculacion`,
    ya construida y probada en Fase 4 exactamente para este endpoint (ver el
    docstring de ese módulo). El chequeo de "409 si el telegram_id ya está
    vinculado" vive ACÁ (no dentro del claim atómico de `consumir_codigo_
    vinculacion`, que solo sabe de códigos): sin él, un `telegram_id` ya
    vinculado a OTRO `Usuario` violaría en silencio `uq_usuario_telegram_id`
    contra una base real.

    Ese pre-chequeo secuencial NO cubre la carrera real (post-review fix #2,
    BLOCKER, un nivel más abajo): dos llamadas `/vincular` concurrentes
    presentando dos códigos DISTINTOS, ambos todavía vigentes, para el MISMO
    `telegram_id` sin vincular, pasan las DOS el chequeo de arriba (ninguna
    ve el `telegram_id` vinculado todavía). El claim atómico de `consumir_
    codigo_vinculacion` está scoped por `codigo_vinculacion_hash`, no por
    `telegram_id` -- así que las DOS pueden ganar su propio claim, y el
    SEGUNDO `UPDATE ... SET telegram_id=...` viola de verdad `uq_usuario_
    telegram_id` DENTRO de esa función. El `except IntegrityError` de abajo
    es el backstop real contra esa carrera, traduciendo al MISMO 409 que el
    pre-chequeo ya usa para el caso simple -- sin necesitar rediseñar el
    claim de `vinculacion.py`."""
    ya_usado = await db.execute(select(Usuario).where(Usuario.telegram_id == telegram_id))
    if ya_usado.scalars().first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={"code": "TELEGRAM_YA_VINCULADO"}
        )

    try:
        usuario = await vinculacion.consumir_codigo_vinculacion(db, payload.codigo, telegram_id)
    except vinculacion.CodigoVinculacionInvalidoError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "CODIGO_INVALIDO"})
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={"code": "TELEGRAM_YA_VINCULADO"}
        )

    await db.commit()
    return {"id": str(usuario.id), "nombre": usuario.nombre, "role": _role_value(usuario)}


async def _resolver_solicitud_bot(
    db: AsyncSession, usuario_id: uuid.UUID, decision: str, actor: BotActor
) -> dict:
    """Compartido por `/aprobar` y `/rechazar` -- delega TODA la lógica de
    transición en `services/solicitudes.py::resolver_solicitud`, la MISMA
    función que `api/usuarios.py`'s `/aprobar|/rechazar` web ya llama
    (design D5: nunca una segunda implementación acá). `actor_id` viene
    SIEMPRE de `actor.usuario_id` -- el `Usuario` real resuelto por
    `require_bot_admin` a partir del `telegram_id` del que está tocando el
    botón, NUNCA de un id en el cuerpo del request (este endpoint no
    recibe ninguno)."""
    try:
        usuario = await solicitudes.resolver_solicitud(
            db, usuario_id, decision, uuid.UUID(actor.usuario_id)
        )
    except solicitudes.SolicitudYaResuelta:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "YA_RESUELTA"})

    await db.commit()
    return {
        "usuario_id": str(usuario.id),
        "status": usuario.status,
        "nombre": usuario.nombre,
        "telegram_id_solicitante": usuario.telegram_id,
    }


@router.post("/admin/solicitudes/{usuario_id}/aprobar")
async def aprobar_solicitud_bot(
    usuario_id: uuid.UUID,
    actor: BotActor = Depends(require_bot_admin),
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> dict:
    return await _resolver_solicitud_bot(db, usuario_id, "approved", actor)


@router.post("/admin/solicitudes/{usuario_id}/rechazar")
async def rechazar_solicitud_bot(
    usuario_id: uuid.UUID,
    actor: BotActor = Depends(require_bot_admin),
    db: AsyncSession = Depends(get_motored_db_or_503),
) -> dict:
    return await _resolver_solicitud_bot(db, usuario_id, "rejected", actor)

