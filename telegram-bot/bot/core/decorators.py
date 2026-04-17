import re
import time
import httpx
from functools import wraps
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from . import config
from .config import BACKEND_URL, logger, USER_CACHE_TTL_SECONDS
from keyboards.reply import get_main_keyboard

def role_required(allowed_roles=None):
    """
    Decorador para proteger los Handlers de Telegram. 
    Verifica si el usuario existe en la DB de empleados y si tiene un rol permitido.
    """
    if allowed_roles is None:
        allowed_roles = ["superadmin", "jefe_taller", "technician"]

    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            telegram_id = update.effective_user.id
            target = update.message if update.message else update.callback_query.message
            
            # 1. Chequeo de Caché Rápido en Contexto Local (con TTL)
            logged_in_user = context.user_data.get("logged_in_user")
            cached_at = context.user_data.get("logged_in_user_cached_at", 0)
            if logged_in_user and (time.time() - cached_at > USER_CACHE_TTL_SECONDS):
                logger.info(f"Caché de usuario expirado para {telegram_id}, re-autenticando...")
                context.user_data.pop("logged_in_user", None)
                context.user_data.pop("logged_in_user_cached_at", None)
                logged_in_user = None

            # 2. Si no hay caché, buscar en Backend (Protección estricta)
            if not logged_in_user:
                logger.info(f"Autorizando usuario {telegram_id} contra el Backend...")
                async with httpx.AsyncClient() as client:
                    try:
                        headers = {"x-sonia-secret": config.SONIA_BOT_SECRET}
                        res = await client.get(f"{BACKEND_URL}/users/telegram/{telegram_id}", headers=headers, timeout=10.0)
                        if res.status_code == 200:
                            user_data = res.json()
                            if user_data.get("status") == "pending":
                                await target.reply_text(
                                    "⏳ Tu solicitud de cuenta aún está **pendiente de aprobación** por parte del Super Administrador UM.\n\n"
                                    "Te avisaremos en cuanto tengas acceso a la plataforma.", parse_mode="Markdown"
                                )
                                return
                                
                            context.user_data["logged_in_user"] = {
                                "id": user_data["id"],
                                "role": user_data["role"],
                                "name": user_data["name"],
                                "tenant_id": user_data["tenant_id"]
                            }
                            context.user_data["logged_in_user_cached_at"] = time.time()
                            logged_in_user = context.user_data["logged_in_user"]
                        else:
                            logger.warning(f"Intento de acceso denegado T-ID: {telegram_id}")
                            kb = InlineKeyboardMarkup([[
                                InlineKeyboardButton("📝 Solicitar acceso", callback_data="start_registration")
                            ]])
                            await target.reply_text(
                                "⛔ *No estás registrado* en la Red UM Colombia.\n\n"
                                "¿Querés enviar una solicitud de acceso al administrador?",
                                parse_mode="Markdown",
                                reply_markup=kb
                            )
                            return
                    except Exception as e:
                        logger.error(f"Error HTTP Auth Guard: {e}")
                        await target.reply_text("⚠️ Sonia tuvo un problema de comunicación con el servidor. Por favor intentá en unos segundos.")
                        return

            # 3. Validación Final de Permisos/Roles
            user_role = logged_in_user.get("role")
            if user_role not in allowed_roles:
                await target.reply_text("🚫 No tienes permisos suficientes para realizar esta acción.", parse_mode="Markdown")
                return

            return await func(update, context, *args, **kwargs)
        return wrapper
    return decorator


CANCEL_PATTERN = re.compile(
    r'(?i)\b(cancelar|cancela|cancelo|cancelalo|anular|anula|abortar|no quiero|detener|salir|ya no|parar|para|quiero parar|olvida|olvidalo|olvidar|dejalo|deja|para ya|basta|terminar|stop)\b'
)

async def check_cancel_intent(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> bool:
    if not text: return False
    pattern = CANCEL_PATTERN
    if pattern.search(text):
        # Preservar sesión del usuario ANTES de limpiar
        logged_in_user = context.user_data.get("logged_in_user")
        logged_in_user_cached_at = context.user_data.get("logged_in_user_cached_at")

        context.user_data.clear()

        # Restaurar sesión
        if logged_in_user:
            context.user_data["logged_in_user"] = logged_in_user
        if logged_in_user_cached_at:
            context.user_data["logged_in_user_cached_at"] = logged_in_user_cached_at

        user_role = logged_in_user.get("role", "none") if logged_in_user else "none"

        await update.message.reply_text(
            "Listo, cancelado. Cuando quieras arrancamos de nuevo.",
            reply_markup=get_main_keyboard(user_role)
        )
        return True
    return False
