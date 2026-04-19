import tempfile
import os
import httpx

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler

from core.config import logger, BACKEND_URL, SONIA_BOT_SECRET
from core.constants import OTP_ASKING_PLATE, OTP_ASKING_CODE, OTP_CONFIRMING, PLATE_REGEX
from core.decorators import role_required, check_cancel_intent
from keyboards.reply import get_main_keyboard
from services.ai import transcribe_voice


async def _transcribe_if_voice(update: Update) -> str:
    """Retorna el texto del mensaje — transcribe si es voz."""
    if update.message.voice:
        await update.message.reply_text("Escuchando... 🎧")
        voice_file = await update.message.voice.get_file()
        fd, path = tempfile.mkstemp(suffix=".ogg")
        os.close(fd)
        await voice_file.download_to_drive(path)
        transcript = await transcribe_voice(path)
        os.remove(path)
        return transcript or ""
    return update.message.text or ""


BYPASS_ROLES = {"superadmin", "jefe_taller"}


async def _get_pending_otp_orders(tenant_id: str = None, is_superadmin: bool = False) -> list:
    """Consulta al backend las órdenes pendientes de firma OTP."""
    headers = {"x-sonia-secret": SONIA_BOT_SECRET}
    if tenant_id:
        headers["X-Tenant-ID"] = str(tenant_id)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(f"{BACKEND_URL}/orders/pending-otp", headers=headers)
            if res.status_code == 200:
                return res.json()
    except Exception as e:
        logger.error(f"Error consultando órdenes pendientes OTP: {e}")
    return []


# ─── Entry point ──────────────────────────────────────────────────────────────

@role_required()
async def start_otp_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia el flujo OTP — muestra órdenes pendientes y pide la placa."""
    logged_in = context.user_data.get("logged_in_user", {})
    user_role = logged_in.get("role", "")
    tenant_id = logged_in.get("tenant_id") or context.user_data.get("active_tenant_id")
    is_superadmin = user_role == "superadmin"

    pending = await _get_pending_otp_orders(tenant_id, is_superadmin)

    if pending:
        lines = "\n".join([f"• *{o['placa']}* — {o.get('cliente', 'Cliente N/D')}" for o in pending[:10]])
        await update.message.reply_text(
            f"🔑 *Ingreso de OTP*\n\n"
            f"Estas motos están pendientes de firma:\n{lines}\n\n"
            f"¿Para qué placa vas a ingresar el código? Escribila o dímela.",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "🔑 *Ingreso de OTP*\n\n"
            "No hay órdenes pendientes de firma en este momento.\n\n"
            "Si el cliente ya tiene el código, decime la placa igual.",
            parse_mode="Markdown"
        )

    return OTP_ASKING_PLATE


# ─── Paso 1: Placa ────────────────────────────────────────────────────────────

@role_required()
async def otp_handle_plate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = await _transcribe_if_voice(update)
    if await check_cancel_intent(update, context, text):
        return ConversationHandler.END

    plate_match = PLATE_REGEX.search(text.upper())
    if not plate_match:
        await update.message.reply_text(
            "No encontré una placa válida. Escribila así: *ABC123* o *NOI82G*",
            parse_mode="Markdown"
        )
        return OTP_ASKING_PLATE

    plate = plate_match.group(0).upper()

    # Verificar que la placa tiene una orden pendiente de firma
    logged_in  = context.user_data.get("logged_in_user", {})
    tenant_id  = logged_in.get("tenant_id") or context.user_data.get("active_tenant_id")
    headers    = {"x-sonia-secret": SONIA_BOT_SECRET}
    if tenant_id:
        headers["X-Tenant-ID"] = str(tenant_id)

    order_id = None
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(f"{BACKEND_URL}/orders/pending-otp/plate/{plate}", headers=headers)
            if res.status_code == 200:
                data = res.json()
                order_id = data.get("order_id")
            elif res.status_code == 404:
                await update.message.reply_text(
                    f"⚠️ La placa *{plate}* no tiene ninguna orden pendiente de firma OTP.\n\n"
                    f"Verificá la placa o consultá el estado en el panel web.",
                    parse_mode="Markdown"
                )
                return OTP_ASKING_PLATE
    except Exception as e:
        logger.error(f"Error verificando placa {plate} para OTP: {e}")
        await update.message.reply_text("Tuve un problema de conexión. Intentá de nuevo.")
        return OTP_ASKING_PLATE

    context.user_data["otp_plate"]    = plate
    context.user_data["otp_order_id"] = order_id

    logged_in = context.user_data.get("logged_in_user", {})
    user_role = logged_in.get("role", "")
    can_bypass = user_role in BYPASS_ROLES

    bypass_hint = "\n\n_O si no tiene el código, podés escribir *'sin otp'* para autorizar manualmente._" if can_bypass else ""

    await update.message.reply_text(
        f"Placa *{plate}* ✅ — orden pendiente encontrada.\n\n"
        f"Ahora decime el *código de 6 dígitos* que recibió el cliente.{bypass_hint}",
        parse_mode="Markdown"
    )
    return OTP_ASKING_CODE


# ─── Paso 2: Código ───────────────────────────────────────────────────────────

@role_required()
async def otp_handle_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = await _transcribe_if_voice(update)
    if await check_cancel_intent(update, context, text):
        return ConversationHandler.END

    plate    = context.user_data.get("otp_plate", "")
    logged_in = context.user_data.get("logged_in_user", {})
    user_role = logged_in.get("role", "")
    can_bypass = user_role in BYPASS_ROLES

    # Detectar intención de autorizar sin OTP
    if can_bypass and any(k in text.lower() for k in ["sin otp", "sin codigo", "sin código", "autorizar", "bypass"]):
        context.user_data["otp_bypass"] = True
        kb = [[
            InlineKeyboardButton("✅ Sí, autorizar", callback_data="otp_confirm_yes"),
            InlineKeyboardButton("❌ Cancelar",       callback_data="otp_confirm_no"),
        ]]
        await update.message.reply_text(
            f"⚠️ Vas a *autorizar sin OTP* la orden de la placa *{plate}*.\n\n"
            f"Esta acción quedará registrada con tu usuario. ¿Confirmás?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return OTP_CONFIRMING

    # Extraer solo dígitos
    digits = "".join(filter(str.isdigit, text))
    if len(digits) != 6:
        bypass_hint = "\n\nSi no tenés el código, escribí *'sin otp'* para autorizar manualmente." if can_bypass else ""
        await update.message.reply_text(
            f"El código debe tener exactamente 6 dígitos. "
            f"Te entendí: *'{text}'* — revisalo e intentá de nuevo.{bypass_hint}",
            parse_mode="Markdown"
        )
        return OTP_ASKING_CODE

    context.user_data["otp_code"]   = digits
    context.user_data["otp_bypass"] = False

    kb = [[
        InlineKeyboardButton("✅ Sí, registrar", callback_data="otp_confirm_yes"),
        InlineKeyboardButton("❌ No, corregir",  callback_data="otp_confirm_no"),
    ]]
    await update.message.reply_text(
        f"Voy a registrar el código *{digits}* para la placa *{plate}*.\n\n"
        f"¿Confirmás?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )
    return OTP_CONFIRMING


# ─── Paso 3: Confirmación ─────────────────────────────────────────────────────

@role_required()
async def otp_handle_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    logged_in = context.user_data.get("logged_in_user", {})
    user_role = logged_in.get("role", "none")

    if query.data == "otp_confirm_no":
        await query.edit_message_text(
            "Entendido. Decime el código correcto de 6 dígitos."
        )
        return OTP_ASKING_CODE

    # Confirmar → llamar al backend
    order_id  = context.user_data.get("otp_order_id")
    code      = context.user_data.get("otp_code")
    plate     = context.user_data.get("otp_plate", "")
    is_bypass = context.user_data.get("otp_bypass", False)
    tenant_id = logged_in.get("tenant_id") or context.user_data.get("active_tenant_id")

    headers = {"x-sonia-secret": SONIA_BOT_SECRET}
    if tenant_id:
        headers["X-Tenant-ID"] = str(tenant_id)

    action_txt = "Autorizando sin OTP" if is_bypass else "Verificando código"
    await query.edit_message_text(f"{action_txt} para *{plate}*...", parse_mode="Markdown")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            if is_bypass:
                res = await client.post(
                    f"{BACKEND_URL}/orders/{order_id}/otp/bypass",
                    headers=headers
                )
            else:
                res = await client.post(
                    f"{BACKEND_URL}/orders/{order_id}/otp/verify",
                    json={"code": code},
                    headers=headers
                )
            data = res.json()

        if res.status_code == 200:
            if is_bypass:
                bypass_at   = data.get("bypass_at", "")[:16].replace("T", " ")
                by_name     = data.get("bypass_by_name", "")
                await query.message.reply_text(
                    f"⚠️ *Orden autorizada sin OTP*\n\n"
                    f"🏍️ Placa: *{plate}*\n"
                    f"👤 Autorizado por: {by_name}\n"
                    f"🕐 Fecha/hora: {bypass_at}\n\n"
                    f"La orden ya está activa en el tablero Kanban.",
                    parse_mode="Markdown",
                    reply_markup=get_main_keyboard(user_role)
                )
            else:
                accepted_at    = data.get("accepted_at", "")[:16].replace("T", " ")
                accepted_phone = data.get("accepted_phone", "")
                await query.message.reply_text(
                    f"✅ *¡Firma registrada!*\n\n"
                    f"🏍️ Placa: *{plate}*\n"
                    f"📱 Teléfono: {accepted_phone}\n"
                    f"🕐 Aceptado: {accepted_at}\n\n"
                    f"La orden ya está activa en el tablero Kanban.",
                    parse_mode="Markdown",
                    reply_markup=get_main_keyboard(user_role)
                )
        else:
            detail = data.get("detail", "Error desconocido")
            await query.message.reply_text(
                f"❌ *No se pudo procesar*\n\n{detail}",
                parse_mode="Markdown",
                reply_markup=get_main_keyboard(user_role)
            )
    except Exception as e:
        logger.error(f"Error procesando OTP/bypass para orden {order_id}: {e}")
        await query.message.reply_text(
            "Tuve un problema de conexión. Intentá de nuevo.",
            reply_markup=get_main_keyboard(user_role)
        )

    # Limpiar datos del flujo OTP
    for key in ("otp_plate", "otp_order_id", "otp_code", "otp_bypass"):
        context.user_data.pop(key, None)

    return ConversationHandler.END
