"""Admin-facing Telegram surface: `/vincular <codigo>`, the pending-requests
list (`/pendientes` or the "Solicitudes pendientes" button), and the
Aprobar/Rechazar callback buttons pushed by `handlers/registro.py` or shown
in that list (design D5).

Authorization note (this project's own established pattern — "server is
the real gate"): the backend's `require_bot_admin` re-resolves the tapping
admin's `telegram_id` on every call. None of `vincular_command`,
`solicitudes_pendientes` or `resolver_solicitud_callback` performs its own
authorization check beyond that — an unauthorized tap simply gets a
`LoreApiError` back from the backend, same as any other bot user.
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
    Inactivo,
    LoreApiError,
    NoRegistrado,
    Pendiente,
    Rechazado,
    TelegramYaVinculado,
    YaResuelta,
)
from lore.handlers._common import (
    _MSG_CONEXION,
    editar_o_ignorar_sin_cambios,
    teclado_resolver_solicitud,
)

logger = logging.getLogger("lore.handlers.admin")

_MSG_SOLICITUD_INVALIDA = "⚠️ No pude procesar esta solicitud. Contactá a soporte."
_MSG_SOLO_ADMIN = "⛔ Solo un administrador puede ver las solicitudes pendientes."
_MSG_SIN_PENDIENTES = "No hay solicitudes pendientes."
# Most request messages sent per tap (oldest first), to stay clear of
# Telegram's per-chat rate limits.
_MAX_SOLICITUDES_POR_TOQUE = 10
# Any of these from `GET /admin/solicitudes` means the caller is not an active,
# approved ADMIN; they all get the same polite refusal.
_NO_ES_ADMIN = (NoRegistrado, Pendiente, Rechazado, Inactivo)


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


def _texto_solicitud(solicitud: dict) -> str:
    """Plain text (no parse_mode) so a name with Markdown characters can
    never break the message."""
    sucursales = ", ".join(solicitud.get("sucursales") or []) or "N/D"
    return (
        "🔔 Solicitud de acceso (Lore)\n\n"
        f"👤 Nombre: {solicitud.get('nombre', 'N/D')}\n"
        f"📱 Celular: {solicitud.get('phone') or 'N/D'}\n"
        f"🏢 Sucursal: {sucursales}"
    )


def _solicitud_valida(solicitud: object) -> bool:
    """A list item must be a dict with a UUID `id`; anything else is skipped
    with a warning so one bad item never aborts the whole list."""
    valida = isinstance(solicitud, dict) and _es_uuid(solicitud.get("id"))
    if not valida:
        logger.warning("solicitudes_pendientes: solicitud malformada descartada: %r", solicitud)
    return valida


def _es_uuid(usuario_id: object) -> bool:
    try:
        uuid.UUID(str(usuario_id))
    except ValueError:
        return False
    return True


def _resumen_pendientes(total: int) -> str:
    if total <= _MAX_SOLICITUDES_POR_TOQUE:
        return f"📋 Solicitudes pendientes: {total}"
    return (
        f"Hay {total} solicitudes pendientes. Te muestro las {_MAX_SOLICITUDES_POR_TOQUE} "
        "más antiguas; aprobalas o rechazalas y volvé a tocar el botón para ver más, "
        "o revisalas todas en el panel (Usuarios)."
    )


async def solicitudes_pendientes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/pendientes` or the "Solicitudes pendientes" button — lists every
    pending registration as its own message with the same Aprobar/Rechazar
    buttons the push notification carries. Only an ADMIN gets the list; the
    backend decides, anyone else is politely refused."""
    telegram_id = update.effective_user.id
    async with _cliente(telegram_id) as client:
        try:
            pendientes = await client.listar_solicitudes()
        except _NO_ES_ADMIN:
            await update.message.reply_text(_MSG_SOLO_ADMIN)
            return
        except LoreApiError:
            await update.message.reply_text(_MSG_CONEXION)
            return

    pendientes = [s for s in pendientes if _solicitud_valida(s)]
    if not pendientes:
        await update.message.reply_text(_MSG_SIN_PENDIENTES)
        return
    await update.message.reply_text(_resumen_pendientes(len(pendientes)))
    for solicitud in pendientes[:_MAX_SOLICITUDES_POR_TOQUE]:
        await update.message.reply_text(
            _texto_solicitud(solicitud),
            reply_markup=teclado_resolver_solicitud(solicitud["id"]),
        )


async def _reintentar_con_botones(query) -> None:
    """The backend was unreachable: keep the request text and its
    Aprobar/Rechazar buttons and add the retry notice, instead of leaving the
    admin with a message that can no longer be resolved."""
    await editar_o_ignorar_sin_cambios(
        query,
        f"{query.message.text}\n\n{_MSG_CONEXION}",
        reply_markup=query.message.reply_markup,
    )


def _usuario_id_valido(usuario_id: str, accion: str) -> bool:
    """`usuario_id` comes from callback_data, which is bot-authored (not
    user-invented), so this is low-exploitability defense-in-depth — but
    `BackendClient` string-formats it straight into the request URL path, so
    a malformed value is rejected BEFORE it ever reaches that call (Phase 9
    fix-up, finding #4)."""
    try:
        uuid.UUID(usuario_id)
    except ValueError:
        logger.warning(
            "resolver_solicitud_callback: usuario_id malformado %r (accion=%s)",
            usuario_id,
            accion,
        )
        return False
    return True


async def _resolver_en_backend(update: Update, aprobar: bool, usuario_id: str) -> dict | None:
    """Calls the backend's approve/reject endpoint. On any failure it edits
    the admin's message accordingly and returns None; otherwise returns the
    backend's body."""
    query = update.callback_query
    async with _cliente(update.effective_user.id) as client:
        try:
            if aprobar:
                return await client.aprobar_solicitud(usuario_id)
            return await client.rechazar_solicitud(usuario_id)
        except YaResuelta:
            await query.edit_message_text("Esta solicitud ya fue resuelta por otro administrador.")
        except BackendCaido:
            await _reintentar_con_botones(query)
        except LoreApiError:
            # gga finding (post-4-lens-review): `require_bot_admin` itself
            # can raise NO_REGISTRADO/PENDIENTE/RECHAZADO/INACTIVO (mapped to
            # their own LoreApiError subclasses) if the tapping admin's own
            # status changed between being sent this button and tapping it
            # -- must still get a reply, not silently reach only the global
            # logger.
            await query.edit_message_text(_MSG_CONEXION)
    return None


async def _notificar_solicitante(
    context: ContextTypes.DEFAULT_TYPE, solicitante_telegram_id: int, aprobar: bool, usuario_id: str
) -> None:
    """Tells the applicant the outcome. Isolated like `registro.py::
    _notificar_admins`: the decision is already saved backend-side and the
    admin's message already edited, so if the applicant blocked the bot
    (Forbidden) or any other Telegram API error happens, it is only logged."""
    mensaje = (
        "✅ Tu solicitud de acceso fue *aprobada*. Ya podés usar /start."
        if aprobar
        else "❌ Tu solicitud de acceso fue *rechazada*."
    )
    try:
        await context.bot.send_message(
            chat_id=solicitante_telegram_id, text=mensaje, parse_mode="Markdown"
        )
    except Exception:  # noqa: BLE001 — any Telegram API error must stay isolated.
        logger.exception(
            "No pude notificar al solicitante %s de la resolución (usuario_id=%s)",
            solicitante_telegram_id,
            usuario_id,
        )


async def resolver_solicitud_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`CallbackQueryHandler(pattern=r"^lore_(apr|rej):")` — the Aprobar/
    Rechazar buttons pushed to every admin after a successful `/registro`
    or shown in the `/pendientes` list.

    On success: edits the admin's message to the final state and notifies
    the applicant. On `YaResuelta` (409 — someone else already decided):
    edits the message instead of crashing (design D5's dual-channel
    approval race). The backend's 409 body for this race carries only
    `code` (no `status` — a known gap flagged since Phase 5), so the exact
    final status cannot be shown here; the message says only that it was
    already resolved. On a backend outage the buttons are kept for retry.
    """
    query = update.callback_query
    await query.answer()

    accion, _, usuario_id = query.data.partition(":")
    aprobar = accion == "lore_apr"
    if not _usuario_id_valido(usuario_id, accion):
        await query.edit_message_text(_MSG_SOLICITUD_INVALIDA)
        return

    resultado = await _resolver_en_backend(update, aprobar, usuario_id)
    if resultado is None:
        return

    nombre = resultado.get("nombre", "N/D")
    estado_final = "aprobada ✅" if aprobar else "rechazada ❌"
    await query.edit_message_text(f"Solicitud de {nombre}: {estado_final}")

    solicitante_telegram_id = resultado.get("telegram_id_solicitante")
    if solicitante_telegram_id:
        await _notificar_solicitante(context, solicitante_telegram_id, aprobar, usuario_id)
