"""Shared rules for a Telegram account that several advisors share.

`GET /yo` lists every usuario of the calling Telegram under `asesores`. When
more than one of them is approved and active, Captura and Correccion ask
"¿Quién registra?" at the start of EVERY conversation; the choice lives only
in that conversation's `user_data` and travels as `x-lore-usuario-id`. The
backend still checks that the chosen usuario belongs to the Telegram — this
module only decides whether to ask and who is eligible.
"""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update

from lore.api import (
    BackendClient,
    LoreApiError,
    NoRegistrado,
    Pendiente,
    Rechazado,
)
from lore.handlers._common import _MSG_CONEXION, con_cancelar, responder

MSG_QUIEN_REGISTRA = "👤 ¿Quién registra?"
MSG_SIN_ASESOR_HABILITADO = (
    "⏳ Ningún asesor de esta cuenta está habilitado todavía. Contactá a un administrador."
)
MSG_ASESOR_NO_DISPONIBLE = "⚠️ Ese asesor ya no está disponible. Volvé a empezar."


def _candidatos(yo: dict) -> list[dict]:
    """Every usuario `/yo` reported; a legacy single-actor body counts as one."""
    return yo.get("asesores") or [yo]


def _es_utilizable(asesor: dict) -> bool:
    return asesor.get("status", "approved") == "approved" and asesor.get("activo", True)


def asesores_utilizables(yo: dict) -> list[dict]:
    return [a for a in _candidatos(yo) if _es_utilizable(a)]


def ninguno_habilitado(yo: dict) -> bool:
    """Several usuarios share this Telegram and none can act yet. A single
    usuario keeps the pre-existing flow (the backend answers its own status)."""
    candidatos = _candidatos(yo)
    return len(candidatos) > 1 and not asesores_utilizables(yo)


def actor_automatico(yo: dict) -> tuple[dict, str | None]:
    """The actor to use when no question needs asking, plus the usuario id to
    send. One usuario (or a legacy body) sends no id, exactly as before; when
    the Telegram has several usuarios but only one is usable, that one is
    named explicitly so a later approval mid-conversation cannot change who
    the conversation acts as."""
    candidatos = _candidatos(yo)
    if len(candidatos) == 1:
        return candidatos[0], None
    usables = asesores_utilizables(yo)
    if len(usables) == 1:
        return usables[0], usables[0]["id"]
    return yo, None


def teclado_asesores(prefijo: str, asesores: list[dict]) -> InlineKeyboardMarkup:
    filas = [
        [InlineKeyboardButton(a.get("nombre", "?"), callback_data=f"{prefijo}{a['id']}")]
        for a in asesores
    ]
    return con_cancelar(filas)


def buscar_asesor(opciones: dict, crudo: str) -> dict | None:
    """The tapped advisor, only if it was one of the options offered in THIS
    conversation; callback data is never trusted on its own."""
    return opciones.get(crudo)


async def verificar_actor(client: BackendClient, update: Update) -> dict | None:
    """Re-derives the actor via `client.yo()` on every entry, never assumed
    from a prior `/start` (the status could have changed since). Replies and
    returns `None` when the actor can't proceed; returns `/yo`'s body
    otherwise."""
    try:
        return await client.yo()
    except NoRegistrado:
        await responder(update, "No estás registrado todavía. Mandá /start para solicitar acceso.")
    except Pendiente:
        await responder(update, "⏳ Tu solicitud de acceso todavía está pendiente de aprobación.")
    except Rechazado:
        await responder(update, "❌ Tu solicitud de acceso fue rechazada. Contactá a un administrador.")
    except LoreApiError:
        # Every BackendClient method shares ONE global error-code map, so a
        # subclass not branched on above must still get a reply.
        await responder(update, _MSG_CONEXION)
    return None
