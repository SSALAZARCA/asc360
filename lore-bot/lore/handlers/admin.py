"""Admin-facing Telegram surface: `/vincular <codigo>` and the
Aprobar/Rechazar callback buttons pushed by `handlers/registro.py`
(design D5).

Authorization note (this project's own established pattern — "server is
the real gate"): the backend's `require_bot_admin` re-resolves the tapping
admin's `telegram_id` on every call. Neither `vincular_command` nor
`resolver_solicitud_callback` performs its own authorization check beyond
that — an unauthorized tap simply gets a `LoreApiError` back from the
backend, same as any other bot user.
"""
from __future__ import annotations

import logging
import uuid

from telegram import Update
from telegram.ext import ContextTypes

from lore.api import (
    BackendCaido,
    BackendClient,
    CodigoInvalido,
    LoreApiError,
    TelegramYaVinculado,
    YaResuelta,
)
from lore.handlers._common import _MSG_CONEXION

logger = logging.getLogger("lore.handlers.admin")

_MSG_SOLICITUD_INVALIDA = "⚠️ No pude procesar esta solicitud. Contactá a soporte."


def _cliente(telegram_id: int) -> BackendClient:
    """Same seam as `handlers/registro.py::_cliente` — the only thing the
    handler unit tests monkeypatch."""
    return BackendClient(telegram_id)


async def vincular_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/vincular <codigo>` — consumes the one-time linking code an ADMIN
    already generated on the web Usuarios screen (Phase 4)."""
    if not context.args:
        await update.message.reply_text(
            "Usá: /vincular <codigo>\n\nGenerá el código desde la pantalla web de Usuarios."
        )
        return

    codigo = context.args[0].strip()
    telegram_id = update.effective_user.id
    async with _cliente(telegram_id) as client:
        try:
            usuario = await client.vincular(codigo)
        except CodigoInvalido:
            await update.message.reply_text(
                "❌ Ese código es inválido o ya expiró. Generá uno nuevo desde la web."
            )
            return
        except TelegramYaVinculado:
            await update.message.reply_text(
                "⚠️ Este Telegram ya está vinculado a otro usuario."
            )
            return
        except BackendCaido:
            await update.message.reply_text(_MSG_CONEXION)
            return
        except LoreApiError:
            # gga finding (post-4-lens-review): every `BackendClient` method
            # shares ONE global error-code map (`api.py::_ERROR_CODE_MAP`);
            # an unmapped-here subclass (e.g. this ADMIN's own status
            # changing to `pending`/`rejected` between generating the code
            # and using it) must still get a reply, not silently reach only
            # the global logger.
            await update.message.reply_text(_MSG_CONEXION)
            return

    await update.message.reply_text(
        f"✅ Vinculado como administrador: {usuario.get('nombre', '')}."
    )


async def resolver_solicitud_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`CallbackQueryHandler(pattern=r"^lore_(apr|rej):")` — the Aprobar/
    Rechazar buttons pushed to every admin after a successful `/registro`.

    On success: edits the admin's message to the final state and notifies
    the applicant. On `YaResuelta` (409 — someone else already decided):
    edits the message instead of crashing (design D5's dual-channel
    approval race). The backend's 409 body for this race carries only
    `code` (no `status` — a known gap flagged since Phase 5), so the exact
    final status cannot be shown here; the message says only that it was
    already resolved.
    """
    query = update.callback_query
    await query.answer()

    accion, _, usuario_id = query.data.partition(":")
    decision_aprobar = accion == "lore_apr"

    try:
        uuid.UUID(usuario_id)
    except ValueError:
        # `usuario_id` comes from callback_data, which is bot-authored (not
        # user-invented), so this is low-exploitability defense-in-depth —
        # but `BackendClient` string-formats it straight into the request
        # URL path, so a malformed value is validated and rejected here
        # BEFORE it ever reaches that call (Phase 9 fix-up, finding #4).
        logger.warning(
            "resolver_solicitud_callback: usuario_id malformado %r (accion=%s)",
            usuario_id,
            accion,
        )
        await query.edit_message_text(_MSG_SOLICITUD_INVALIDA)
        return

    telegram_id = update.effective_user.id
    async with _cliente(telegram_id) as client:
        try:
            if decision_aprobar:
                resultado = await client.aprobar_solicitud(usuario_id)
            else:
                resultado = await client.rechazar_solicitud(usuario_id)
        except YaResuelta:
            await query.edit_message_text("Esta solicitud ya fue resuelta por otro administrador.")
            return
        except BackendCaido:
            await query.edit_message_text(_MSG_CONEXION)
            return
        except LoreApiError:
            # gga finding (post-4-lens-review): `require_bot_admin` itself
            # can raise NO_REGISTRADO/PENDIENTE/RECHAZADO/INACTIVO (mapped to
            # their own LoreApiError subclasses) if the tapping admin's own
            # status changed between being sent this button and tapping it
            # -- must still get a reply, not silently reach only the global
            # logger.
            await query.edit_message_text(_MSG_CONEXION)
            return

    nombre = resultado.get("nombre", "N/D")
    estado_final = "aprobada ✅" if decision_aprobar else "rechazada ❌"
    await query.edit_message_text(f"Solicitud de {nombre}: {estado_final}")

    solicitante_telegram_id = resultado.get("telegram_id_solicitante")
    if solicitante_telegram_id:
        mensaje = (
            "✅ Tu solicitud de acceso fue *aprobada*. Ya podés usar /start."
            if decision_aprobar
            else "❌ Tu solicitud de acceso fue *rechazada*."
        )
        try:
            await context.bot.send_message(
                chat_id=solicitante_telegram_id, text=mensaje, parse_mode="Markdown"
            )
        except Exception:  # noqa: BLE001 — gga finding (post-4-lens-review):
            # the approval/rejection is already saved backend-side and the
            # admin's own message is already edited by this point -- if the
            # applicant blocked the bot (Forbidden) or any other Telegram
            # API error happens notifying them, that must never surface as
            # an unhandled exception (same isolation as
            # `registro.py::_notificar_admins`, finding #1).
            logger.exception(
                "No pude notificar al solicitante %s de la resolución (usuario_id=%s)",
                solicitante_telegram_id,
                usuario_id,
            )
