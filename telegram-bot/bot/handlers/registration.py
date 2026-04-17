import time
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from core.config import BACKEND_URL, SONIA_BOT_SECRET, logger
from core.constants import O_NAME, O_PHONE, O_ROLE, O_TENANT, O_CONFIRM
from services.api import get_all_tenants, register_user, get_superadmin_telegram_ids

ROLES_FOR_REGISTRATION = {
    "technician":   "👨‍🔧 Técnico / Mecánico",
    "jefe_taller":  "🏢 Jefe de Taller",
    "proveedor":    "📦 Proveedor de Repuestos",
    "parts_dealer": "🔩 Distribuidor / Repuestero",
}

# Roles que deben indicar a qué taller pertenecen
ROLES_NEED_TENANT = {"technician", "jefe_taller"}

ROLES_ES = {
    "technician":   "Técnico / Mecánico",
    "jefe_taller":  "Jefe de Taller",
    "proveedor":    "Proveedor de Repuestos",
    "parts_dealer": "Distribuidor / Repuestero",
    "superadmin":   "Super Administrador",
    "client":       "Cliente",
}


async def start_or_register(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Entry point de /start — funciona tanto para usuarios registrados como no registrados.
    - Registrado y activo  → muestra bienvenida normal.
    - Pendiente/rechazado  → informa el estado.
    - No encontrado        → ofrece botón de auto-registro.
    """
    telegram_id = str(update.effective_user.id)

    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(
                f"{BACKEND_URL}/users/telegram/{telegram_id}",
                headers={"x-sonia-secret": SONIA_BOT_SECRET},
                timeout=10.0
            )
        except Exception as e:
            logger.error(f"start_or_register: error de conexión: {e}")
            await update.message.reply_text(
                "⚠️ Tuve un problema de conexión. Intentá de nuevo en unos segundos."
            )
            return ConversationHandler.END

    if res.status_code == 200:
        user_data_json = res.json()
        # Cachear para que @role_required no vuelva a ir al backend
        context.user_data["logged_in_user"] = {
            "id":        user_data_json["id"],
            "role":      user_data_json["role"],
            "name":      user_data_json["name"],
            "tenant_id": user_data_json.get("tenant_id"),
        }
        context.user_data["logged_in_user_cached_at"] = time.time()
        from handlers.admin import send_welcome
        return await send_welcome(update, context)

    if res.status_code == 403:
        # Existe pero pending o rejected
        body = {}
        try:
            body = res.json()
        except Exception:
            pass
        detail = body.get("detail", "")
        if "rechazado" in detail.lower() or "rejected" in detail.lower():
            await update.message.reply_text(
                "❌ Tu solicitud de acceso fue *rechazada* por el administrador.\n\n"
                "Si crees que es un error, contactá directamente al Super Administrador UM.",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                "⏳ Tu solicitud de acceso está *pendiente de aprobación*.\n\n"
                "Te aviso por acá mismo en cuanto el administrador te dé el visto bueno.",
                parse_mode="Markdown"
            )
        return ConversationHandler.END

    # 404 u otro — usuario no encontrado → ofrecer registro
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("📝 Solicitar acceso", callback_data="start_registration")
    ]])
    await update.message.reply_text(
        f"👋 ¡Hola, {update.effective_user.first_name}!\n\n"
        "No te tengo registrado en la *Red UM Colombia*.\n"
        "¿Querés enviar una solicitud de acceso al administrador?",
        parse_mode="Markdown",
        reply_markup=kb
    )
    return ConversationHandler.END


async def begin_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia el flujo de registro desde el botón 'Solicitar acceso'."""
    query = update.callback_query
    await query.answer()

    context.user_data["reg_data"] = {
        "telegram_id": str(update.effective_user.id),
    }

    await query.message.reply_text(
        "📝 *Solicitud de Acceso — Red UM Colombia*\n\n"
        "Paso *1 de 4* → ¿Cuál es tu *nombre completo*?",
        parse_mode="Markdown"
    )
    return O_NAME


async def handle_reg_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text.strip()
    if len(name) < 3:
        await update.message.reply_text(
            "Necesito tu nombre completo (mínimo 3 letras). ¿Cómo te llamás?"
        )
        return O_NAME

    context.user_data["reg_data"]["name"] = name

    await update.message.reply_text(
        f"✅ *{name}*\n\n"
        "Paso *2 de 4* → ¿Cuál es tu número de *celular*? (solo dígitos, ej: 3001234567)",
        parse_mode="Markdown"
    )
    return O_PHONE


async def handle_reg_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    phone = update.message.text.strip().replace(" ", "").replace("-", "")
    if not phone.lstrip("+").isdigit() or len(phone) < 7:
        await update.message.reply_text(
            "Ese número no parece válido. Mandame solo los dígitos, ej: *3001234567*",
            parse_mode="Markdown"
        )
        return O_PHONE

    context.user_data["reg_data"]["phone"] = phone

    kb = [[InlineKeyboardButton(label, callback_data=f"reg_role_{role}")]
          for role, label in ROLES_FOR_REGISTRATION.items()]

    await update.message.reply_text(
        "Paso *3 de 4* → ¿Con qué *rol* vas a trabajar en la red?\n\n"
        "Elegí el que mejor te describe:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )
    return O_ROLE


async def handle_reg_role(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    role = query.data.replace("reg_role_", "")
    if role not in ROLES_FOR_REGISTRATION:
        await query.message.reply_text("Seleccioná una opción válida del menú.")
        return O_ROLE

    context.user_data["reg_data"]["role"] = role
    role_label = ROLES_FOR_REGISTRATION[role]

    if role in ROLES_NEED_TENANT:
        tenants = await get_all_tenants()
        if not tenants:
            await query.message.reply_text(
                "⚠️ No pude cargar la lista de centros en este momento. "
                "Intentá de nuevo con /start."
            )
            return ConversationHandler.END

        # Guardar mapa id→nombre para usarlo después
        context.user_data["reg_tenants"] = {t["id"]: t["name"] for t in tenants}

        TIPOS = {"service_center": "🔧", "distributor": "📦"}
        kb = []
        for t in tenants:
            tipo = TIPOS.get(t.get("tenant_type", ""), "🏢")
            kb.append([InlineKeyboardButton(
                f"{tipo} {t['name']}",
                callback_data=f"reg_tenant_{t['id']}"
            )])

        await query.message.reply_text(
            f"✅ *{role_label}*\n\n"
            "Paso *4 de 4* → ¿En qué *centro de servicio* trabajás?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return O_TENANT

    # Proveedor / Distribuidor — no necesita taller, ir directo a confirmar
    return await _show_confirmation(query.message, context)


async def handle_reg_tenant(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    tenant_id = query.data.replace("reg_tenant_", "")
    tenant_name = context.user_data.get("reg_tenants", {}).get(tenant_id, "Centro seleccionado")

    context.user_data["reg_data"]["tenant_id"] = tenant_id
    context.user_data["reg_data"]["service_center_name"] = tenant_name
    context.user_data.pop("reg_tenants", None)

    return await _show_confirmation(query.message, context)


async def _show_confirmation(target_msg, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Muestra el resumen de la solicitud y pide confirmación final."""
    d = context.user_data["reg_data"]
    role_label = ROLES_FOR_REGISTRATION.get(d["role"], d["role"])

    lines = [
        "📋 *Resumen de tu solicitud:*\n",
        f"👤 *Nombre:*  {d['name']}",
        f"📱 *Celular:* {d['phone']}",
        f"🛠️ *Rol:*     {role_label}",
    ]
    if d.get("service_center_name"):
        lines.append(f"🏢 *Centro:*  {d['service_center_name']}")

    lines.append("\n¿Confirmás el envío de esta solicitud?")

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Confirmar y enviar", callback_data="reg_confirm_yes"),
        InlineKeyboardButton("❌ Cancelar",           callback_data="reg_confirm_no"),
    ]])

    await target_msg.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=kb
    )
    return O_CONFIRM


async def handle_reg_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "reg_confirm_no":
        context.user_data.pop("reg_data", None)
        await query.message.reply_text(
            "Cancelado. Si querés intentarlo de nuevo, mandame /start."
        )
        return ConversationHandler.END

    d = context.user_data.get("reg_data", {})

    payload = {
        "name":                 d["name"],
        "phone":                d["phone"],
        "role":                 d["role"],
        "telegram_id":          d["telegram_id"],
        "status":               "pending",
        "tenant_id":            d.get("tenant_id"),
        "service_center_name":  d.get("service_center_name"),
    }

    user = await register_user(payload)

    if not user:
        await query.message.reply_text(
            "⚠️ Hubo un error al enviar tu solicitud. Intentá de nuevo más tarde con /start."
        )
        return ConversationHandler.END

    await query.edit_message_text(
        "✅ *¡Solicitud enviada!*\n\n"
        "Tu pedido de acceso llegó al Super Administrador.\n"
        "Te aviso acá mismo cuando sea aprobado. ¡Gracias por la paciencia! 🙏",
        parse_mode="Markdown"
    )

    await _notify_superadmins(context, user)

    context.user_data.pop("reg_data", None)
    return ConversationHandler.END


async def _notify_superadmins(context: ContextTypes.DEFAULT_TYPE, user: dict) -> None:
    """Envía notificación con botones aprobar/rechazar a todos los superadmins activos."""
    superadmin_ids = await get_superadmin_telegram_ids()
    if not superadmin_ids:
        logger.warning("_notify_superadmins: no se encontraron superadmins activos con telegram_id")
        return

    role_label = ROLES_ES.get(user.get("role", ""), user.get("role", "N/D"))

    msg = (
        f"🔔 *Nueva solicitud de acceso*\n\n"
        f"👤 *Nombre:*  {user['name']}\n"
        f"📱 *Tel:*     {user.get('phone') or 'N/D'}\n"
        f"🛠️ *Rol:*     {role_label}\n"
        f"🏢 *Centro:*  {user.get('service_center_name') or 'No aplica'}\n"
    )

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Aprobar",  callback_data=f"status_approve_{user['id']}"),
        InlineKeyboardButton("❌ Rechazar", callback_data=f"status_reject_{user['id']}"),
    ]])

    for tid in superadmin_ids:
        try:
            await context.bot.send_message(
                chat_id=tid,
                text=msg,
                parse_mode="Markdown",
                reply_markup=kb
            )
        except Exception as e:
            logger.error(f"_notify_superadmins: error notificando a {tid}: {e}")


async def cancel_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("reg_data", None)
    context.user_data.pop("reg_tenants", None)
    await update.message.reply_text(
        "Registro cancelado. Si querés intentarlo de nuevo, mandame /start."
    )
    return ConversationHandler.END
