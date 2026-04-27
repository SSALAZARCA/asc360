import re
import os
import tempfile
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from core.config import logger, USE_UNIFIED_INTENT
from core.constants import PLATE_REGEX, ASKING_PLATE, CORRECTING_DATA, L_ASKING_PLATE, SELECTING_TENANT
from core.decorators import role_required, check_cancel_intent
from services.ai import classify_admin_intent, classify_tech_intent, classify_unified_intent, transcribe_voice, extract_data_from_text, extract_part_data
from services.api import (
    update_order_status, post_work_log, post_order_parts,
    search_parts_catalog, get_part_by_number, get_part_by_factory_code,
)
from .admin import send_welcome, show_pending_users_inner, _show_tenant_selector
from .technician import handle_active_orders

# Placeholder para functions de Recepción
from .reception import process_plate, send_vehicle_lifecycle, apply_correction_to_data


async def _start_reception(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Punto de entrada único para arrancar una recepción.
    Si el superadmin no tiene taller activo en sesión, muestra el selector primero.
    Para todos los demás roles, arranca directamente.
    """
    logged_in = context.user_data.get("logged_in_user", {})
    user_role = logged_in.get("role", "")

    if user_role == "superadmin" and not context.user_data.get("active_tenant_id"):
        context.user_data['pending_action'] = "reception"
        return await _show_tenant_selector(update.message, context)

    active_tenant_name = context.user_data.get("active_tenant_name")
    taller_txt = f" en *{active_tenant_name}*" if active_tenant_name else ""
    await update.message.reply_text(
        f"Dale{taller_txt}. Pasame la placa o una foto de la matrícula para arrancar.",
        parse_mode="Markdown"
    )
    return ASKING_PLATE

# Prompt de contexto para Whisper: mejora la precisión en placas colombianas
WHISPER_CONTEXT_PROMPT = (
    "Sonia, quiero ingresar la moto de placa NOI82G. "
    "La placa es Ene O I ochenta y dos Ge. "
    "Empiezo a trabajar en la ABC12D. "
    "Mostrame el historial de la XYZ789. "
    "Mis órdenes activas. "
    "La moto ya está lista, placa JKL45M."
)

ESTADO_ES = {
    "in_progress": "En Proceso 👨‍🔧",
    "on_hold_parts": "Esperando Repuestos ⏳",
    "on_hold_client": "Esperando Cliente ⏳",
    "external_work": "Trabajo Externo 🛠️",
    "completed": "Terminada ✅",
    "rescheduled": "Reprogramada 📅",
}

async def _ask_status_confirmation(update, context, placa: str, order_id, estado: str, confidence: float = 1.0):
    """Guarda el cambio pendiente y muestra botones de confirmación."""
    if not order_id:
        await update.message.reply_text(
            f"No encontré una orden activa para la *{placa.upper()}* asignada a vos.",
            parse_mode="Markdown"
        )
        return

    context.user_data["pending_status_change"] = {
        "order_id": order_id,
        "placa": placa.upper(),
        "estado": estado,
    }

    msg = f"Entendí: cambiar la *{placa.upper()}* a *{ESTADO_ES.get(estado, estado)}*."
    if confidence < 0.7:
        msg += "\n\n⚠️ No estoy muy segura — confirmame si lo entendí bien."
    msg += "\n¿Lo hacemos?"

    kb = [[
        InlineKeyboardButton("✅ Sí, cambiar", callback_data="status_confirm_yes"),
        InlineKeyboardButton("❌ No", callback_data="status_confirm_no"),
    ]]
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def handle_status_confirm(update, context):
    """Callback: confirma o cancela el cambio de estado pendiente."""
    query = update.callback_query
    await query.answer()

    pending = context.user_data.pop("pending_status_change", None)

    if query.data == "status_confirm_no" or not pending:
        await query.edit_message_text("Ok, nada cambió.")
        return

    logged_in = context.user_data.get("logged_in_user", {})
    user_id = logged_in.get("id")
    tenant_id = logged_in.get("tenant_id")
    success = await update_order_status(pending["order_id"], pending["estado"], user_id)

    if success:
        await query.edit_message_text(
            f"✅ Hecho, *{pending['placa']}* pasó a *{ESTADO_ES.get(pending['estado'], pending['estado'])}*.",
            parse_mode="Markdown"
        )
        # Agendar recordatorio de diagnóstico si pasa a in_progress
        if pending["estado"] == "in_progress":
            from services.api import get_tenant_config
            from handlers.technician import _diagnosis_reminder_job
            chat_id = query.message.chat_id
            order_id = pending["order_id"]
            job_name = f"diagnosis_{chat_id}_{order_id}"
            for job in context.job_queue.get_jobs_by_name(job_name):
                job.schedule_removal()
            reminder_minutes = 60
            if tenant_id:
                try:
                    config = await get_tenant_config(str(tenant_id))
                    reminder_minutes = config.get("diagnosis_reminder_minutes", 60)
                except Exception:
                    pass
            context.job_queue.run_repeating(
                _diagnosis_reminder_job,
                interval=reminder_minutes * 60,
                first=reminder_minutes * 60,
                name=job_name,
                data={"chat_id": chat_id, "order_id": order_id, "plate": pending["placa"]}
            )
    else:
        await query.edit_message_text("❌ No pude actualizar el estado. Intentá de nuevo desde el menú.")


async def _route_intent(update: Update, context: ContextTypes.DEFAULT_TYPE, intent_data: dict) -> int:
    """Enruta la intención detectada al handler correcto."""
    intent = intent_data.get("intent", "UNKNOWN")
    confidence = intent_data.get("confidence", 0.0)
    entities = intent_data.get("entities", {})
    placa = entities.get("placa")
    estado = entities.get("estado")
    target_name = entities.get("target_name")
    user_role = context.user_data.get("logged_in_user", {}).get("role", "")

    logger.info(f"[INTENT] role={user_role} intent={intent} conf={confidence} entities={entities}")

    # Confianza baja → pedir clarificación
    if confidence < 0.6 and intent not in ("GREETING", "CANCEL", "UNKNOWN"):
        await update.message.reply_text(
            "No te entendí bien. ¿Necesitás ingresar una moto, ver tus órdenes o consultarme algo?"
        )
        return ConversationHandler.END

    if intent == "GREETING":
        await send_welcome(update, context)
        return ConversationHandler.END

    if intent == "CANCEL":
        from keyboards.reply import get_main_keyboard
        logged_in_user = context.user_data.get("logged_in_user")
        logged_in_user_cached_at = context.user_data.get("logged_in_user_cached_at")
        context.user_data.clear()
        if logged_in_user:
            context.user_data["logged_in_user"] = logged_in_user
        if logged_in_user_cached_at:
            context.user_data["logged_in_user_cached_at"] = logged_in_user_cached_at
        await update.message.reply_text(
            "Listo, cancelado. Cuando necesités algo me avisás.",
            reply_markup=get_main_keyboard(user_role)
        )
        return ConversationHandler.END

    if intent == "START_RECEPTION":
        if placa:
            # Verificar taller antes incluso si ya viene la placa
            logged_in = context.user_data.get("logged_in_user", {})
            if logged_in.get("role") == "superadmin" and not context.user_data.get("active_tenant_id"):
                context.user_data['pending_action'] = "reception"
                context.user_data['pending_plate'] = placa
                return await _show_tenant_selector(update.message, context)
            await update.message.reply_text(f"Dale, ya reviso la placa {placa}...")
            return await process_plate(update, context, placa)
        else:
            return await _start_reception(update, context)

    if intent == "VIEW_LIFECYCLE":
        if placa:
            await update.message.reply_text(f"Dale, ya busco el historial de la *{placa}*...", parse_mode="Markdown")
            await send_vehicle_lifecycle(update, context, placa)
            return ConversationHandler.END
        else:
            await update.message.reply_text("Claro, de cuál moto? Dame la placa (ej. NOI82G).")
            return L_ASKING_PLATE

    if intent == "ACTIVE_ORDERS":
        await handle_active_orders(update, context)
        return ConversationHandler.END

    if intent == "CHANGE_STATUS":
        if placa and estado:
            from services.api import resolve_order_by_plate
            user_id = context.user_data["logged_in_user"]["id"]
            order_id = await resolve_order_by_plate(user_id, placa)
            await _ask_status_confirmation(update, context, placa, order_id, estado, confidence)
        else:
            await update.message.reply_text(
                "Para cambiar el estado necesito la placa y el nuevo estado. Ej: 'la NOI82G ya está lista'."
            )
        return ConversationHandler.END

    if intent == "PENDING_USERS":
        await show_pending_users_inner(update.message, context)
        return ConversationHandler.END

    if intent in ("APPROVE_USER", "REJECT_USER"):
        from .admin import resolve_and_apply_user_status
        action = "approve" if intent == "APPROVE_USER" else "reject"
        await resolve_and_apply_user_status(update, context, target_name, action)
        return ConversationHandler.END

    if intent == "LOAD_TENANTS":
        context.user_data['awaiting_tenant_excel'] = True
        from keyboards.reply import get_main_keyboard
        await update.message.reply_text(
            "📤 *Carga de Centros de Servicio*\n\nEnviame el archivo Excel (.xlsx)",
            parse_mode="Markdown", reply_markup=get_main_keyboard("superadmin")
        )
        return ConversationHandler.END

    if intent == "OPEN_PANEL":
        from .admin import show_admin_panel
        await show_admin_panel(update, context)
        return ConversationHandler.END

    # UNKNOWN o fallback
    await update.message.reply_text(
        "No estoy segura de qué necesitás. Podés usar los botones del menú o decirme la placa de la moto que querés gestionar."
    )
    return ConversationHandler.END


@role_required()
async def handle_general_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Enrutador Principal de Texto."""
    raw_text = update.message.text.strip()
    return await _process_text(update, context, raw_text)

async def _check_awaiting_states(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> bool:
    """
    Verifica si hay un estado pendiente (awaiting_*) y lo procesa.
    Retorna True si se manejó el mensaje, False si debe seguir el flujo normal.
    """
    chat_id = str(update.message.chat_id)
    user_data = context.user_data
    telegram_id = str(update.message.from_user.id)

    # ── awaiting_diagnosis (viene de job o de flujo directo) ──────────────────
    awaiting_diag = user_data.get("awaiting_diagnosis") or \
        context.bot_data.get("awaiting_diagnosis", {}).get(chat_id)

    if awaiting_diag:
        order_id = awaiting_diag.get("order_id")
        plate = awaiting_diag.get("plate", "la moto")

        # Cancelar job pendiente si existe
        job_name = f"diagnosis_{chat_id}_{order_id}"
        for job in context.job_queue.get_jobs_by_name(job_name):
            job.schedule_removal()

        # Guardar diagnóstico
        success = await post_work_log(order_id, text, telegram_id=telegram_id)

        # Limpiar estado
        user_data.pop("awaiting_diagnosis", None)
        context.bot_data.get("awaiting_diagnosis", {}).pop(chat_id, None)

        if success:
            await update.message.reply_text(
                f"✅ Diagnóstico de la *{plate}* guardado. Queda en la hoja de vida.",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("⚠️ No pude guardar el diagnóstico. Intentá de nuevo.")
        return True

    # ── awaiting_part_info ────────────────────────────────────────────────────
    awaiting_part = user_data.get("awaiting_part_info")
    if awaiting_part:
        order_id = awaiting_part.get("order_id")
        plate = awaiting_part.get("plate", "la moto")

        part_data = await extract_part_data(text)
        if not part_data.get("reference"):
            await update.message.reply_text(
                "No logré identificar la referencia del repuesto. ¿Me la decís más claro? "
                "Ej: 'filtro de aire referencia 12345, garantía'"
            )
            return True

        success = await post_order_parts(order_id, [part_data])
        user_data.pop("awaiting_part_info", None)

        if success:
            tipo = {"warranty": "garantía", "paid": "pago", "quote": "cotización"}.get(part_data["part_type"], part_data["part_type"])
            await update.message.reply_text(
                f"✅ Repuesto *{part_data['reference']}* (x{part_data['qty']}, {tipo}) registrado para la *{plate}*.",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("⚠️ No pude registrar el repuesto. Intentá de nuevo.")
        return True

    # ── awaiting_external_dest ────────────────────────────────────────────────
    awaiting_ext = user_data.get("awaiting_external_dest")
    if awaiting_ext:
        order_id = awaiting_ext.get("order_id")
        plate = awaiting_ext.get("plate", "la moto")

        diagnosis = f"Trabajo externo: {text}"
        await post_work_log(order_id, diagnosis, telegram_id=telegram_id)
        user_data.pop("awaiting_external_dest", None)

        await update.message.reply_text(
            f"✅ Anotado: la *{plate}* fue a *{text}*. Cuando vuelva pasala a Reprogramación.",
            parse_mode="Markdown"
        )
        return True

    # ── awaiting_part_search (técnico describe el repuesto que necesita) ──────
    awaiting_ps = user_data.get("awaiting_part_search")
    if awaiting_ps:
        order_id = awaiting_ps["order_id"]
        plate = awaiting_ps["plate"]

        await update.message.reply_text("🔍 Buscando en el catálogo de despiece...")
        sections = await search_parts_catalog(order_id, text)
        user_data.pop("awaiting_part_search", None)

        if not sections:
            await update.message.reply_text(
                "⚠️ No encontré secciones coincidentes.\n"
                "Buscá el *Factory Part Number* en el catálogo físico e ingresalo.",
                parse_mode="Markdown"
            )
            user_data["awaiting_part_factory"] = {"order_id": order_id, "plate": plate}
            return True

        user_data["pending_part_sections"] = {
            "order_id": order_id,
            "plate": plate,
            "sections": sections,
        }
        kb = [
            [InlineKeyboardButton(
                f"{s['section_code']}: {s['section_name'][:35]}",
                callback_data=f"parts_section_{s['section_id']}"
            )]
            for s in sections
        ]
        kb.append([InlineKeyboardButton("❌ No está en ninguna", callback_data=f"parts_notfound_{order_id}")])
        await update.message.reply_text(
            "Encontré estas secciones del catálogo. ¿En cuál está la parte que necesitás?",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return True

    # ── awaiting_part_number (técnico ingresa número de posición del diagrama) ─
    awaiting_pn = user_data.get("awaiting_part_number")
    if awaiting_pn:
        order_id = awaiting_pn["order_id"]
        plate = awaiting_pn["plate"]
        section_id = awaiting_pn["section_id"]

        part_item = await get_part_by_number(section_id, text.strip())
        user_data.pop("awaiting_part_number", None)

        if not part_item:
            await update.message.reply_text(
                f"No encontré el número *{text.strip()}* en ese diagrama.\n"
                "Ingresá el *Factory Part Number* directamente.",
                parse_mode="Markdown"
            )
            user_data["awaiting_part_factory"] = {"order_id": order_id, "plate": plate}
            return True

        user_data["awaiting_part_confirm"] = {
            "order_id": order_id,
            "plate": plate,
            "reference": part_item["um_part_number"],
            "description": part_item["description"],
        }
        kb = [[
            InlineKeyboardButton("💰 Pago",       callback_data="parts_ptype_paid"),
            InlineKeyboardButton("🛡️ Garantía",  callback_data="parts_ptype_warranty"),
            InlineKeyboardButton("📋 Cotización", callback_data="parts_ptype_quote"),
        ]]
        await update.message.reply_text(
            f"✅ Parte encontrada:\n*{part_item['description']}*\n"
            f"🏭 Fábrica: `{part_item['factory_part_number']}`\n"
            f"🔵 UM: `{part_item['um_part_number']}`\n\n"
            "¿Cómo se carga este repuesto?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return True

    # ── awaiting_part_factory (técnico ingresa factory part number directo) ────
    awaiting_pf = user_data.get("awaiting_part_factory")
    if awaiting_pf:
        order_id = awaiting_pf["order_id"]
        plate = awaiting_pf["plate"]
        factory_code = text.strip().upper()

        part_item = await get_part_by_factory_code(factory_code)
        user_data.pop("awaiting_part_factory", None)

        kb = [[
            InlineKeyboardButton("💰 Pago",       callback_data="parts_ptype_paid"),
            InlineKeyboardButton("🛡️ Garantía",  callback_data="parts_ptype_warranty"),
            InlineKeyboardButton("📋 Cotización", callback_data="parts_ptype_quote"),
        ]]
        if part_item:
            user_data["awaiting_part_confirm"] = {
                "order_id": order_id,
                "plate": plate,
                "reference": part_item["um_part_number"],
                "description": part_item["description"],
            }
            await update.message.reply_text(
                f"✅ Parte encontrada:\n*{part_item['description']}*\n"
                f"🏭 Fábrica: `{part_item['factory_part_number']}`\n"
                f"🔵 UM: `{part_item['um_part_number']}`\n\n"
                "¿Cómo se carga este repuesto?",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(kb)
            )
        else:
            user_data["awaiting_part_confirm"] = {
                "order_id": order_id,
                "plate": plate,
                "reference": factory_code,
                "description": f"Factory ref: {factory_code}",
            }
            await update.message.reply_text(
                f"No encontré `{factory_code}` en el catálogo, pero lo registramos igual.\n\n"
                "¿Cómo se carga este repuesto?",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(kb)
            )
        return True

    # ── awaiting_part_qty (técnico ingresa cantidad luego de elegir tipo) ──────
    awaiting_qty = user_data.get("awaiting_part_qty")
    if awaiting_qty:
        order_id = awaiting_qty["order_id"]
        plate = awaiting_qty["plate"]
        reference = awaiting_qty["reference"]
        part_type = awaiting_qty["part_type"]

        try:
            qty = int(text.strip())
            if qty < 1:
                raise ValueError
        except ValueError:
            await update.message.reply_text("Ingresá un número válido de unidades (ej: 1, 2, 4).")
            return True

        success = await post_order_parts(order_id, [{"reference": reference, "qty": qty, "part_type": part_type}])
        user_data.pop("awaiting_part_qty", None)

        tipo = {"warranty": "garantía", "paid": "pago", "quote": "cotización"}.get(part_type, part_type)
        if success:
            await update.message.reply_text(
                f"✅ Repuesto *{reference}* (x{qty}, {tipo}) registrado para la *{plate}*.",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("⚠️ No pude registrar el repuesto. Intentá de nuevo.")
        return True

    return False


async def _process_text(update: Update, context: ContextTypes.DEFAULT_TYPE, raw_text: str) -> int:
    text = raw_text.upper()

    if await check_cancel_intent(update, context, text):
        context.user_data.pop('pending_intent', None)
        return ConversationHandler.END

    # ── Pending awaiting states (post-recepción) ──────────────────────────────
    if await _check_awaiting_states(update, context, raw_text):
        return ConversationHandler.END

    # ── Botones del teclado persistente (resueltos por regex, sin IA) ──────────
    if raw_text.lower() in ["hola", "buenas", "buenos dias", "buenas tardes"]:
        await send_welcome(update, context)
        return ConversationHandler.END

    if "MIS ÓRDENES ACTIVAS" in text or "MIS ORDENES ACTIVAS" in text:
        await handle_active_orders(update, context)
        return ConversationHandler.END

    if "RECEPCION" in text or "RECEPCIÓN" in text or "NUEVA RECEPCI" in text:
        return await _start_reception(update, context)

    historia_keywords = re.compile(
        r'(?i)(historia|historial|hoja de vida|hoja vida|ciclo de vida|expediente|antecedentes)', re.IGNORECASE
    )
    if historia_keywords.search(raw_text):
        cleaned_text = "".join(text.split())
        plate_match = PLATE_REGEX.search(cleaned_text)
        if plate_match:
            plate_found = plate_match.group(0)
            await update.message.reply_text(f"Dale, ya busco el historial de la *{plate_found}*...", parse_mode="Markdown")
            await send_vehicle_lifecycle(update, context, plate_found)
            return ConversationHandler.END
        else:
            await update.message.reply_text("Claro, de cuál moto? Decime la placa (ej. *NOI82G*).", parse_mode="Markdown")
            return L_ASKING_PLATE

    user_role = context.user_data.get("logged_in_user", {}).get("role", "")

    # ── Clasificador unificado (feature flag) ──────────────────────────────────
    if USE_UNIFIED_INTENT:
        intent_data = await classify_unified_intent(raw_text, user_role)
        return await _route_intent(update, context, intent_data)

    # ── Flujo legacy (USE_UNIFIED_INTENT=false) ────────────────────────────────
    if user_role == "superadmin":
        admin_data = await classify_admin_intent(raw_text)
        intent = admin_data.get("intent")
        target_name = admin_data.get("target_name")

        if intent == "PENDING_USERS":
            await show_pending_users_inner(update.message, context)
            return ConversationHandler.END
        elif intent in ["APPROVE_USER", "REJECT_USER"]:
            from .admin import resolve_and_apply_user_status
            action = "approve" if intent == "APPROVE_USER" else "reject"
            await resolve_and_apply_user_status(update, context, target_name, action)
            return ConversationHandler.END
        elif intent == "LOAD_TENANTS":
            context.user_data['awaiting_tenant_excel'] = True
            from keyboards.reply import get_main_keyboard
            await update.message.reply_text(
                "📤 *Carga de Centros de Servicio*\n\nEnviame el archivo Excel (.xlsx)",
                parse_mode="Markdown", reply_markup=get_main_keyboard("superadmin")
            )
            return ConversationHandler.END
        elif intent == "OPEN_PANEL":
            from .admin import show_admin_panel
            await show_admin_panel(update, context)
            return ConversationHandler.END

    if user_role in ["technician", "superadmin", "jefe_taller"]:
        tech_data = await classify_tech_intent(raw_text)
        intent = tech_data.get("intent")
        placa = tech_data.get("placa")
        nuevo_estado = tech_data.get("estado")

        if intent == "ACTIVE_ORDERS":
            await handle_active_orders(update, context)
            return ConversationHandler.END

        if intent == "CHANGE_STATUS" and placa and nuevo_estado:
            from services.api import resolve_order_by_plate
            order_id = await resolve_order_by_plate(context.user_data["logged_in_user"]["id"], placa)
            await _ask_status_confirmation(update, context, placa, order_id, nuevo_estado, tech_data.get("confidence", 0.5))
            return ConversationHandler.END

    # ── Detección automática de placa (Último recurso) ────────────────────────
    plate_match = PLATE_REGEX.search(text.replace(" ", ""))
    if plate_match:
        plate_found = plate_match.group(0)
        await update.message.reply_text(f"Dame un segundito, ya reviso la placa {plate_found}...")
        return await process_plate(update, context, plate_found)

    if len(text) < 5 and not PLATE_REGEX.search(text):
        await update.message.reply_text("¿Me estás hablando? Si necesitás ayuda, escribime la placa de la moto (ej. NOI82G) o mandame una foto de la matrícula.")
        return ConversationHandler.END

    await update.message.reply_text("No te entendí bien. Si necesitás ingresar una moto, pasame la placa o una foto del SOAT.")
    return ConversationHandler.END

@role_required()
async def handle_general_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Escuchando tu nota de voz... 🎧")
    voice_file = await update.message.voice.get_file()

    fd, path = tempfile.mkstemp(suffix=".ogg")
    os.close(fd)

    await voice_file.download_to_drive(path)

    transcript = await transcribe_voice(path, prompt=WHISPER_CONTEXT_PROMPT)
    os.remove(path)

    if not transcript:
        await update.message.reply_text("Uy, tuve un problema escuchando la nota de voz.")
        return ConversationHandler.END

    if await check_cancel_intent(update, context, transcript):
        return ConversationHandler.END

    transcript = transcript.strip()

    # ── Pending awaiting states (post-recepción, voz) ─────────────────────────
    if await _check_awaiting_states(update, context, transcript):
        return ConversationHandler.END

    if USE_UNIFIED_INTENT:
        user_role = context.user_data.get("logged_in_user", {}).get("role", "")
        intent_data = await classify_unified_intent(transcript, user_role)
        return await _route_intent(update, context, intent_data)

    return await _process_text(update, context, transcript)

# ── Manejadores del Estado L_ASKING_PLATE (Hoja de Vida) ──
async def handle_parts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja todos los callbacks del flujo de catálogo de repuestos (pattern: ^parts_)."""
    query = update.callback_query
    await query.answer()
    data = query.data
    user_data = context.user_data

    if data.startswith("parts_search_"):
        order_id = data[len("parts_search_"):]
        action = user_data.pop("awaiting_parts_action", {})
        plate = action.get("plate", "la moto")
        user_data["awaiting_part_search"] = {"order_id": order_id, "plate": plate}
        await query.edit_message_text(
            f"🔍 Describime qué repuesto necesitás para la *{plate}* "
            f"(ej: 'filtro de aceite', 'manija de freno izquierda')",
            parse_mode="Markdown"
        )

    elif data.startswith("parts_manual_"):
        order_id = data[len("parts_manual_"):]
        action = user_data.pop("awaiting_parts_action", {})
        plate = action.get("plate", "la moto")
        user_data["awaiting_part_info"] = {"order_id": order_id, "plate": plate}
        await query.edit_message_text(
            f"📝 ¿Qué repuesto necesitás para la *{plate}*?\n"
            "Decime referencia, cantidad y si es garantía, pago o cotización.",
            parse_mode="Markdown"
        )

    elif data.startswith("parts_section_"):
        section_id = data[len("parts_section_"):]
        pending = user_data.get("pending_part_sections", {})
        if not pending:
            await query.edit_message_text("⚠️ Se perdió el contexto. Volvé a marcar el estado.")
            return

        order_id = pending["order_id"]
        plate = pending["plate"]
        sections = pending.get("sections", [])
        section = next((s for s in sections if s["section_id"] == section_id), None)

        if not section:
            await query.edit_message_text("⚠️ Sección no encontrada.")
            return

        user_data.pop("pending_part_sections", None)
        user_data["awaiting_part_number"] = {
            "order_id": order_id,
            "plate": plate,
            "section_id": section_id,
        }

        await query.edit_message_reply_markup(reply_markup=None)
        if section.get("diagram_url"):
            await query.message.reply_photo(
                photo=section["diagram_url"],
                caption=(
                    f"📋 *{section['section_code']}: {section['section_name']}*\n\n"
                    "Ingresá el *número* de la parte en el diagrama (ej: 5, 3-1, 12)"
                ),
                parse_mode="Markdown"
            )
        else:
            await query.message.reply_text(
                f"📋 *{section['section_code']}: {section['section_name']}*\n\n"
                "No hay diagrama para esta sección. Ingresá el número de la parte.",
                parse_mode="Markdown"
            )

    elif data.startswith("parts_notfound_"):
        order_id = data[len("parts_notfound_"):]
        pending = user_data.pop("pending_part_sections", {})
        plate = pending.get("plate", "la moto")
        user_data["awaiting_part_factory"] = {"order_id": order_id, "plate": plate}
        await query.edit_message_text(
            "🔎 Buscá en el catálogo físico e ingresá el *Factory Part Number* de la parte.",
            parse_mode="Markdown"
        )

    elif data.startswith("parts_ptype_"):
        part_type = data[len("parts_ptype_"):]
        pending = user_data.get("awaiting_part_confirm", {})
        if not pending:
            await query.edit_message_text("⚠️ Se perdió el contexto del repuesto.")
            return

        user_data.pop("awaiting_part_confirm", None)
        user_data["awaiting_part_qty"] = {
            "order_id": pending["order_id"],
            "plate": pending["plate"],
            "reference": pending["reference"],
            "description": pending.get("description", pending["reference"]),
            "part_type": part_type,
        }
        tipo = {"paid": "pago 💰", "warranty": "garantía 🛡️", "quote": "cotización 📋"}.get(part_type, part_type)
        await query.edit_message_text(
            f"✅ Tipo: *{tipo}*\n\n¿Cuántas unidades necesitás?",
            parse_mode="Markdown"
        )


@role_required()
async def process_lifecycle_plate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    direct_plate = None
    transcript = ""
    
    # 1. Extraer Placa (Texto)
    if update.message.text:
        text = update.message.text.upper()
        if await check_cancel_intent(update, context, text): return ConversationHandler.END
        
        cleaned_text = "".join(text.split())
        plate_match = PLATE_REGEX.search(cleaned_text)
        if plate_match:
            direct_plate = plate_match.group(0)
        else:
            extracted = await extract_data_from_text(text)
            if extracted and extracted.get("placa"):
                direct_plate = "".join(extracted.get("placa").upper().split())
                
    # 2. Extraer Placa (Audio)
    elif getattr(update.message, "voice", None):
        await update.message.reply_text("Escuchando tu nota de voz para extraer la placa... 🎧")
        import tempfile, os
        voice_file = await update.message.voice.get_file()
        fd, path = tempfile.mkstemp(suffix=".ogg")
        os.close(fd)
        await voice_file.download_to_drive(path)
        transcript = await transcribe_voice(path, prompt="La placa es Noi 82G.")
        os.remove(path)
        
        logger.info(f"🎤 [LIFECYCLE STATE VOICE] Transcripción: '{transcript}'")
        
        if transcript:
            if await check_cancel_intent(update, context, transcript): return ConversationHandler.END
            cleaned_text = "".join(transcript.upper().split())
            plate_match = PLATE_REGEX.search(cleaned_text)
            
            if plate_match:
                direct_plate = plate_match.group(0)
            else:
                extracted = await extract_data_from_text(transcript)
                if extracted and extracted.get("placa"):
                    direct_plate = "".join(extracted.get("placa").upper().split())
        else:
            await update.message.reply_text("Uy, tuve un problema escuchando la nota de voz. ¿Me escribes la placa?")
            return L_ASKING_PLATE
            
    # 3. Flujo final
    if direct_plate:
        await update.message.reply_text(f"🔍 Buscando la hoja de vida de la moto *{direct_plate}*...", parse_mode="Markdown")
        await send_vehicle_lifecycle(update, context, direct_plate)
        return ConversationHandler.END
    else:
        msg = transcript if transcript else "ese mensaje"
        await update.message.reply_text(f"Te entendí, pero no logré hallar una placa válida. ¿Me la escribes directa? (ej. NOI82G)")
        return L_ASKING_PLATE
