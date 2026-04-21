import asyncio
import os
import re
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ConversationHandler
)
from core.config import TELEGRAM_TOKEN, logger
from core.constants import (
    ASKING_PLATE, CONFIRMING_OCR, CORRECTING_DATA,
    CONFIRMING_CLIENT, ASKING_PHONE, ASKING_KM,
    ASKING_PHOTOS, ASKING_MOTIVE, CONFIRMING_MOTIVE, CORRECTING_MOTIVE,
    CONFIRMING_SERVICE_TYPE, L_ASKING_PLATE, SELECTING_TENANT,
    O_NAME, O_PHONE, O_ROLE, O_TENANT, O_CONFIRM,
    OTP_ASKING_PLATE, OTP_ASKING_CODE, OTP_CONFIRMING
)
from core.decorators import role_required, check_cancel_intent, CANCEL_PATTERN
from keyboards.reply import get_main_keyboard
from handlers.general import handle_general_text, handle_general_voice, process_lifecycle_plate, handle_status_confirm
from handlers.admin import (
    start_command, show_admin_panel, handle_admin_menu,
    show_pending_users, handle_status_change, handle_tenant_selection
)
from handlers.registration import (
    start_or_register, begin_registration,
    handle_reg_name, handle_reg_phone, handle_reg_role,
    handle_reg_tenant, handle_reg_confirm, cancel_registration
)
from handlers.reception import (
    prompt_plate, process_plate, handle_ocr_confirmation,
    apply_correction_to_data, handle_client_confirmation,
    handle_phone, handle_km_and_photos, handle_photos, handle_photos_done,
    handle_motive, handle_motive_confirmation, handle_motive_correction,
    handle_service_type_selection, handle_data_correction
)
from handlers.otp import (
    start_otp_flow, otp_handle_plate, otp_handle_code, otp_handle_confirm
)
# Handlers de carga excel no migrados aun en bloque de refactor 1

async def cancel_command(update, context):
    """Cancela cualquier flujo activo y restaura el teclado principal."""
    logged_in_user = context.user_data.get("logged_in_user")
    logged_in_user_cached_at = context.user_data.get("logged_in_user_cached_at")
    context.user_data.clear()
    if logged_in_user:
        context.user_data["logged_in_user"] = logged_in_user
    if logged_in_user_cached_at:
        context.user_data["logged_in_user_cached_at"] = logged_in_user_cached_at
    user_role = logged_in_user.get("role", "none") if logged_in_user else "none"
    await update.message.reply_text(
        "Listo, cancelado. Cuando quieras arrancamos de nuevo.",
        reply_markup=get_main_keyboard(user_role)
    )
    return ConversationHandler.END


async def cancel_voice_handler(update, context):
    """
    Handler de voz universal para estados que solo esperan botones.
    Transcribe el audio y cancela si detecta intención de cancelación.
    Si no es cancelación, guía al usuario a usar los botones.
    """
    import tempfile, os
    from services.ai import transcribe_voice
    try:
        voice_file = await update.message.voice.get_file()
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp_path = tmp.name
        await voice_file.download_to_drive(tmp_path)
        transcript = await transcribe_voice(tmp_path)
        os.unlink(tmp_path)
    except Exception:
        transcript = ""

    if transcript and CANCEL_PATTERN.search(transcript):
        return await cancel_command(update, context)

    await update.message.reply_text(
        "Necesito que toques una de las opciones de arriba. "
        "Si querés cancelar, decí o escribí *cancelar*.",
        parse_mode="Markdown"
    )
    return None  # Permanece en el estado actual

async def timeout_handler(update, context):
    """Notifica al usuario que la sesión expiró por inactividad."""
    logged_in_user = context.user_data.get("logged_in_user")
    logged_in_user_cached_at = context.user_data.get("logged_in_user_cached_at")
    context.user_data.clear()
    if logged_in_user:
        context.user_data["logged_in_user"] = logged_in_user
    if logged_in_user_cached_at:
        context.user_data["logged_in_user_cached_at"] = logged_in_user_cached_at
    user_role = logged_in_user.get("role", "none") if logged_in_user else "none"
    try:
        target = update.message if update and update.message else None
        if target:
            await target.reply_text(
                "La sesión expiró por inactividad. No pasa nada, cuando quieras arrancamos de nuevo.",
                reply_markup=get_main_keyboard(user_role)
            )
    except Exception:
        pass
    return ConversationHandler.END

# Manejador de Errores Global ASYNC
async def error_handler(update, context):
    """Manejador Global de Excepciones para no asfixiar el bot."""
    logger.error(f"Error procesando Telegram Update: {context.error}", exc_info=context.error)
    try:
        if isinstance(update, dict): return
        target = update.message if update.message else update.callback_query.message if update.callback_query else None
        if target:
            await target.reply_text("Uy, se me enredó algo. Dale de nuevo en unos segundos.")
    except Exception as e:
        logger.error(f"Error en el ErrorHandler: {e}")


def main() -> None:
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN no configurado en Entorno.")
        return

    from telegram.request import HTTPXRequest
    request = HTTPXRequest(
        connect_timeout=20.0,    # tiempo para establecer conexión
        read_timeout=40.0,       # tiempo para recibir respuesta (PDF puede tardar)
        write_timeout=40.0,      # tiempo para enviar archivos grandes
        pool_timeout=30.0,
        http_version="1.1",      # más estable que HTTP/2 en redes lentas
    )
    # Configurar APScheduler con SQLAlchemyJobStore para persistir jobs entre reinicios
    database_url = os.environ.get("DATABASE_URL", "")
    jobstores = {}
    if database_url:
        # APScheduler usa SQLAlchemy síncrono — convertir asyncpg a psycopg2 si es necesario
        sync_db_url = database_url.replace("postgresql+asyncpg://", "postgresql://")
        try:
            from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
            jobstores = {"default": SQLAlchemyJobStore(url=sync_db_url)}
            logger.info("APScheduler: usando SQLAlchemyJobStore (jobs persistentes)")
        except Exception as e:
            logger.warning(f"APScheduler: no se pudo configurar SQLAlchemyJobStore: {e}. Jobs en memoria.")

    application = ApplicationBuilder().token(TELEGRAM_TOKEN).request(request).build()

    if jobstores:
        application.job_queue.scheduler.configure(jobstores=jobstores)
    
    # Manejo Errores Globales
    application.add_error_handler(error_handler)

    # Comandos Base (sin /start — lo maneja reg_conv)
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(CommandHandler("panel", show_admin_panel))
    application.add_handler(CommandHandler("pending", show_pending_users))

    # Flujo de auto-registro — debe registrarse ANTES de master_conv
    reg_conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start_or_register),
            CallbackQueryHandler(begin_registration, pattern="^start_registration$"),
        ],
        states={
            O_NAME:    [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reg_name)],
            O_PHONE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reg_phone)],
            O_ROLE:    [CallbackQueryHandler(handle_reg_role,    pattern="^reg_role_")],
            O_TENANT:  [CallbackQueryHandler(handle_reg_tenant,  pattern="^reg_tenant_")],
            O_CONFIRM: [CallbackQueryHandler(handle_reg_confirm, pattern="^reg_confirm_")],
        },
        fallbacks=[CommandHandler("cancel", cancel_registration)],
        allow_reentry=True,
    )
    application.add_handler(reg_conv)

    # Flujo OTP — debe registrarse ANTES de master_conv
    otp_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r'^Ingresar OTP'), start_otp_flow),
        ],
        states={
            OTP_ASKING_PLATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND | filters.VOICE, otp_handle_plate)
            ],
            OTP_ASKING_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND | filters.VOICE, otp_handle_code)
            ],
            OTP_CONFIRMING: [
                CallbackQueryHandler(otp_handle_confirm, pattern="^otp_confirm_")
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_command)],
        allow_reentry=True,
        conversation_timeout=300,
    )
    application.add_handler(otp_conv)

    # Handler de escape para botones
    btn_escape = MessageHandler(filters.Regex(r'^(Nueva Recepción|Consultar Hoja de Vida|Mis Órdenes Activas|Panel Super Admin)'), handle_general_text)

    # Handler de cancelación universal — texto natural en cualquier estado
    cancel_text = MessageHandler(filters.TEXT & ~filters.COMMAND & filters.Regex(CANCEL_PATTERN), cancel_command)
    
    router_text = MessageHandler(filters.TEXT & (~filters.COMMAND), handle_general_text)
    router_voice = MessageHandler(filters.VOICE, handle_general_voice)

    # Master Conversation: Gestiona TODO el flujo del bot de forma inteligente
    master_conv = ConversationHandler(
        entry_points=[
            router_text,
            router_voice,
            CommandHandler("recepcion", prompt_plate),
            # El botón "Nueva Recepción" es capturado por router_text por regex
        ],
        states={
            ASKING_PLATE: [
                btn_escape, # Los botones siempre interrumpen
                MessageHandler(filters.PHOTO | filters.TEXT | filters.VOICE, process_plate)
            ],
            CONFIRMING_OCR: [
                cancel_text,
                MessageHandler(filters.VOICE, cancel_voice_handler),
                CallbackQueryHandler(handle_ocr_confirmation, pattern="^ocr_")
            ],
            CORRECTING_DATA: [
                btn_escape,
                MessageHandler(filters.TEXT | filters.VOICE, handle_data_correction)
            ],
            CONFIRMING_CLIENT: [
                cancel_text,
                MessageHandler(filters.VOICE, cancel_voice_handler),
                CallbackQueryHandler(handle_client_confirmation, pattern="^client_")
            ],
            ASKING_PHONE: [
                btn_escape,
                MessageHandler(filters.TEXT | filters.VOICE, handle_phone)
            ],
            ASKING_KM: [
                btn_escape,
                MessageHandler(filters.PHOTO | filters.TEXT | filters.VOICE, handle_km_and_photos),
            ],
            ASKING_PHOTOS: [
                btn_escape,
                MessageHandler(filters.PHOTO, handle_photos),
                CallbackQueryHandler(handle_photos_done, pattern="^photos_done"),
            ],
            ASKING_MOTIVE: [
                btn_escape,
                MessageHandler(filters.TEXT | filters.VOICE, handle_motive)
            ],
            CONFIRMING_MOTIVE: [
                cancel_text,
                MessageHandler(filters.VOICE, cancel_voice_handler),
                CallbackQueryHandler(handle_motive_confirmation, pattern="^motive_"),
                CallbackQueryHandler(handle_motive_confirmation, pattern="^change_service_type$"),
            ],
            CONFIRMING_SERVICE_TYPE: [
                cancel_text,
                CallbackQueryHandler(handle_service_type_selection, pattern="^stype_"),
            ],
            CORRECTING_MOTIVE: [
                btn_escape,
                MessageHandler(filters.TEXT | filters.VOICE, handle_motive_correction)
            ],
            L_ASKING_PLATE: [
                btn_escape,
                MessageHandler(filters.TEXT | filters.VOICE, process_lifecycle_plate)
            ],
            SELECTING_TENANT: [
                cancel_text,
                MessageHandler(filters.VOICE, cancel_voice_handler),
                CallbackQueryHandler(handle_tenant_selection, pattern="^sel_tenant_")
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, timeout_handler),
                CallbackQueryHandler(timeout_handler),
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel_command),
            CommandHandler("start", start_command),
            cancel_text,  # texto natural de cancelación en cualquier estado no cubierto
        ],
        allow_reentry=False, # Los estados toman prioridad; usar /cancel para reiniciar
        conversation_timeout=600  # 10 minutos de inactividad
    )
    
    application.add_handler(master_conv)

    # Callbacks General Admin / Tecnico (Fuera de la conversación porque son botones inline persistentes)
    application.add_handler(CallbackQueryHandler(handle_admin_menu, pattern="^admin_"))
    application.add_handler(CallbackQueryHandler(handle_status_change, pattern="^status_(approve|reject)_"))
    from handlers.technician import handle_order_status_change
    application.add_handler(CallbackQueryHandler(handle_order_status_change, pattern="^ord_stat_"))
    application.add_handler(CallbackQueryHandler(handle_status_confirm, pattern="^status_confirm_"))

    logger.info("🤖 Iniciando Master Bot Sonia...")
    application.run_polling()

if __name__ == "__main__":
    main()
