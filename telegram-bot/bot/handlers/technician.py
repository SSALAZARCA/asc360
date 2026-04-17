import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from core.config import logger
from core.decorators import role_required
from keyboards.reply import get_main_keyboard
from handlers.reception import fmt_bogota
from services.api import (
    get_admin_dashboard,
    get_tenant_active_orders,
    get_technician_active_orders,
    update_order_status,
    get_tenant_config,
)

@role_required(allowed_roles=["superadmin", "jefe_taller", "technician"])
async def handle_active_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja la vista de Órdenes Activas dependiendo del rol del usuario."""
    target = update.message if update.message else update.callback_query.message
    user_data = context.user_data.get("logged_in_user", {})
    user_role = user_data.get("role")
    user_id = user_data.get("id")
    tenant_id = user_data.get("tenant_id")
    
    if not user_role or not user_id:
        return

    estado_es = {
        "received": "Recepcionada 📋", 
        "scheduled": "Programada 📅", 
        "in_progress": "En Proceso 👨‍🔧", 
        "on_hold_parts": "Faltan Repuestos ⏳", 
        "on_hold_client": "Esperando Cliente ⏳", 
        "external_work": "Trabajo Externo 🛠️"
    }

    try:
        # LÓGICA SUPER ADMIN
        if user_role == "superadmin":
            await target.reply_text("📊 *Consultando métricas de la red nacional...*", parse_mode="Markdown")
            metrics = await get_admin_dashboard()
            if metrics:
                msg = (
                    f"📊 *DASHBOARD NACIONAL - ÓRDENES ACTIVAS*\n\n"
                    f"🔹 *Total Motocicletas en Taller:* {metrics['total_active']}\n\n"
                    f"⏱️ *Tiempos de Permanencia (Antigüedad):*\n"
                    f"• 🟢 0 a 1 día: *{metrics['0_1_days']}* motos\n"
                    f"• 🟡 1 a 3 días: *{metrics['1_3_days']}* motos\n"
                    f"• 🟠 3 a 5 días: *{metrics['3_5_days']}* motos\n"
                    f"• 🔴 Más de 5 días: *{metrics['gt_5_days']}* motos\n"
                )
                await target.reply_text(msg, parse_mode="Markdown", reply_markup=get_main_keyboard(user_role))
            else:
                await target.reply_text("⚠️ No pude consultar el dashboard.")
        
        # LÓGICA JEFE DE TALLER — ve todas las motos con botones de acción
        elif user_role == "jefe_taller":
            await target.reply_text("🏢 *Buscando motocicletas activas en tu centro de servicio...*", parse_mode="Markdown")
            orders = await get_tenant_active_orders(tenant_id)
            if orders is not None:
                if not orders:
                    await target.reply_text("✅ ¡El taller no tiene motos pendientes!", reply_markup=get_main_keyboard(user_role))
                    return
                await target.reply_text(f"🏢 *Motos Activas en el Taller:* {len(orders)}", parse_mode="Markdown")
                for o in orders:
                    plate_str = o.get('plate') or 'S/P'
                    msg = f"🏍 *Placa:* `{plate_str}`\n🔹 *Ingreso:* {fmt_bogota(o.get('created_at') or '', '%d/%m/%Y')}\n🔹 *Estado:* {estado_es.get(o['status'], o['status'])}"
                    kb = [
                        [InlineKeyboardButton("👨‍🔧  Empezar / Retomar Trabajo", callback_data=f"ord_stat_{o['id']}_in_progress")],
                        [InlineKeyboardButton("⏳ Falta Repuesto", callback_data=f"ord_stat_{o['id']}_on_hold_parts"), InlineKeyboardButton("⏳ Espera Cliente", callback_data=f"ord_stat_{o['id']}_on_hold_client")],
                        [InlineKeyboardButton("🛠️ Torno/Tercero", callback_data=f"ord_stat_{o['id']}_external_work"), InlineKeyboardButton("✅ Terminar", callback_data=f"ord_stat_{o['id']}_completed")]
                    ]
                    await target.reply_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
                await target.reply_text("↓ Usá los botones para gestionar cualquier moto del taller.", reply_markup=get_main_keyboard(user_role))
            else:
                await target.reply_text("⚠️ No pude consultar las motos del taller.")

        # LÓGICA TÉCNICO
        elif user_role == "technician":
            await target.reply_text("⏳ *Buscando tus motocicletas asignadas...*", parse_mode="Markdown")
            orders = await get_technician_active_orders(user_id)
            if orders is not None:
                if not orders:
                    await target.reply_text("✅ ¡No tienes órdenes activas! Todo está al día.", reply_markup=get_main_keyboard(user_role))
                    return
                await target.reply_text(f"🏍 *Tienes {len(orders)} órdenes asignadas:*", parse_mode="Markdown")
                for o in orders:
                    plate_str = o.get('plate') or 'S/P'
                    msg = f"🏍 *Placa:* `{plate_str}`\n🔹 *Ingreso:* {fmt_bogota(o.get('created_at') or '', '%d/%m/%Y')}\n🔹 *Estado:* {estado_es.get(o['status'], o['status'])}"
                    kb = [
                        [InlineKeyboardButton("👨‍🔧  Empezar / Retomar Trabajo", callback_data=f"ord_stat_{o['id']}_in_progress")],
                        [InlineKeyboardButton("⏳ Falta Repuesto", callback_data=f"ord_stat_{o['id']}_on_hold_parts"), InlineKeyboardButton("⏳ Espera Cliente", callback_data=f"ord_stat_{o['id']}_on_hold_client")],
                        [InlineKeyboardButton("🛠️ Torno/Tercero", callback_data=f"ord_stat_{o['id']}_external_work"), InlineKeyboardButton("✅ Terminar", callback_data=f"ord_stat_{o['id']}_completed")]
                    ]
                    await target.reply_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
                await target.reply_text("↓ Usa los botones para cambiar el estado.", reply_markup=get_main_keyboard(user_role))
            else:
                await target.reply_text("⚠️ No pude consultar tus órdenes.")
                
    except Exception as e:
        logger.error(f"Error consultando órdenes activas: {e}")
        await target.reply_text("⚠️ Hubo un error de conexión al buscar las órdenes.")

async def _diagnosis_reminder_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job diferido: pregunta al técnico qué encontró en la moto."""
    job_data = context.job.data
    chat_id = job_data.get("chat_id")
    order_id = job_data.get("order_id")
    plate = job_data.get("plate", "la moto")

    context.bot_data.setdefault("awaiting_diagnosis", {})[str(chat_id)] = {
        "order_id": order_id,
        "plate": plate
    }
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"🔍 ¿Qué encontraste en la *{plate}*? Contame el diagnóstico (podés mandar un audio o texto).",
        parse_mode="Markdown"
    )


@role_required(allowed_roles=["superadmin", "jefe_taller", "technician"])
async def handle_order_status_change(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa el evento al pichar un botón inline de orden activa (ord_stat_)."""
    query = update.callback_query
    await query.answer()
    if not query.data.startswith("ord_stat_"):
        return

    rest = query.data[9:]
    order_id = rest[:36]
    nuevo_estado = rest[37:]
    tech_id = context.user_data.get("logged_in_user", {}).get("id")
    tenant_id = context.user_data.get("logged_in_user", {}).get("tenant_id")
    chat_id = query.message.chat_id

    # Obtener placa de la orden activa (si está cacheada)
    active_orders = context.user_data.get("cached_active_orders", [])
    plate = next((o.get("plate", "la moto") for o in active_orders if o.get("id") == order_id), "la moto")

    success = await update_order_status(order_id, nuevo_estado, tech_id)
    if not success:
        await query.message.reply_text("❌ No se pudo actualizar el estado o hubo error de red.")
        return

    estado_es = {
        "in_progress": "En Proceso 👨‍🔧",
        "on_hold_parts": "Pausada (Faltan Repuestos) ⏳",
        "on_hold_client": "Pausada (Esperando Cliente) ⏳",
        "external_work": "Trabajo Externo 🛠️",
        "completed": "Orden Terminada ✅",
        "rescheduled": "Reprogramada 📅",
    }
    await query.edit_message_text(
        f"✅ *Estado Actualizado*\n\nEl nuevo estado es: *{estado_es.get(nuevo_estado, nuevo_estado)}*",
        parse_mode="Markdown"
    )

    # --- Lógica post-cambio según el nuevo estado ---

    if nuevo_estado == "in_progress":
        # Cancelar job anterior si existía
        job_name = f"diagnosis_{chat_id}_{order_id}"
        current_jobs = context.job_queue.get_jobs_by_name(job_name)
        for job in current_jobs:
            job.schedule_removal()

        # Obtener intervalo configurado del tenant
        reminder_minutes = 60
        if tenant_id:
            try:
                config = await get_tenant_config(tenant_id)
                reminder_minutes = config.get("diagnosis_reminder_minutes", 60)
            except Exception:
                pass

        context.job_queue.run_repeating(
            _diagnosis_reminder_job,
            interval=reminder_minutes * 60,
            first=reminder_minutes * 60,
            name=job_name,
            data={"chat_id": chat_id, "order_id": order_id, "plate": plate}
        )
        await query.message.reply_text(
            f"🔧 ¡Dale con la *{plate}*! En *{reminder_minutes} minutos* te pregunto qué encontraste.",
            parse_mode="Markdown"
        )

    elif nuevo_estado == "on_hold_parts":
        context.user_data["awaiting_part_info"] = {"order_id": order_id, "plate": plate}
        await query.message.reply_text(
            f"⏳ Anotado. ¿Qué repuesto necesitás para la *{plate}*?\n"
            "Decime la referencia, cantidad y si es por garantía, pago o cotización.",
            parse_mode="Markdown"
        )

    elif nuevo_estado == "external_work":
        context.user_data["awaiting_external_dest"] = {"order_id": order_id, "plate": plate}
        await query.message.reply_text(
            f"🛠️ ¿A dónde va la *{plate}*? (Ej: torno de Hernández, pintura, etc.)",
            parse_mode="Markdown"
        )
