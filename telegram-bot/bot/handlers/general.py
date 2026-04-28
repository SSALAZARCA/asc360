import re
import os
import tempfile
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from core.config import logger, USE_UNIFIED_INTENT
from core.constants import PLATE_REGEX, ASKING_PLATE, CORRECTING_DATA, L_ASKING_PLATE, SELECTING_TENANT
from core.decorators import role_required, check_cancel_intent
from services.ai import classify_admin_intent, classify_tech_intent, classify_unified_intent, transcribe_voice, extract_data_from_text, extract_part_data
from services.api import (
    update_order_status, post_work_log, post_order_parts,
    search_parts_catalog, get_part_by_number, get_part_by_factory_code,
    get_catalog_models_for_bot, search_parts_by_model, get_part_by_code,
    get_all_sections_for_model,
)
from .admin import send_welcome, show_pending_users_inner, _show_tenant_selector
from .technician import handle_active_orders

# Placeholder para functions de Recepción
from .reception import process_plate, send_vehicle_lifecycle, apply_correction_to_data


async def _send_diagram(message, section_id: str, caption: str) -> None:
    """Pide la imagen al backend (que la sirve desde MinIO) y la manda a Telegram."""
    from core.config import BACKEND_URL, SONIA_BOT_SECRET
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(
                f"{BACKEND_URL}/parts/section/{section_id}/diagram-image",
                headers={"x-sonia-secret": SONIA_BOT_SECRET},
                timeout=15.0,
            )
            res.raise_for_status()
        await message.reply_photo(photo=res.content, caption=caption, parse_mode="Markdown")
    except Exception as e:
        logger.warning(f"_send_diagram error (section {section_id}): {e}")
        await message.reply_text(caption + "\n_(diagrama no disponible)_", parse_mode="Markdown")


async def _show_diagrams_with_nav(message, sections: list, catalog_ctx: dict, user_data: dict) -> None:
    """Manda los diagramas y el menú de navegación. Activa awaiting_part_code."""
    for s in sections:
        await _send_diagram(
            message,
            s["section_id"],
            f"📋 *{s['section_code']}: {s['section_name']}*",
        )
    kb = [
        [InlineKeyboardButton("❌ No está en estos diagramas", callback_data="cat_not_here")],
        [InlineKeyboardButton("🔄 Buscar otra parte", callback_data="cat_new_search")],
    ]
    await message.reply_text(
        "Revisá los diagramas e ingresá el código de posición de la parte (ej: *B1-3*).",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    user_data["awaiting_part_code"] = {
        "model_code": catalog_ctx["model_code"],
        "order_id": catalog_ctx.get("order_id"),
        "plate": catalog_ctx.get("plate"),
        "catalog_mode": catalog_ctx["catalog_mode"],
    }


async def _after_catalog_result_kb() -> list:
    """Teclado inline que aparece después de mostrar un resultado o registrar un repuesto."""
    return [
        [InlineKeyboardButton("🔍 Buscar otro en estos diagramas", callback_data="cat_same_diagrams")],
        [InlineKeyboardButton("🔄 Buscar otra parte", callback_data="cat_new_search")],
        [InlineKeyboardButton("✅ Listo", callback_data="cat_done")],
    ]


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

    if intent == "SEARCH_PARTS_CATALOG":
        await handle_buscar_repuesto(update, context)
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
                "⚠️ No encontré secciones coincidentes en el catálogo.\n"
                "Intentá con otra descripción o consultá el catálogo físico.",
                parse_mode="Markdown"
            )
            return True

        model_code = sections[0].get("model_code") if sections else None
        catalog_ctx = {
            "model_code": model_code,
            "order_id": order_id,
            "plate": plate,
            "catalog_mode": False,
            "sections_shown": [s["section_id"] for s in sections],
            "current_sections": sections,
            "description": text,
        }
        user_data["catalog_context"] = catalog_ctx
        await _show_diagrams_with_nav(update.message, sections, catalog_ctx, user_data)
        return True

    # ── awaiting_catalog_search (superadmin busca sin order_id) ──────────────
    awaiting_cs = user_data.get("awaiting_catalog_search")
    if awaiting_cs:
        model_code = awaiting_cs["model_code"]

        await update.message.reply_text("🔍 Buscando en el catálogo...")
        sections = await search_parts_by_model(model_code, text)
        user_data.pop("awaiting_catalog_search", None)

        if not sections:
            await update.message.reply_text(
                "⚠️ No encontré secciones coincidentes. Intentá con otra descripción.",
                parse_mode="Markdown",
            )
            return True

        catalog_ctx = {
            "model_code": model_code,
            "order_id": None,
            "plate": None,
            "catalog_mode": True,
            "sections_shown": [s["section_id"] for s in sections],
            "current_sections": sections,
            "description": text,
        }
        user_data["catalog_context"] = catalog_ctx
        await _show_diagrams_with_nav(update.message, sections, catalog_ctx, user_data)
        return True

    # ── awaiting_part_code (ingresa código de posición del diagrama, ej: B1-3) ─
    awaiting_pc = user_data.get("awaiting_part_code")
    if awaiting_pc:
        model_code = awaiting_pc.get("model_code")
        catalog_mode = awaiting_pc.get("catalog_mode", False)
        order_id = awaiting_pc.get("order_id")
        plate = awaiting_pc.get("plate", "la moto")
        code = text.strip().upper()

        if not model_code:
            await update.message.reply_text("⚠️ Se perdió el contexto del modelo. Iniciá la búsqueda de nuevo.")
            user_data.pop("awaiting_part_code", None)
            return True

        part_item = await get_part_by_code(model_code, code)

        if not part_item:
            await update.message.reply_text(
                f"No encontré el código *{code}* en este modelo.\n"
                "Revisá el diagrama e ingresá el código nuevamente.",
                parse_mode="Markdown",
            )
            return True

        description = part_item.get("description_es") or part_item.get("description", "")
        msg = (
            f"✅ *{description}*\n"
            f"🏭 Factory: `{part_item['factory_part_number']}`"
        )

        if catalog_mode:
            user_data.pop("awaiting_part_code", None)
            kb = await _after_catalog_result_kb()
            await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
            return True

        user_data.pop("awaiting_part_code", None)
        kb = [[
            InlineKeyboardButton("✅ Sí, es esta", callback_data="parts_confirm_yes"),
            InlineKeyboardButton("❌ No", callback_data="parts_confirm_no"),
        ]]
        user_data["awaiting_part_type"] = {
            "order_id": order_id,
            "plate": plate,
            "model_code": model_code,
            "reference": part_item["factory_part_number"],
            "description": description,
        }
        await update.message.reply_text(
            f"{msg}\n\n¿Es esta la parte que necesitás?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb),
        )
        return True

    # ── awaiting_part_factory (fallback: técnico ingresa factory part number directo) ──
    awaiting_pf = user_data.get("awaiting_part_factory")
    if awaiting_pf:
        order_id = awaiting_pf["order_id"]
        plate = awaiting_pf["plate"]
        factory_code = text.strip().upper()

        part_item = await get_part_by_factory_code(factory_code)
        user_data.pop("awaiting_part_factory", None)

        description = ""
        if part_item:
            description = part_item.get("description_es") or part_item.get("description", "")
            msg = f"✅ *{description}*\n🏭 Factory: `{factory_code}`"
        else:
            description = f"Factory ref: {factory_code}"
            msg = f"No encontré `{factory_code}` en el catálogo, pero lo registramos igual."

        kb = [[
            InlineKeyboardButton("✅ Sí, es esta", callback_data="parts_confirm_yes"),
            InlineKeyboardButton("❌ No", callback_data="parts_confirm_no"),
        ]]
        user_data["awaiting_part_type"] = {
            "order_id": order_id,
            "plate": plate,
            "model_code": None,
            "reference": factory_code,
            "description": description,
        }
        await update.message.reply_text(
            f"{msg}\n\n¿Es esta la parte que necesitás?",
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
            kb = await _after_catalog_result_kb()
            await update.message.reply_text(
                f"✅ *{reference}* (x{qty}, {tipo}) registrado para la *{plate}*.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(kb),
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

    if "BUSCAR REPUESTO" in text:
        await handle_buscar_repuesto(update, context)
        return ConversationHandler.END

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

    elif data == "parts_confirm_yes":
        pending = user_data.pop("awaiting_part_type", None)
        if not pending:
            await query.edit_message_text("⚠️ Se perdió el contexto del repuesto.")
            return
        user_data["awaiting_part_confirm"] = pending
        kb = [[
            InlineKeyboardButton("💰 Pago",       callback_data="parts_ptype_paid"),
            InlineKeyboardButton("🛡️ Garantía",  callback_data="parts_ptype_warranty"),
            InlineKeyboardButton("📋 Cotización", callback_data="parts_ptype_quote"),
        ]]
        await query.edit_message_text(
            f"✅ *{pending['description']}*\n`{pending['reference']}`\n\n¿Cómo se carga?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb),
        )

    elif data == "parts_confirm_no":
        pending = user_data.pop("awaiting_part_type", None)
        if pending and not pending.get("catalog_mode"):
            user_data["awaiting_part_code"] = {
                "order_id": pending["order_id"],
                "plate": pending["plate"],
                "model_code": pending.get("model_code"),
            }
        await query.edit_message_text(
            "Ingresá el código correcto de la parte (ej: *B1-3*).",
            parse_mode="Markdown",
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


async def handle_catalog_model_callback(update, context):
    """Callback para selección de modelo en búsqueda de catálogo del superadmin."""
    query = update.callback_query
    await query.answer()
    model_code = query.data[len("catalog_model_"):]
    context.user_data["awaiting_catalog_search"] = {"model_code": model_code}
    await query.edit_message_text(
        f"Modelo seleccionado. ¿Qué parte necesitás?\n"
        f"Describila en español (ej: *carenaje izquierdo*, *filtro de aceite*).",
        parse_mode="Markdown",
    )


async def handle_catalog_nav_callback(update, context):
    """Maneja la navegación del catálogo de despiece (pattern: ^cat_)."""
    query = update.callback_query
    await query.answer()
    data = query.data
    user_data = context.user_data
    catalog_ctx = user_data.get("catalog_context", {})

    if data == "cat_same_diagrams":
        user_data["awaiting_part_code"] = {
            "model_code": catalog_ctx.get("model_code"),
            "order_id": catalog_ctx.get("order_id"),
            "plate": catalog_ctx.get("plate"),
            "catalog_mode": catalog_ctx.get("catalog_mode", True),
        }
        await query.edit_message_text(
            "Ingresá el código de posición de la parte en los diagramas (ej: *B1-3*).",
            parse_mode="Markdown",
        )

    elif data == "cat_not_here":
        kb = [
            [InlineKeyboardButton("📝 Ampliar descripción", callback_data="cat_new_desc")],
            [InlineKeyboardButton("📄 Ver más secciones",   callback_data="cat_more_sections")],
            [InlineKeyboardButton("🔄 Buscar otra parte",   callback_data="cat_new_search")],
        ]
        await query.edit_message_text("¿Qué querés hacer?", reply_markup=InlineKeyboardMarkup(kb))

    elif data == "cat_new_desc":
        catalog_mode = catalog_ctx.get("catalog_mode", True)
        if catalog_mode:
            user_data["awaiting_catalog_search"] = {"model_code": catalog_ctx.get("model_code")}
        else:
            user_data["awaiting_part_search"] = {
                "order_id": catalog_ctx.get("order_id"),
                "plate": catalog_ctx.get("plate", "la moto"),
            }
        await query.edit_message_text(
            "Describí la parte con más detalle para afinar la búsqueda:",
            parse_mode="Markdown",
        )

    elif data == "cat_more_sections":
        model_code = catalog_ctx.get("model_code")
        already_shown = catalog_ctx.get("sections_shown", [])

        all_sections = await get_all_sections_for_model(model_code)
        remaining = [s for s in all_sections if s["section_id"] not in already_shown]

        if not remaining:
            await query.edit_message_text(
                "Ya revisaste todas las secciones disponibles para este modelo.\n"
                "Probá ampliar la descripción o iniciá una nueva búsqueda.",
            )
            return

        next_sections = remaining[:3]
        catalog_ctx["sections_shown"] = already_shown + [s["section_id"] for s in next_sections]
        catalog_ctx["current_sections"] = next_sections
        user_data["catalog_context"] = catalog_ctx

        await query.edit_message_reply_markup(reply_markup=None)
        await _show_diagrams_with_nav(query.message, next_sections, catalog_ctx, user_data)

    elif data == "cat_new_search":
        catalog_mode = catalog_ctx.get("catalog_mode", True)
        order_id = catalog_ctx.get("order_id")
        plate = catalog_ctx.get("plate", "la moto")
        user_data.pop("catalog_context", None)
        user_data.pop("awaiting_part_code", None)

        if catalog_mode:
            models = await get_catalog_models_for_bot()
            if not models:
                await query.edit_message_text("⚠️ No hay catálogos disponibles.")
                return
            kb = [
                [InlineKeyboardButton(m["vehicle_model"], callback_data=f"catalog_model_{m['catalog_model_code']}")]
                for m in models
            ]
            await query.edit_message_text(
                "🔍 *Nueva búsqueda*\n\n¿Para qué modelo?",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(kb),
            )
        else:
            user_data["awaiting_part_search"] = {"order_id": order_id, "plate": plate}
            await query.edit_message_text(
                f"¿Qué repuesto necesitás para la *{plate}*? Describilo.",
                parse_mode="Markdown",
            )

    elif data == "cat_done":
        user_data.pop("catalog_context", None)
        user_data.pop("awaiting_part_code", None)
        await query.edit_message_text("✅ Búsqueda cerrada.")


async def handle_buscar_repuesto(update, context):
    """Muestra los modelos disponibles en el catálogo para que el superadmin elija."""
    models = await get_catalog_models_for_bot()
    if not models:
        await update.message.reply_text(
            "⚠️ No hay catálogos cargados todavía. Subí los PDFs desde el panel de administración."
        )
        return

    kb = [
        [InlineKeyboardButton(m["vehicle_model"], callback_data=f"catalog_model_{m['catalog_model_code']}")]
        for m in models
    ]
    await update.message.reply_text(
        "🔍 *Búsqueda en catálogo de despiece*\n\n¿Para qué modelo es el repuesto?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
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
