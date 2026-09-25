"""Self-registration conversation for an ASESOR_MOSTRADOR (design D5/D7).

Explicitly modeled on `telegram-bot/bot/handlers/registration.py`'s own
`/start` → not-found → registration UX ("same system", per the proposal) —
read ONLY as a UX/flow reference, nothing imported or copied from it (see
`tests/test_isolation.py`).

`/start` calls `client.yo()`:
- `NoRegistrado` (404, no Usuario for this `telegram_id` yet) → offers the
  "Solicitar acceso" self-registration flow below.
- Any other outcome is a 200 body with a `status` field — this is what makes
  re-entry "status-aware" (spec): `pending`/`rejected`/`approved` are all
  read directly off `/yo`'s own response, never off a second endpoint.
"""
from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from lore.api import (
    BackendCaido,
    BackendClient,
    LoreApiError,
    NoRegistrado,
    SucursalNoEncontrada,
    YaRegistrado,
)
from lore.estados import RegistroEstado
from lore.handlers._common import _MSG_CONEXION, _MSG_SESION_EXPIRADA, _escapar_markdown

logger = logging.getLogger("lore.handlers.registro")

_DRAFT_KEY = "lore_registro"
_PHONE_MIN_DIGITS = 7
_PHONE_MAX_DIGITS = 15


def _cliente(telegram_id: int) -> BackendClient:
    """Thin factory — the only seam the handler tests monkeypatch, so unit
    tests never need a real `httpx.MockTransport` for conversation logic
    (that transport-level contract is already covered by `test_api.py`)."""
    return BackendClient(telegram_id)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """`/start` — status-aware re-entry point (spec)."""
    telegram_id = update.effective_user.id
    async with _cliente(telegram_id) as client:
        try:
            data = await client.yo()
        except NoRegistrado:
            return await _iniciar_registro(update, context)
        except BackendCaido:
            await update.message.reply_text(_MSG_CONEXION)
            return ConversationHandler.END
        except LoreApiError:
            # gga finding (post-4-lens-review): `/yo` shares ONE global
            # error-code map (`api.py::_ERROR_CODE_MAP`) with every other
            # endpoint -- any `LoreApiError` subclass not explicitly handled
            # above must still get a reply instead of silently reaching only
            # the global logger (`main.py::_manejar_error`).
            await update.message.reply_text(_MSG_CONEXION)
            return ConversationHandler.END

    estado = data.get("status")
    if estado == "pending":
        await update.message.reply_text(
            "⏳ Tu solicitud de acceso está *pendiente de aprobación*. "
            "Te aviso por acá apenas un administrador la revise.",
            parse_mode="Markdown",
        )
        return ConversationHandler.END
    if estado == "rejected":
        await update.message.reply_text(
            "❌ Tu solicitud de acceso fue *rechazada*. "
            "Si creés que es un error, contactá a un administrador.",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    await update.message.reply_text(
        f"👋 ¡Hola, {data.get('nombre', '')}! Ya estás registrado como asesor de mostrador."
    )
    return ConversationHandler.END


async def _iniciar_registro(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data[_DRAFT_KEY] = {}
    await update.message.reply_text(
        "👋 No te tengo registrado todavía.\n\n"
        "Vamos a mandar una solicitud de acceso.\n"
        "Paso 1 de 3 → ¿Cuál es tu *nombre completo*?",
        parse_mode="Markdown",
    )
    return RegistroEstado.NOMBRE


async def recibir_nombre(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    nombre = (update.message.text or "").strip()
    if len(nombre) < 3:
        await update.message.reply_text(
            "Necesito tu nombre completo (mínimo 3 letras). ¿Cómo te llamás?"
        )
        return RegistroEstado.NOMBRE

    context.user_data[_DRAFT_KEY]["nombre"] = nombre
    await update.message.reply_text(
        "Paso 2 de 3 → ¿Cuál es tu *celular*? (solo dígitos, ej: 3001234567)",
        parse_mode="Markdown",
    )
    return RegistroEstado.CELULAR


async def recibir_celular(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    phone = (update.message.text or "").strip().replace(" ", "").replace("-", "")
    if not phone.isdigit() or not (_PHONE_MIN_DIGITS <= len(phone) <= _PHONE_MAX_DIGITS):
        await update.message.reply_text(
            "Ese número no parece válido. Mandame solo los dígitos, ej: 3001234567"
        )
        return RegistroEstado.CELULAR

    context.user_data[_DRAFT_KEY]["phone"] = phone

    telegram_id = update.effective_user.id
    async with _cliente(telegram_id) as client:
        try:
            sucursales = await client.sucursales()
        except BackendCaido:
            await update.message.reply_text(_MSG_CONEXION)
            return ConversationHandler.END
        except LoreApiError:
            await update.message.reply_text(_MSG_CONEXION)
            return ConversationHandler.END

    if not sucursales:
        await update.message.reply_text(
            "⚠️ No pude cargar la lista de sucursales en este momento. Probá de nuevo con /start."
        )
        return ConversationHandler.END

    context.user_data[_DRAFT_KEY]["sucursales"] = {s["id"]: s["nombre"] for s in sucursales}
    kb = [
        [InlineKeyboardButton(s["nombre"], callback_data=f"lore_sucursal:{s['id']}")]
        for s in sucursales
    ]
    await update.message.reply_text(
        "Paso 3 de 3 → ¿En qué *sucursal* trabajás?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return RegistroEstado.SUCURSAL


async def recibir_sucursal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    sucursal_id = query.data.replace("lore_sucursal:", "")
    draft = context.user_data.get(_DRAFT_KEY, {})
    sucursales = draft.get("sucursales", {})
    if sucursal_id not in sucursales:
        # Stale/orphaned interaction (e.g. `user_data` was reset by a process
        # restart but the user still tapped an old inline keyboard button) —
        # never fabricate a placeholder branch name and let them "confirm"
        # a request for an unknown sucursal (Phase 9 fix-up, finding #6).
        logger.warning(
            "recibir_sucursal: sucursal_id desconocido %r (no está en el draft)",
            sucursal_id,
        )
        context.user_data.pop(_DRAFT_KEY, None)
        await query.edit_message_text(_MSG_SESION_EXPIRADA)
        return ConversationHandler.END

    sucursal_nombre = sucursales[sucursal_id]
    draft["sucursal_id"] = sucursal_id

    resumen = (
        "📋 *Resumen de tu solicitud:*\n\n"
        f"👤 Nombre: {_escapar_markdown(draft.get('nombre', ''))}\n"
        f"📱 Celular: {draft.get('phone')}\n"
        f"🏢 Sucursal: {sucursal_nombre}\n\n"
        "¿Confirmás el envío?"
    )
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Confirmar", callback_data="lore_reg_confirmar"),
                InlineKeyboardButton("❌ Cancelar", callback_data="lore_reg_cancelar"),
            ]
        ]
    )
    await query.edit_message_text(resumen, parse_mode="Markdown", reply_markup=kb)
    return RegistroEstado.CONFIRMAR


async def confirmar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "lore_reg_cancelar":
        context.user_data.pop(_DRAFT_KEY, None)
        await query.edit_message_text("Solicitud cancelada. Si querés intentarlo de nuevo, mandá /start.")
        return ConversationHandler.END

    draft = context.user_data.get(_DRAFT_KEY, {})
    telegram_id = update.effective_user.id
    async with _cliente(telegram_id) as client:
        try:
            resultado = await client.registro(
                nombre=draft.get("nombre", ""),
                phone=draft.get("phone", ""),
                sucursal_id=draft.get("sucursal_id", ""),
            )
        except YaRegistrado:
            await query.edit_message_text(
                "Ya tenés una solicitud registrada para este usuario. Mandá /start para ver tu estado."
            )
            context.user_data.pop(_DRAFT_KEY, None)
            return ConversationHandler.END
        except SucursalNoEncontrada:
            await query.edit_message_text(
                "⚠️ La sucursal seleccionada ya no está disponible. Probá de nuevo con /start."
            )
            context.user_data.pop(_DRAFT_KEY, None)
            return ConversationHandler.END
        except BackendCaido:
            await query.edit_message_text(_MSG_CONEXION)
            return ConversationHandler.END
        except LoreApiError:
            await query.edit_message_text(_MSG_CONEXION)
            return ConversationHandler.END

    await query.edit_message_text(
        "✅ *¡Solicitud enviada!*\n\nQueda pendiente de aprobación por un administrador. "
        "Te aviso por acá apenas la revisen.",
        parse_mode="Markdown",
    )
    await _notificar_admins(context, resultado)
    context.user_data.pop(_DRAFT_KEY, None)
    return ConversationHandler.END


async def _notificar_admins(context: ContextTypes.DEFAULT_TYPE, resultado: dict) -> None:
    """Pushes the approval request to every admin `POST /registro` returned
    in `admin_telegram_ids` — the token/notification only Lore holds, never
    the backend (design D5).

    Each admin's `send_message` call is isolated in its own try/except
    (Phase 9 fix-up, finding #1): a Telegram API error for ONE admin (e.g.
    `Forbidden` because they blocked the bot or never opened a DM with it)
    must never stop the remaining admins from being notified."""
    usuario = resultado.get("usuario", {})
    admin_ids = resultado.get("admin_telegram_ids") or []
    usuario_id = usuario.get("id")
    if not admin_ids:
        logger.warning(
            "Solicitud de registro sin administradores a notificar (usuario_id=%s)",
            usuario_id,
        )
        return

    nombre = _escapar_markdown(usuario.get("nombre", "N/D"))
    mensaje = f"🔔 *Nueva solicitud de acceso (Lore)*\n\n👤 Nombre: {nombre}"
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Aprobar", callback_data=f"lore_apr:{usuario_id}"),
                InlineKeyboardButton("❌ Rechazar", callback_data=f"lore_rej:{usuario_id}"),
            ]
        ]
    )
    for admin_telegram_id in admin_ids:
        try:
            await context.bot.send_message(
                chat_id=admin_telegram_id,
                text=mensaje,
                parse_mode="Markdown",
                reply_markup=kb,
            )
        except Exception:  # noqa: BLE001 — any Telegram API error for one
            # admin must never block the others; caught broadly on purpose.
            logger.exception(
                "No pude notificar al admin %s de la solicitud de %s (usuario_id=%s)",
                admin_telegram_id,
                nombre,
                usuario_id,
            )


async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop(_DRAFT_KEY, None)
    await update.message.reply_text("Registro cancelado. Si querés intentarlo de nuevo, mandá /start.")
    return ConversationHandler.END


async def callback_huerfano(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Low-priority fallback for any `lore_*` callback_data that reaches us
    with no active handler to claim it — e.g. a stale inline keyboard button
    tapped after the process restarted mid-conversation. `ConversationHandler`
    state (and `context.user_data`) is in-memory only — there is no
    `.persistence()` configured (an accepted, deliberately deferred
    architectural limitation) — so a restart makes the process "forget" it
    was ever mid-conversation with that chat, and the next tap would
    otherwise match NO handler at all and be silently dropped
    (Phase 9 fix-up, finding #7).

    Registered LAST among `CallbackQueryHandler`s in the DEFAULT handler
    group (group=0) in `main.py::build_application` — not a higher group
    number. python-telegram-bot's dispatch rule is "the first handler that
    matches wins" WITHIN one group (`break` after the first match), but
    every group still runs independently per update regardless of what an
    earlier group already matched. A higher group (e.g. group=1) would fire
    this fallback IN ADDITION to whatever a group-0 handler already
    processed for the same update — verified experimentally before choosing
    this approach — which is not what we want here.
    """
    query = update.callback_query
    await query.answer()
    logger.info("Callback huérfano descartado: %s", query.data)
    await query.edit_message_text(_MSG_SESION_EXPIRADA)
