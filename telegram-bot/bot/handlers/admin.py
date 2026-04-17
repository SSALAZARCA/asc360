from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler

from core.config import logger
from core.constants import SELECTING_TENANT
from core.decorators import role_required
from keyboards.reply import get_main_keyboard
from services.api import get_pending_users, register_tenant_batch, set_user_status, get_all_tenants
from services.ai import classify_admin_intent

async def _show_tenant_selector(target, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Muestra al superadmin la lista de talleres disponibles como botones inline.
    Guarda la lista en user_data para referenciarla al confirmar la selección.
    Retorna el estado SELECTING_TENANT.
    """
    tenants = await get_all_tenants()
    if not tenants:
        await target.reply_text(
            "⚠️ No encontré talleres registrados en la red. "
            "Cargá centros de servicio desde el Panel Admin primero."
        )
        return ConversationHandler.END

    # Guardar mapa id→nombre para usarlo en el handler de confirmación
    context.user_data['tenant_map'] = {t['id']: t['name'] for t in tenants}

    TIPOS = {"service_center": "🔧 Centro", "distributor": "📦 Distribuidor"}
    kb = []
    for t in tenants:
        tipo = TIPOS.get(t.get('tenant_type', ''), '🏢')
        label = f"{tipo} {t['name']}"
        kb.append([InlineKeyboardButton(label, callback_data=f"sel_tenant_{t['id']}")])

    await target.reply_text(
        "🏢 *¿En qué taller vas a operar hoy?*\n\nSeleccioná uno de la lista:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )
    return SELECTING_TENANT


@role_required()
async def send_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_data = context.user_data.get("logged_in_user", {})
    user_role = user_data.get("role", "")
    user_name = user_data.get("name", update.effective_user.first_name)

    if user_role == "superadmin":
        # Limpiar taller activo al hacer /start — fuerza re-selección en la próxima recepción
        context.user_data.pop('active_tenant_id', None)
        context.user_data.pop('active_tenant_name', None)

        msg = (
            f"¡Hola {user_name}! 👋 Soy Sonia.\n\n"
            f"Reconozco tu acceso privilegiado como <b>Super Administrador</b> de la Red UM Colombia 🛡️.\n"
            f"Cuando vayas a recepcionar una moto te voy a pedir que elijas el taller.\n\n"
            f"¿En qué te puedo ayudar hoy?"
        )
    else:
        msg = (
            f"¡Hola {user_name}! 👋 Soy Sonia, tu asistente de servicio.\n\n"
            f"Si tenés una moto para ingresar, podés enviarme una foto de la matrícula, "
            f"mandarme una nota de voz o simplemente escribirme la placa."
        )

    await update.message.reply_html(msg, reply_markup=get_main_keyboard(user_role))
    return ConversationHandler.END


@role_required()
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await send_welcome(update, context)


@role_required(allowed_roles=["superadmin"])
async def handle_tenant_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Procesa la selección de taller del superadmin y la persiste en la sesión."""
    query = update.callback_query
    await query.answer()

    tenant_id = query.data.replace("sel_tenant_", "")
    tenant_map = context.user_data.get('tenant_map', {})
    tenant_name = tenant_map.get(tenant_id, "Taller seleccionado")

    # Persistir en sesión — válido hasta el próximo /start
    context.user_data['active_tenant_id']   = tenant_id
    context.user_data['active_tenant_name'] = tenant_name

    await query.edit_message_text(
        f"✅ *Taller activo: {tenant_name}*\n\n"
        f"Ya podés recepcionar motos en este taller. "
        f"Para cambiar de taller usá /start.",
        parse_mode="Markdown"
    )

    # Continuar con lo que el superadmin quería hacer
    pending       = context.user_data.pop('pending_action', None)
    pending_plate = context.user_data.pop('pending_plate', None)

    if pending == "reception":
        from keyboards.reply import get_main_keyboard
        from core.constants import ASKING_PLATE

        if pending_plate:
            # Ya tenía la placa antes de elegir taller → ir directo a procesarla
            await query.message.reply_text(
                f"✅ Taller: *{tenant_name}*. Dale, ya reviso la placa *{pending_plate}*...",
                parse_mode="Markdown",
                reply_markup=get_main_keyboard("superadmin")
            )
            from handlers.reception import process_plate
            # Necesitamos simular el update con el mensaje del callback
            return await process_plate(
                type('obj', (object,), {'message': query.message, 'effective_user': query.from_user})(),
                context,
                pending_plate
            )

        await query.message.reply_text(
            f"✅ Taller: *{tenant_name}*. Pasame la placa o una foto de la matrícula.",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard("superadmin")
        )
        return ASKING_PLATE

    await query.message.reply_text(
        f"✅ Taller activo: *{tenant_name}*. ¿Qué necesitás hacer?",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard("superadmin")
    )
    return ConversationHandler.END

@role_required(allowed_roles=["superadmin"])
async def show_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra el sub-menú del Panel Super Admin con botones Inline."""
    target = update.message if update.message else update.callback_query.message
    keyboard = [
        [InlineKeyboardButton("📌 ① Aprobar Solicitudes de Ingreso", callback_data="admin_pending")],
        [InlineKeyboardButton("🏢 ② Cargar Centros de Servicio / Distribuidoras", callback_data="admin_load_tenants")],
    ]
    await target.reply_text(
        "👑 *Panel Super Administrador*\n\n¿Qué deseas gestionar hoy?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

@role_required(allowed_roles=["superadmin"])
async def handle_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Enruta las opciones del Panel Admin."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "admin_pending":
        await show_pending_users_inner(query.message, context)
    elif query.data == "admin_load_tenants":
        context.user_data['awaiting_tenant_excel'] = True
        await query.message.reply_text(
            "📤 *Carga de Centros de Servicio*\n\n"
            "Envíame el archivo Excel (.xlsx) con los centros. Deberá tener las columnas en este orden:\n\n"
            "`nombre` | `nit` | `telefono` | `tipo` | `subdominio`\n\n"
            "El tipo puede ser *Centro de Servicio* o *Distribuidor / Repuestero*.\n\n"
            "Envía el archivo ahora, o escribe /cancelar para salir.",
            parse_mode="Markdown"
        )

async def show_pending_users_inner(target_msg, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lógica interna de pendientes (reutilizable desde menú o comando)."""
    await target_msg.reply_text("⏳ Buscando solicitudes pendientes de ingreso...")
    
    try:
        pending_users = await get_pending_users()
        if not pending_users:
            await target_msg.reply_text(
                "✅ *Todo al día.*\n\nNo tienes solicitudes de registro de personal pendientes en la fila.",
                parse_mode="Markdown",
                reply_markup=get_main_keyboard("superadmin")
            )
            return
        
        await target_msg.reply_text(f"📋 *Bandeja de Entrada* ({len(pending_users)} solicitudes en cola):", parse_mode="Markdown")
        
        ROLES_ES = {
            "technician": "Técnico / Mecánico",
            "jefe_taller": "Jefe / Coordinador de Taller",
            "superadmin": "Super Administrador",
            "parts_dealer": "Distribuidor de Repuestos",
            "client": "Cliente",
        }
        for u in pending_users:
            rol_es = ROLES_ES.get(u.get('role', ''), u.get('role', 'N/D'))
            msg = (
                f"👤 *Solicitante:* {u['name']}\n"
                f"📱 *Tel:* {u.get('phone', 'N/D')}\n"
                f"📧 *Email:* {u.get('email') or 'No proporcionado'}\n"
                f"🏢 *Centro de Servicio:* {u.get('service_center_name') or 'No proporcionado'}\n"
                f"🛠️ *Rol:* {rol_es}\n"
            )
            keyboard = [
                [InlineKeyboardButton("✅ Aprobar e Ingresar", callback_data=f"status_approve_{u['id']}")],
                [InlineKeyboardButton("❌ Rechazar", callback_data=f"status_reject_{u['id']}")]
            ]
            await target_msg.reply_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        logger.error(f"Error consultando pending users: {e}")
        await target_msg.reply_text(
            "⚠️ Ocurrió un error leyendo las solicitudes.",
            reply_markup=get_main_keyboard("superadmin")
        )
    else:
        # Adjuntar teclado como último mensaje para restaurar botones
        await target_msg.reply_text(
            "↓ *Usa los botones de arriba para aprobar o rechazar.*",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard("superadmin")
        )

@role_required(allowed_roles=["superadmin"])
async def show_pending_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler público para el comando /pending."""
    target = update.message if update.message else update.callback_query.message
    await show_pending_users_inner(target, context)

async def resolve_and_apply_user_status(update: Update, context: ContextTypes.DEFAULT_TYPE, name_query: str, action: str) -> None:
    """Busca en pendientes y aplica la acción si hay un match razonable."""
    if not name_query:
        await update.message.reply_text("¿A quién deseas procesar? No logré entender el nombre.")
        return

    pending = await get_pending_users()
    if not pending:
        await update.message.reply_text("No hay solicitudes pendientes en este momento.")
        return

    # Buscar match (muy básico por ahora)
    target = None
    name_query = name_query.lower()
    for u in pending:
        if name_query in u['name'].lower():
            target = u
            break
    
    if not target:
        await update.message.reply_text(f"No encontré a nadie llamado '{name_query}' en las solicitudes pendientes.")
        return

    new_status = "active" if action == "approve" else "rejected"
    user_updated = await set_user_status(target['id'], new_status)
    
    if user_updated:
        badge = "✅ *Aprobado*" if action == "approve" else "❌ *Rechazado*"
        await update.message.reply_text(
            f"Listo, procesé a *{target['name']}*.\nEstado: {badge}.",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard("superadmin")
        )
        if action == "approve" and user_updated.get("telegram_id"):
            try:
                await context.bot.send_message(
                    chat_id=user_updated["telegram_id"],
                    text=f"🎉 ¡Bienvenido a la Red UM Colombia!\n\nTu cuenta fue aprobada por el Super Administrador. Escribí /start para ver tu menú y empezar a trabajar con Sonia."
                )
            except: pass
    else:
        await update.message.reply_text("Uy, tuve un problema con el servidor al intentar procesar esa solicitud.")

@role_required(allowed_roles=["superadmin"])
async def handle_status_change(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    data = query.data
    parts = data.split("_")
    action = parts[1]  # approve o reject
    user_id = parts[2]
    
    new_status = "active" if action == "approve" else "rejected"
    
    try:
        user_updated = await set_user_status(user_id, new_status)
        if user_updated:
            badge = "✅ *Aprobado*" if action == "approve" else "❌ *Rechazado*"
            await query.edit_message_text(
                f"{query.message.text}\n\n{badge} por Super Admin.",
                parse_mode="Markdown"
            )
            
            # Notificar al Botonero del Nuevo Admin si aprueba
            if action == "approve" and user_updated.get("telegram_id"):
                try:
                    await context.bot.send_message(
                        chat_id=user_updated["telegram_id"],
                        text=f"🎉 ¡Bienvenido a la Red UM Colombia!\n\nTu cuenta fue aprobada por el Super Administrador. Escribí /start para ver tu menú y empezar a trabajar con Sonia."
                    )
                except: pass
        else:
             await query.edit_message_text("❌ Ocurrió un error cambiando el estado en el servidor.")
    except Exception as e:
        logger.error(f"Error procesando status handler: {e}")
        await query.edit_message_text("⚠️ Ocurrió un error de red intentando procesar esta solicitud.")
