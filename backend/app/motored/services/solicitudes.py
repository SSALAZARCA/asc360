"""
Motored Pedidos — servicio de aprobación de solicitudes de registro
(sdd/motored-ventas-perdidas-bot, Phase 4 "Approval service + Usuarios UI",
design D5 "Registration, auth, dual-channel approval").

`resolver_solicitud` es la ÚNICA función que transiciona `Usuario.status`
de `pending` a `approved`/`rejected` -- tanto la pantalla web Usuarios
(`POST /api/motored/usuarios/{id}/aprobar|rechazar`, este Phase) como los
botones inline de aprobación del bot Lore (`POST /admin/solicitudes/{id}/
aprobar|rechazar`, Fase 5) DEBEN llamar a esta misma función -- design D5
es explícito: "Web: ... call the SAME function" -- nunca una segunda
implementación de la transición en el router del bot.

Mismo patrón de claim atómico que `services/demanda_perdida_bot.py::
_reclamar_anulacion` y, más atrás, `services/trabajos/supervisor.py::
_claim_by_id`: un `UPDATE ... WHERE status='pending' AND activo ...
RETURNING id` es la única barrera común contra dos resoluciones
concurrentes de la MISMA solicitud (doble-click en la web, o un tap de
Telegram y un click web casi simultáneos -- spec "Racing approval and
rejection resolve to one terminal state") -- quien pierde el claim ve 0
filas afectadas y levanta `SolicitudYaResuelta` ANTES de leer o escribir
cualquier otra cosa.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.models.usuario import Usuario


class SolicitudYaResuelta(Exception):
    """La solicitud ya no estaba `pending` (o el usuario ya no está
    `activo`, o el id no existe) en el momento del claim atómico -- ver el
    docstring del módulo. Excepción de dominio propia, traducida a
    `HTTPException(409)` en la capa de API (nunca levantada directamente
    contra el cliente), mismo criterio que `CargaYaAnuladaError`. No
    distingue "ya resuelta" de "id inexistente" -- ambos casos fallan la
    MISMA claúsula `WHERE status='pending'`, igual que
    `_reclamar_anulacion` no distingue "ya anulada" de "id inexistente"."""


class UsuarioNoEncontradoTrasClaim(Exception):
    """El claim atómico afectó una fila (0 filas NO fue lo que devolvió),
    pero el SELECT posterior no encontró ningún `Usuario` con ese id --
    post-Phase-4 review, finding #3. Hoy es inalcanzable en la práctica (no
    existe un camino de hard-delete para `Usuario`), pero
    `resolver_solicitud` es código COMPARTIDO que Fase 5 también llamará
    desde el router del bot, así que este caso debe fallar RUIDOSAMENTE
    ACÁ -- ANTES de que `_resolver_solicitud_endpoint` (o cualquier otro
    caller) haga `commit()` -- en vez de devolver `None` en silencio y
    dejar que el caller comitee la transición de estado y recién después
    reviente con un `pydantic.ValidationError` opaco al intentar construir
    una respuesta a partir de `None`."""


async def resolver_solicitud(
    db: AsyncSession,
    usuario_id: uuid.UUID,
    decision: str,
    actor_id: uuid.UUID,
) -> Usuario:
    """`decision` es el valor FINAL de `status` (`"approved"` o
    `"rejected"`) -- el caller (la ruta `/aprobar` vs `/rechazar`, web o
    bot) ya sabe cuál es un literal fijo de SU propio código, nunca un
    valor tomado del usuario final, así que esta función no valida el
    conjunto de valores posibles.

    Claim atómico (design D5): `UPDATE usuario SET status=:decision,
    resuelto_por=:actor_id, resuelto_en=:ahora WHERE id=:usuario_id AND
    status='pending' AND activo RETURNING id`. 0 filas afectadas -> la
    solicitud ya fue resuelta (por el otro canal, o dos veces desde el
    mismo), o el id no existe, o el usuario fue desactivado mientras
    estaba pendiente -> `SolicitudYaResuelta`.

    Devuelve la fila `Usuario` ya actualizada (re-consultada después del
    claim, mismo criterio en dos pasos que `anular_registro_bot`/
    `_reclamar_anulacion`: primero se gana el claim, después se lee todo
    lo demás que se necesite)."""
    ahora = datetime.utcnow()
    claim = await db.execute(
        update(Usuario)
        .where(
            Usuario.id == usuario_id,
            Usuario.status == "pending",
            Usuario.activo.is_(True),
        )
        .values(status=decision, resuelto_por=actor_id, resuelto_en=ahora)
        .returning(Usuario.id)
    )
    if claim.scalars().first() is None:
        raise SolicitudYaResuelta(f"La solicitud del usuario {usuario_id} ya fue resuelta.")

    result = await db.execute(select(Usuario).where(Usuario.id == usuario_id))
    usuario = result.scalars().first()
    if usuario is None:
        # Ver `UsuarioNoEncontradoTrasClaim` -- se levanta ACÁ, antes de que
        # cualquier caller llegue a su propio `db.commit()`.
        raise UsuarioNoEncontradoTrasClaim(
            f"El claim de la solicitud del usuario {usuario_id} afectó una "
            "fila, pero no se encontró esa fila al releerla."
        )
    # Sincroniza en memoria lo que el UPDATE ya escribió (mismo criterio
    # que `_reclamar_anulacion` sincroniza `carga.estado` tras su propio
    # claim atómico) -- redundante contra una base real (el SELECT ya lee
    # la fila post-UPDATE dentro de la misma transacción), pero es lo que
    # hace que este resultado sea confiable también contra un
    # `FakeAsyncSession` de test, que nunca aplica un `UPDATE` de verdad.
    usuario.status = decision
    usuario.resuelto_por = actor_id
    usuario.resuelto_en = ahora
    return usuario
