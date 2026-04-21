import os
import json
import asyncio
import tempfile
from datetime import datetime, timezone, timedelta
import httpx

BOGOTA = timezone(timedelta(hours=-5))

def fmt_bogota(iso_str: str, fmt: str = "%d/%m/%Y %H:%M") -> str:
    """Convierte un string ISO UTC a hora Colombia (UTC-5)."""
    if not iso_str:
        return "N/D"
    try:
        s = iso_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(BOGOTA).strftime(fmt)
    except Exception:
        return iso_str[:10]
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler

from core.config import logger, BACKEND_URL, FAKE_TENANT, SONIA_BOT_SECRET
from core.constants import (
    PLATE_REGEX,
    ASKING_PLATE, CONFIRMING_OCR, CORRECTING_DATA,
    CONFIRMING_CLIENT, ASKING_PHONE, ASKING_KM,
    ASKING_PHOTOS, ASKING_MOTIVE, CONFIRMING_MOTIVE,
    CORRECTING_MOTIVE, CONFIRMING_KM, SELECTING_TENANT,
    CONFIRMING_SERVICE_TYPE
)
from core.decorators import role_required, check_cancel_intent
from keyboards.reply import get_main_keyboard
from services.ai import (
    extract_data_from_image, 
    extract_data_from_text,
    extract_reception_data,
    extract_reception_data_from_image,
    extract_motive_data,
    transcribe_voice
)

# -------------------------------------------------------------
# Funciones Complementarias de IA para Correcciones Locales
# -------------------------------------------------------------
from services.ai import aclient

async def apply_correction_to_data(original_data: dict, correction_text: str) -> dict:
    """
    Aplica la corrección verbal del asesor sobre los datos actuales del OCR.
    Conoce todos los campos del esquema para poder modificar el correcto.
    """
    schema_desc = (
        "placa (6 chars), vin (VIN/chasis), numero_motor, propietario (nombre completo), "
        "numero_documento_propietario (cédula/NIT solo dígitos), marca, linea (nombre del modelo), "
        "modelo (año, 4 dígitos), color, cilindraje"
    )
    prompt = f"""Eres Sonia, asistente de un taller de motos UM Colombia.
Tienes los siguientes datos leídos de la matrícula del vehículo:
{json.dumps(original_data, ensure_ascii=False, indent=2)}

El asesor quiere corregir algo y dice: "{correction_text}"

Campos disponibles en el esquema: {schema_desc}

INSTRUCCIONES:
1. Identifica qué campo(s) está corrigiendo el asesor.
2. Actualiza SOLO esos campos con el valor corregido.
3. Si la corrección no aplica a ningún campo conocido, devuelve el JSON sin cambios.
4. Normaliza: placa y VIN siempre en MAYÚSCULAS sin espacios. Año solo 4 dígitos.
5. Devuelve ÚNICAMENTE el JSON completo actualizado, sin explicaciones."""
    try:
        response = await aclient.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=300,
        )
        corrected = json.loads(response.choices[0].message.content)
        # Asegurar normalización post-corrección
        if corrected.get("placa"):
            corrected["placa"] = "".join(str(corrected["placa"]).upper().split())
        if corrected.get("vin"):
            corrected["vin"] = "".join(str(corrected["vin"]).upper().split())
        return corrected
    except Exception:
        return original_data


# -------------------------------------------------------------
# Helpers de presentación
# -------------------------------------------------------------
def _build_ocr_summary(ocr: dict) -> str:
    """
    Construye el mensaje de validación que ve el asesor después del OCR.
    Muestra todos los campos leídos de la matrícula para que el asesor confirme o corrija.
    """
    def val(key: str, label: str) -> str:
        v = ocr.get(key)
        return f"• *{label}:* {v}\n" if v else ""

    lines = "📋 *Datos leídos de la matrícula:*\n\n"
    lines += val("placa",                        "Placa")
    lines += val("propietario",                  "Propietario")
    lines += val("numero_documento_propietario", "Documento")
    lines += val("marca",                        "Marca")
    lines += val("linea",                        "Línea / Modelo")
    lines += val("modelo",                       "Año")
    lines += val("color",                        "Color")
    lines += val("cilindraje",                   "Cilindraje")
    lines += val("vin",                          "VIN / Chasis")
    lines += val("numero_motor",                 "N° Motor")

    lines += "\n¿Los datos son correctos?"
    return lines


# -------------------------------------------------------------
# Funciones Internas de Ayuda API
# -------------------------------------------------------------
async def fetch_vehicle_data(plate: str, vin: str = None, tenant_id: str = None) -> dict:
    """
    Búsqueda en cascada:
      1. Busca la moto por placa dentro del taller (vehicles).
      2. Si no la encuentra y tenemos VIN (extraído del OCR), busca en VinMaster global.
      3. Si no hay VIN disponible, retorna None → moto nueva absoluta.
    """
    headers = {"x-sonia-secret": SONIA_BOT_SECRET}
    if tenant_id:
        headers["X-Tenant-ID"] = str(tenant_id)

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Paso 1 — buscar por placa en el taller
        try:
            res = await client.get(f"{BACKEND_URL}/vehicles/{plate}", headers=headers)
            if res.status_code == 200:
                return {"type": "vehicle", "data": res.json()}
            if res.status_code not in (404, 422):
                logger.warning(f"⚠️ [API] Error {res.status_code} buscando placa {plate}: {res.text}")
        except Exception as e:
            logger.error(f"❌ [API] Conexión fallida buscando placa {plate}: {e}")

        # Paso 2 — buscar por VIN en la base maestra global (solo si el OCR lo extrajo)
        if vin and len(vin) >= 10:
            try:
                res_vin = await client.get(f"{BACKEND_URL}/vehicles/vin/{vin}", headers=headers)
                if res_vin.status_code == 200:
                    return {"type": "vin_master", "data": res_vin.json()}
            except Exception as e:
                logger.error(f"❌ [API] Conexión fallida buscando VIN {vin}: {e}")

    return None

async def create_user_and_vehicle(ocr_data: dict, plate: str, tenant_id: str = None, phone: str = None) -> dict:
    """
    Crea el usuario (cliente) y el vehículo en el backend usando los datos del OCR.
    Se llama AL FINAL del flujo de recepción, cuando ya se tiene toda la información.
    Las keys del dict ocr_data deben estar alineadas con el schema del backend:
      placa, vin, propietario, numero_documento_propietario, marca, linea, modelo, color
    """
    if not tenant_id:
        tenant_id = FAKE_TENANT
    headers = {"X-Tenant-ID": tenant_id, "x-sonia-secret": SONIA_BOT_SECRET}

    propietario = ocr_data.get("propietario") or "Desconocido"
    user_payload = {
        "name": propietario,
        "role": "client",
        "tenant_id": tenant_id,
        "phone": phone or ocr_data.get("numero_documento_propietario"),
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        client_id = None
        try:
            res_user = await client.post(f"{BACKEND_URL}/users/", json=user_payload, headers=headers)
            if res_user.status_code == 201:
                client_id = res_user.json().get("id")
        except Exception as e:
            logger.warning(f"⚠️ No se pudo crear el usuario cliente: {e}")

        # Keys alineadas: vin, marca, linea (→ model en el backend), modelo (→ year)
        year = None
        modelo_raw = ocr_data.get("modelo")
        if modelo_raw:
            try:
                year = int(str(modelo_raw).strip()[:4])
            except (ValueError, TypeError):
                pass

        vehicle_payload = {
            "plate": plate,
            "vin": ocr_data.get("vin"),
            "brand": ocr_data.get("marca") or "UM",       # fallback: marca UM si no hay dato
            "model": ocr_data.get("linea") or "N/D",      # fallback: N/D si no hay dato
            "year": year,
            "color": ocr_data.get("color"),
            "tenant_id": tenant_id,
        }
        try:
            res_veh = await client.post(f"{BACKEND_URL}/vehicles/", json=vehicle_payload, headers=headers)
            if res_veh.status_code == 201:
                vh = res_veh.json()
                vh["client_id"] = client_id
                return vh
            logger.warning(f"⚠️ Error creando vehículo ({res_veh.status_code}): {res_veh.text}")
        except Exception as e:
            logger.error(f"❌ Excepción creando vehículo: {e}")

    return None

async def bg_upload_media_to_order(media_files, order_id: str, tenant_id: str):
    """Sube fotos pasivamente al backend."""
    headers = {"X-Tenant-ID": tenant_id}
    async with httpx.AsyncClient(timeout=30.0) as client:
        for file_bytes in media_files:
            try:
                files = {"file": ("reception_photo.jpg", file_bytes, "image/jpeg")}
                await client.post(f"{BACKEND_URL}/media/upload/?order_id={order_id}", files=files, headers=headers)
            except Exception as e:
                logger.error(f"Fallo carga foto a MinIO: {e}")

async def background_create_order(payload: dict, tenant_id: str, media_files: list, bot, chat_id: int, user_role: str, plate: str = ""):
    """Tarea no bloqueante que crea la orden y genera el PDF de Recepción."""
    headers = {
        "X-Tenant-ID": str(tenant_id),
        "x-sonia-secret": SONIA_BOT_SECRET,
    }
    # La placa viene separada del payload (el payload de la orden no tiene 'plate')
    plate_label = plate.upper() if plate else "MOTO"

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # 1. Crear la Orden
            res_order = await client.post(f"{BACKEND_URL}/orders/", json=payload, headers=headers)
            logger.info(f"[ORDEN] POST /orders/ → {res_order.status_code}: {res_order.text[:200]}")

            if res_order.status_code == 201:
                order = res_order.json()
                order_id = order["id"]

                # 2. Subir Fotos asíncronamente a MinIO
                if media_files:
                    await bg_upload_media_to_order(media_files, order_id, tenant_id)

                # 3. El backend ya nos devolvió la URL del PDF al crear la orden
                pdf_url = None
                if "reception" in order and order["reception"]:
                    pdf_url = order["reception"].get("reception_pdf_url")

                if pdf_url:
                    # El bot y el backend están en docker. Reemplazamos localhost por minio para alcance interno
                    internal_pdf_url = pdf_url.replace("localhost", "minio")
                    pdf_bytes = None
                    try:
                        async with httpx.AsyncClient() as c:
                            res_pdf = await c.get(internal_pdf_url, timeout=20.0)
                            if res_pdf.status_code == 200:
                                pdf_bytes = res_pdf.content
                    except Exception as e:
                        logger.error(f"Error descargando PDF internamente: {e}")

                    if pdf_bytes:
                        # Retry con backoff exponencial para tolerar timeouts de Telegram
                        sent = False
                        for attempt in range(3):
                            try:
                                await bot.send_document(
                                    chat_id=chat_id,
                                    document=pdf_bytes,
                                    filename=f"Recepcion_{plate_label}.pdf",
                                    caption=(
                                        f"✅ *¡Recepción Finalizada!*\n\n"
                                        f"🏍️ Placa: *{plate_label}*\n"
                                        f"La orden quedó registrada. Adjunto el acta para firma.\n\n"
                                        f"_Podés ver esta orden en Órdenes Activas._"
                                    ),
                                    parse_mode="Markdown",
                                    reply_markup=get_main_keyboard(user_role),
                                    read_timeout=60,
                                    write_timeout=60,
                                    connect_timeout=20,
                                )
                                sent = True
                                break
                            except Exception as te:
                                wait = 2 ** attempt
                                logger.warning(f"[PDF] Intento {attempt+1} fallido al enviar PDF: {te}. Reintentando en {wait}s...")
                                await asyncio.sleep(wait)
                        if not sent:
                            # El PDF fue generado pero Telegram no pudo recibirlo — informar sin bloquear
                            await bot.send_message(
                                chat_id=chat_id,
                                text=(
                                    f"✅ *Orden de {plate_label} creada correctamente.*\n\n"
                                    f"⚠️ No pude enviar el PDF por un problema de conexión con Telegram, "
                                    f"pero la orden quedó registrada en el sistema. Podés descargarlo desde el panel web."
                                ),
                                parse_mode="Markdown",
                                reply_markup=get_main_keyboard(user_role),
                            )
                        return

                await bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️ Orden *{plate_label}* creada, pero hubo un error generando el PDF. Ya quedó registrada en el sistema.",
                    parse_mode="Markdown",
                    reply_markup=get_main_keyboard(user_role)
                )
            else:
                logger.error(f"[ORDEN] Error {res_order.status_code}: {res_order.text}")
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ Error al crear la orden ({res_order.status_code}): {res_order.text[:200]}",
                    reply_markup=get_main_keyboard(user_role)
                )
        except Exception as e:
            logger.error(f"[ORDEN] Excepción en background_create_order: {e}", exc_info=True)
            await bot.send_message(
                chat_id=chat_id,
                text="❌ Ocurrió un error de conexión al crear la orden. Intentá de nuevo.",
                reply_markup=get_main_keyboard(user_role)
            )


# -------------------------------------------------------------
# Handlers del Conversation (Máquina de Estados)
# -------------------------------------------------------------
@role_required()
async def prompt_plate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logged_in = context.user_data.get("logged_in_user", {})
    user_role = logged_in.get("role", "")

    # Superadmin sin taller activo → mostrar selector antes de continuar
    if user_role == "superadmin" and not context.user_data.get("active_tenant_id"):
        context.user_data['pending_action'] = "reception"
        from handlers.admin import _show_tenant_selector
        return await _show_tenant_selector(update.message, context)

    # Preservar sesión y limpiar solo datos de recepción anterior
    logged_in_user        = context.user_data.get("logged_in_user")
    logged_in_cached_at   = context.user_data.get("logged_in_user_cached_at")
    active_tenant_id      = context.user_data.get("active_tenant_id")
    active_tenant_name    = context.user_data.get("active_tenant_name")
    context.user_data.clear()
    if logged_in_user:       context.user_data["logged_in_user"]           = logged_in_user
    if logged_in_cached_at:  context.user_data["logged_in_user_cached_at"] = logged_in_cached_at
    if active_tenant_id:     context.user_data["active_tenant_id"]         = active_tenant_id
    if active_tenant_name:   context.user_data["active_tenant_name"]       = active_tenant_name

    taller_txt = f" en *{active_tenant_name}*" if active_tenant_name else ""
    await update.message.reply_text(
        f"Excelente{taller_txt}. Pasame la placa o una foto de la matrícula para arrancar.",
        parse_mode="Markdown"
    )
    return ASKING_PLATE

@role_required()
async def handle_data_correction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = ""
    if update.message.voice:
        await update.message.reply_text("Escuchando tu corrección... 🎧")
        voice_file = await update.message.voice.get_file()
        fd, path = tempfile.mkstemp(suffix=".ogg")
        os.close(fd)
        await voice_file.download_to_drive(path)
        transcript = await transcribe_voice(path)
        os.remove(path)
        text = transcript or ""
    elif update.message.text:
        text = update.message.text
        
    if await check_cancel_intent(update, context, text): return ConversationHandler.END
    
    if not text:
        await update.message.reply_text("¿Qué deseas corregir?")
        return CORRECTING_DATA
        
    ocr_data = context.user_data.get('ocr_data', {})
    new_data = await apply_correction_to_data(ocr_data, text)

    context.user_data['ocr_data'] = new_data
    if new_data.get("placa"):
        context.user_data['ocr_plate'] = new_data["placa"].upper().strip()

    btn = [[
        InlineKeyboardButton("✅ Sí, continuar", callback_data="ocr_yes"),
        InlineKeyboardButton("✏️ Corregir otro campo", callback_data="ocr_no")
    ]]
    await update.message.reply_text(
        "¡Listo, actualicé los datos! Revisalos:\n\n" + _build_ocr_summary(new_data),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(btn)
    )
    return CONFIRMING_OCR

@role_required()
async def process_plate(update: Update, context: ContextTypes.DEFAULT_TYPE, direct_plate: str = None) -> int:
    # 1. Si no viene parametrizada explícitamente, intentamos sacarla del texto
    if not direct_plate and update.message.text:
        text = update.message.text.upper()
        if await check_cancel_intent(update, context, text): return ConversationHandler.END
        
        plate_match = PLATE_REGEX.search(text)
        if plate_match:
            direct_plate = plate_match.group(0)
        else:
            extracted = await extract_data_from_text(text)
            if extracted and extracted.get("placa"):
                direct_plate = extracted.get("placa")

    # 2. Manejo de Nota de Voz en el estado ASKING_PLATE
    if not direct_plate and getattr(update.message, "voice", None):
        await update.message.reply_text("Escuchando tu nota de voz para extraer la placa... 🎧")
        voice_file = await update.message.voice.get_file()
        fd, path = tempfile.mkstemp(suffix=".ogg")
        os.close(fd)
        await voice_file.download_to_drive(path)
        transcript = await transcribe_voice(path, prompt="La placa es Noi 82G.")
        os.remove(path)
        
        if transcript:
            if await check_cancel_intent(update, context, transcript): return ConversationHandler.END
            plate_match = PLATE_REGEX.search(transcript.upper())
            if plate_match:
                direct_plate = plate_match.group(0)
            else:
                extracted = await extract_data_from_text(transcript)
                if extracted and extracted.get("placa"):
                    direct_plate = extracted.get("placa")
            
            if not direct_plate:
                await update.message.reply_text(f"Te entendí: '{transcript}', pero no encontré la placa. ¿Me la escribes?")
                return ASKING_PLATE
        else:
            await update.message.reply_text("Uy, tuve un problema escuchando la nota de voz. ¿Me escribes la placa?")
            return ASKING_PLATE

    # 3. Soporta Flujo Mixto (Foto de Placa / Texto Directo)
    if direct_plate:
        # Texto Directo / Voz Extraída
        plate = direct_plate.upper().strip()
        if context.user_data.get('pending_intent') == 'lifecycle':
            # Mandó la placa para buscar Historial (Lifecycle)
            await update.message.reply_text(f"🔍 Buscando la hoja de vida de la moto *{plate}*...", parse_mode="Markdown")
            await send_vehicle_lifecycle(update, context, plate)
            context.user_data.pop('pending_intent', None)
            return ConversationHandler.END
        
        # Envoltorio Fake para Receptar Text
        context.user_data['ocr_data'] = {"placa": plate}
        context.user_data['ocr_plate'] = plate
        
        keyboard = [
            [InlineKeyboardButton("Sí, continuar", callback_data="ocr_yes"), InlineKeyboardButton("No, corregir", callback_data="ocr_no")]
        ]
        await update.message.reply_text(f"Ok, registramos la placa *{plate}*. ¿Continuamos con esta moto?", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        return CONFIRMING_OCR

    elif update.message.photo:
        await update.message.reply_text("Revisando la matrícula... dame un segundo 🔍")
        photo_file = await update.message.photo[-1].get_file()
        extracted = await extract_data_from_image(photo_file.file_path)

        plate = extracted.get("placa")
        if not plate:
            await update.message.reply_text(
                "Hmm, no logré leer la placa en esa foto. 🤔\n"
                "Intentá con mejor iluminación o escribime la placa directamente."
            )
            return ASKING_PLATE

        context.user_data['ocr_data'] = extracted
        context.user_data['ocr_plate'] = plate.upper()

        btn = [[
            InlineKeyboardButton("✅ Sí, continuar", callback_data="ocr_yes"),
            InlineKeyboardButton("✏️ Corregir", callback_data="ocr_no")
        ]]
        await update.message.reply_text(
            _build_ocr_summary(extracted),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(btn)
        )
        return CONFIRMING_OCR
    else:
        await update.message.reply_text("Por favor envíame la placa o una foto legible del SOAT.")
        return ASKING_PLATE

@role_required()
async def handle_ocr_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    if query.data == "ocr_yes":
        ocr_data = context.user_data.get('ocr_data', {})
        plate    = context.user_data.get('ocr_plate')
        vin      = ocr_data.get('vin')   # VIN extraído por el OCR (puede ser None)

        await query.edit_message_text(
            f"Perfecto, placa *{plate}* confirmada. Buscando en el sistema... 🔍",
            parse_mode="Markdown"
        )

        logged_in = context.user_data.get("logged_in_user", {})
        tenant_id_real = logged_in.get("tenant_id")
        # Superadmin no tiene tenant propio → usar el taller activo elegido en sesión
        if not tenant_id_real and logged_in.get("role") == "superadmin":
            tenant_id_real = context.user_data.get("active_tenant_id") or FAKE_TENANT

        # Búsqueda en cascada: placa en taller → VIN en maestro global
        veh_data = await fetch_vehicle_data(plate, vin=vin, tenant_id=tenant_id_real)

        if veh_data:
            v_type = veh_data["type"]
            v_info = veh_data["data"]

            if v_type == "vehicle":
                # Moto conocida en este taller
                context.user_data['vehicle_id'] = v_info.get("id")
                marca  = v_info.get('brand') or ocr_data.get('marca') or 'UM'
                modelo = v_info.get('model') or ocr_data.get('linea') or ''
                txt = (
                    f"¡Esta moto ya ha estado en el taller! 🏍️\n"
                    f"*{marca} {modelo}*\n\n"
                    f"¿Procedemos con la recepción?"
                )
                kb = [[InlineKeyboardButton("Sí, ingresar a Taller", callback_data="client_yes")]]
                await query.message.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
                return CONFIRMING_CLIENT

            else:  # vin_master — primera vez en este taller pero es moto UM registrada
                context.user_data['vehicle_id'] = None  # Se creará al confirmar la orden
                # Enriquecer ocr_data con los datos del maestro (el OCR puede tener menos info)
                v_marca  = v_info.get('brand') or v_info.get('model_name', 'UM')
                v_linea  = v_info.get('model') or v_info.get('model_name', '')
                v_anio   = v_info.get('year')
                v_color  = v_info.get('color')
                # Solo completar lo que el OCR no haya leído
                if not ocr_data.get('marca')  and v_marca:  ocr_data['marca']  = v_marca
                if not ocr_data.get('linea')  and v_linea:  ocr_data['linea']  = v_linea
                if not ocr_data.get('modelo') and v_anio:   ocr_data['modelo'] = str(v_anio)
                if not ocr_data.get('color')  and v_color:  ocr_data['color']  = v_color
                context.user_data['ocr_data'] = ocr_data

                txt = (
                    f"Esta moto es de la red UM pero es la primera vez que viene a *este* taller. 🆕\n"
                    f"*{v_marca} {v_linea}* ({v_anio or 'año N/D'})\n\n"
                    f"¿Me das el *teléfono del cliente* para completar el registro?"
                )
                await query.message.reply_text(txt, parse_mode="Markdown")
                return ASKING_PHONE

        else:
            # Moto nueva absoluta — no está en taller ni en VinMaster de UM
            # No creamos nada todavía — esperamos tener toda la info antes de persistir
            context.user_data['vehicle_id'] = None  # Se creará al confirmar la orden
            await query.message.reply_text(
                f"Esta moto (*{plate}*) es nueva en el sistema. La registramos desde cero.\n\n"
                f"¿Me das el *teléfono del cliente* para continuar?",
                parse_mode="Markdown"
            )
            return ASKING_PHONE

    elif query.data == "ocr_no":
        await query.edit_message_text(
            "Dale, decime qué está mal — podés escribirlo o mandarme un audio. "
            "Por ejemplo: *'la placa es NOI82G'* o *'el propietario se llama Carlos'*.",
            parse_mode="Markdown"
        )
        return CORRECTING_DATA
        
@role_required()
async def handle_client_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    if query.data == "client_yes":
        await query.edit_message_text(
            "Perfecto, vamos con la recepción.\n\n"
            "Primero, *¿cuántos kilómetros tiene la moto?* Escribilo, mandame audio o una foto del tablero."
        )
        context.user_data['media_files'] = []
        return ASKING_KM

@role_required()
async def handle_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = ""
    if update.message.voice:
        await update.message.reply_text("Escuchando el teléfono... 🎧")
        voice_file = await update.message.voice.get_file()
        fd, path = tempfile.mkstemp(suffix=".ogg")
        os.close(fd)
        await voice_file.download_to_drive(path)
        transcript = await transcribe_voice(path, prompt="Mi número es 3101234567")
        os.remove(path)
        text = transcript or ""
    elif update.message.text:
        text = update.message.text

    if await check_cancel_intent(update, context, text): return ConversationHandler.END
    
    # Limpiar solo números
    phone = "".join(filter(str.isdigit, text))
    if len(phone) < 7:
        await update.message.reply_text("No logré identificar un número de teléfono válido. ¿Me lo escribes o repites?")
        return ASKING_PHONE

    context.user_data['client_phone'] = phone
    await update.message.reply_text(
        f"Teléfono *{phone}* registrado. ✅\n\n"
        "Ahora, *¿cuántos kilómetros tiene la moto?* También podés decirme el nivel de gasolina. "
        "Escribilo, mandame un audio o una foto del tablero.",
        parse_mode="Markdown"
    )
    context.user_data['media_files'] = []
    return ASKING_KM

@role_required()
async def handle_km_and_photos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Paso 1: Solo captura KM y nivel de gasolina. Las fotos de evidencia van en el paso siguiente."""
    if update.message.photo:
        await update.message.reply_text("Revisando el tablero... 🔍")
        photo_file = await update.message.photo[-1].get_file()
        extracted = await extract_reception_data_from_image(photo_file.file_path)
        if extracted.get("kilometraje"): context.user_data['km'] = extracted["kilometraje"]
        if extracted.get("gasolina"): context.user_data['gas_level'] = extracted["gasolina"]

    elif update.message.voice:
        await update.message.reply_text("Escuchando... 🎧")
        voice_file = await update.message.voice.get_file()
        fd, path = tempfile.mkstemp(suffix=".ogg")
        os.close(fd)
        await voice_file.download_to_drive(path)
        transcript = await transcribe_voice(path, prompt="Tiene 5000 km y está medio de gasolina.")
        os.remove(path)
        if transcript:
            extracted = await extract_reception_data(transcript)
            if extracted.get("kilometraje"): context.user_data['km'] = extracted["kilometraje"]
            if extracted.get("gasolina"): context.user_data['gas_level'] = extracted["gasolina"]

    elif update.message.text:
        txt = update.message.text
        if await check_cancel_intent(update, context, txt): return ConversationHandler.END
        extracted = await extract_reception_data(txt)
        if extracted.get("kilometraje"): context.user_data['km'] = extracted["kilometraje"]
        if extracted.get("gasolina"): context.user_data['gas_level'] = extracted["gasolina"]

    km = context.user_data.get('km', 'No registrado')
    gas = context.user_data.get('gas_level', 'No registrado')
    context.user_data.setdefault('media_files', [])

    kb = [[InlineKeyboardButton("✅ Continuar sin fotos", callback_data="photos_done")]]
    await update.message.reply_text(
        f"*KM:* {km}  |  *Gasolina:* {gas} ✅\n\n"
        "Ahora mandame las *fotos de evidencia* del estado actual de la moto: "
        "golpes, rayones, detalles importantes.\n\n"
        "Cuando termines (o si no hay nada que registrar), presioná *Continuar*.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )
    return ASKING_PHOTOS


@role_required()
async def handle_photos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Paso 2: Recibe fotos de evidencia del estado del vehículo al ingreso."""
    photo_file = await update.message.photo[-1].get_file()
    file_bytes = await photo_file.download_as_bytearray()
    context.user_data.setdefault('media_files', []).append(file_bytes)
    count = len(context.user_data['media_files'])

    kb = [[InlineKeyboardButton("✅ Continuar", callback_data="photos_done")]]
    await update.message.reply_text(
        f"Foto {count} guardada ✅\n\nMandame más si querés, o presioná *Continuar* cuando estés listo.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )
    return ASKING_PHOTOS


@role_required()
async def handle_photos_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cierra el paso de fotos y pasa al motivo de ingreso."""
    query = update.callback_query
    await query.answer()
    count = len(context.user_data.get('media_files', []))
    fotos_txt = f"{count} foto(s) de evidencia guardadas." if count > 0 else "Sin fotos de evidencia."
    await query.edit_message_text(
        f"{fotos_txt}\n\nAhora describime el *motivo de ingreso*: ¿qué le pasa a la moto o qué necesita? "
        "Podés escribirlo o mandarme un audio.",
        parse_mode="Markdown"
    )
    return ASKING_MOTIVE

@role_required()
async def handle_motive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = ""
    if update.message.voice:
        voice_file = await update.message.voice.get_file()
        fd, path = tempfile.mkstemp(suffix=".ogg")
        os.close(fd)
        await voice_file.download_to_drive(path)
        transcript = await transcribe_voice(path, prompt="Motivo: Cliente expone ruidos en el motor, cambio aceite.")
        os.remove(path)
        text = transcript or ""
    elif update.message.text:
        text = update.message.text
        
    if await check_cancel_intent(update, context, text): return ConversationHandler.END
    
    if not text:
        await update.message.reply_text("Por favor descríbeme el motivo.")
        return ASKING_MOTIVE

    await update.message.reply_text("Dejame organizar eso...")
    result = await extract_motive_data(text)
    motivos = result["motivos"]
    service_type = result["service_type"]
    context.user_data['motives'] = motivos
    context.user_data['service_type'] = service_type

    SERVICE_TYPE_LABELS = {
        "warranty":  "🔴 Garantía",
        "km_review": "🟢 Revisión de kilometraje",
        "regular":   "🔵 Mecánica general",
        "quick":     "🟣 Mecánica rápida",
    }
    type_label = SERVICE_TYPE_LABELS.get(service_type, "🔵 Mecánica general")

    msg = "*Motivos Identificados:*\n"
    for m in motivos:
        msg += f"• {m}\n"
    msg += f"\n*Tipo de servicio detectado:* {type_label}\n\n¿Está correcto?"

    kb = [
        [InlineKeyboardButton("✅ Sí, crear Orden", callback_data="motive_yes"),
         InlineKeyboardButton("✏️ Cambiar tipo", callback_data="change_service_type")],
        [InlineKeyboardButton("❌ Corregir motivo", callback_data="motive_no")],
    ]
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    return CONFIRMING_MOTIVE

@role_required()
async def handle_motive_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "motive_yes":
        await query.edit_message_text("📝 *Procesando recepción...* Dame un segundo.", parse_mode="Markdown")

        # --- Recuperar todos los datos recolectados en el flujo ---
        plate        = context.user_data.get('ocr_plate', '')
        ocr_data     = context.user_data.get('ocr_data', {})
        km           = context.user_data.get('km', 0)
        gas          = context.user_data.get('gas_level', 'No Registrado')
        motives      = context.user_data.get('motives', [])
        vid          = context.user_data.get('vehicle_id')
        media_files  = context.user_data.get('media_files', [])
        client_phone = context.user_data.get('client_phone')
        tech_id      = context.user_data.get("logged_in_user", {}).get("id")

        try: km = int("".join(filter(str.isdigit, str(km))))
        except: km = 0

        motive_text = "\n".join([f"- {m}" for m in motives])

        logged_in_user = context.user_data.get("logged_in_user", {})
        tenant_id = logged_in_user.get("tenant_id")
        user_role = logged_in_user.get("role", "none")

        # Superadmin no tiene tenant propio — usa el taller activo elegido en sesión
        if not tenant_id:
            if user_role == "superadmin":
                tenant_id = context.user_data.get("active_tenant_id") or FAKE_TENANT
            else:
                await query.message.reply_text(
                    "No pude identificar tu taller. Verificá tu sesión con /start."
                )
                return ConversationHandler.END

        # ─────────────────────────────────────────────────────────────
        # VALIDACIÓN DE INTEGRIDAD — Ningún dato se persiste si falta
        # información obligatoria. La regla es simple y no tiene excepciones.
        # ─────────────────────────────────────────────────────────────
        datos_faltantes = []
        if not plate:
            datos_faltantes.append("placa de la moto")
        if km == 0:
            datos_faltantes.append("kilometraje")
        if not motives:
            datos_faltantes.append("motivo de ingreso")
        # Para motos nuevas (vid es None) el teléfono del cliente es obligatorio
        if not vid and not client_phone:
            datos_faltantes.append("teléfono del cliente")

        if datos_faltantes:
            faltantes_txt = "\n".join([f"• {d}" for d in datos_faltantes])
            logger.warning(f"[RECEPCIÓN] Abortado — datos incompletos para {plate}: {datos_faltantes}")
            await query.message.reply_text(
                f"⛔ *Recepción abortada.*\n\n"
                f"Faltan los siguientes datos obligatorios:\n{faltantes_txt}\n\n"
                f"Iniciá el proceso nuevamente con /start para cargar la moto correctamente.",
                parse_mode="Markdown"
            )
            return ConversationHandler.END
        # ─────────────────────────────────────────────────────────────

        # --- PASO 1: Crear vehículo/cliente si es moto nueva (se hace acá con todos los datos) ---
        if not vid:
            logger.info(f"[RECEPCIÓN] Moto nueva {plate} — creando usuario y vehículo con teléfono {client_phone}")
            new_veh = await create_user_and_vehicle(
                ocr_data, plate, tenant_id=tenant_id, phone=client_phone
            )
            if new_veh:
                vid = new_veh["id"]
                context.user_data['vehicle_id'] = vid
            else:
                await query.message.reply_text(
                    "⚠️ No pude registrar el vehículo en el sistema. "
                    "Verificá que el taller esté correctamente configurado e intentá de nuevo."
                )
                return ConversationHandler.END

        # --- PASO 2: Construir payload de la Orden ---
        payload = {
            "tenant_id": tenant_id,
            "vehicle_id": vid,
            "client_id": context.user_data.get("client_id"),
            "client_phone": client_phone,
            "technician_id": tech_id,
            "service_type": context.user_data.get("service_type", "regular"),
            "reception": {
                "mileage_km": km,
                "gas_level": gas,
                "customer_notes": motive_text,
                "damage_photos_urls": [],
            }
        }
        bot = context.bot
        chat_id = query.message.chat_id

        # Limpiar contexto temporal antes de lanzar la tarea background
        context.user_data.pop('ocr_data', None)
        context.user_data.pop('ocr_plate', None)
        context.user_data.pop('media_files', None)

        # --- PASO 3: Crear orden y PDF en background (no bloquea al usuario) ---
        context.application.create_task(
            background_create_order(payload, tenant_id, media_files, bot, chat_id, user_role, plate=plate)
        )
        return ConversationHandler.END
        
    elif query.data == "change_service_type":
        kb = [
            [InlineKeyboardButton("🔴 Garantía",              callback_data="stype_warranty")],
            [InlineKeyboardButton("🟢 Revisión de kilometraje", callback_data="stype_km_review")],
            [InlineKeyboardButton("🔵 Mecánica general",       callback_data="stype_regular")],
            [InlineKeyboardButton("🟣 Mecánica rápida",        callback_data="stype_quick")],
        ]
        await query.edit_message_text(
            "Seleccioná el tipo de servicio correcto:",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return CONFIRMING_SERVICE_TYPE

    elif query.data == "motive_no":
        await query.edit_message_text("Ok, por favor escríbeme el motivo correcto para reemplazarlo.")
        return CORRECTING_MOTIVE

@role_required()
async def handle_motive_correction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await handle_motive(update, context)


STYPE_MAP = {
    "stype_warranty":  ("warranty",  "🔴 Garantía"),
    "stype_km_review": ("km_review", "🟢 Revisión de kilometraje"),
    "stype_regular":   ("regular",   "🔵 Mecánica general"),
    "stype_quick":     ("quick",     "🟣 Mecánica rápida"),
}

@role_required()
async def handle_service_type_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    stype, label = STYPE_MAP.get(query.data, ("regular", "🔵 Mecánica general"))
    context.user_data['service_type'] = stype

    motivos = context.user_data.get('motives', [])
    msg = "*Motivos Identificados:*\n"
    for m in motivos:
        msg += f"• {m}\n"
    msg += f"\n*Tipo de servicio:* {label}\n\n¿Confirmamos y creamos la Orden?"

    kb = [
        [InlineKeyboardButton("✅ Sí, crear Orden", callback_data="motive_yes"),
         InlineKeyboardButton("❌ Corregir motivo", callback_data="motive_no")],
    ]
    await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    return CONFIRMING_MOTIVE


# -------------------------------------------------------------
# Funciones Extra / Legacy Lifecycle 
# -------------------------------------------------------------
async def send_vehicle_lifecycle(update: Update, context: ContextTypes.DEFAULT_TYPE, plate: str) -> None:
    """Envía la bitácora historica de la motocileta enriquecida."""
    user_data = context.user_data.get("logged_in_user", {})
    user_role = user_data.get("role", "")
    full_name = user_data.get("name", "Usuario Desconocido")
    
    logger.info(f"🔍 [LIFECYCLE] Consultando placa '{plate}' para usuario: {full_name} (Rol: {user_role})")
    
    # Si es admin o superadmin, consultamos GLOBAL (sin tenant_id)
    if user_role in ["jefe_taller", "superadmin"]:
        v_data = await fetch_vehicle_data(plate, tenant_id=None)
    else:
        tenant_id = user_data.get("tenant_id", FAKE_TENANT)
        v_data = await fetch_vehicle_data(plate, tenant_id)
    if not v_data:
        await update.message.reply_text(f"No encontré hoja de vida para la moto con placa *{plate}* en tu taller, ni en la base maestra de UM.", parse_mode="Markdown")
        return
        
    info = v_data["data"]
    
    # Construcción de Reporte Premium
    if v_data["type"] == "vin_master":
        txt = f"📖 *EXPEDIENTE TÉCNICO DE FÁBRICA (UM)*\n\n"
        txt += f"🏍️ *Referencia:* {info.get('brand','UM')} {info.get('model_name')}\n"
        txt += f"🔢 *VIN:* `{info.get('vin')}`\n"
        txt += f"⚙️ *Motor:* `{info.get('engine_number','N/D')}`\n"
        txt += f"📅 *Modelo:* {info.get('year')}\n"
        txt += f"🎨 *Color:* {info.get('color','N/D')}\n\n"
        
        txt += "🛡️ *COBERTURA DE GARANTÍA:*\n"
        txt += f"• Motor: {info.get('garantia_motor_km',0):,} km / {info.get('garantia_motor_meses',0)} meses\n"
        txt += f"• General: {info.get('garantia_general_km',0):,} km / {info.get('garantia_general_meses',0)} meses\n\n"
        
        txt += "⚠️ *Nota:* Este vehículo es nuevo en la red y no tiene ingresos registrados en taller todavía."
    else:
        # Vehículo de Taller (Enriquecido por Backend)
        warranty = info.get('warranty_info', {})
        txt = f"📖 *HOJA DE VIDA DE SERVICIO - {info.get('plate')}*\n\n"
        txt += f"🏍️ *Moto:* {info.get('brand')} {info.get('model')}\n"
        txt += f"🔢 *VIN:* `{info.get('vin')}`\n"
        txt += f"📅 *Modelo:* {info.get('year')}\n"
        txt += f"🎨 *Color:* {info.get('color','N/D')}\n\n"

        # Estado actual en taller
        active = info.get('active_order')
        if active:
            STATUS_LABELS = {
                "received": "Recibida",
                "scheduled": "Agendada",
                "in_progress": "En proceso",
                "on_hold_parts": "Esperando repuestos",
                "on_hold_client": "Esperando cliente",
                "external_work": "Trabajo externo",
                "rescheduled": "Reagendada",
                "completed": "Finalizada",
                "delivered": "Entregada",
            }
            status_label = STATUS_LABELS.get(active.get('status', ''), active.get('status', 'N/D').upper())
            taller = active.get('tenant_name', 'N/D')
            ciudad = active.get('tenant_city', '')
            taller_str = f"{taller} — {ciudad}" if ciudad else taller
            ingreso_str = fmt_bogota(active.get('created_at') or '', "%d/%m/%Y %H:%M")
            txt += f"🔴 *ACTUALMENTE EN TALLER*\n"
            txt += f"📍 *Centro:* {taller_str}\n"
            txt += f"⚙️ *Estado:* {status_label}\n"
            txt += f"📆 *Ingreso:* {ingreso_str}\n\n"

        if warranty:
            txt += "🛡️ *GARANTÍA:* Activa según parámetros UM.\n\n"

        txt += "📑 *RESUMEN DE HISTORIAL:*\n"
        orders = info.get('service_orders_summary', [])
        if orders:
            for i, order in enumerate(orders, 1):
                date_str = fmt_bogota(order.get('created_at') or '', "%d/%m/%Y")
                km_str = f" | {order['mileage_km']:,} km" if order.get('mileage_km') else ""
                txt += f"{i}. *{date_str}* - {order.get('status','?').upper()}{km_str}\n"
        else:
            txt += "• No se registran órdenes aún.\n"

        latest_km = info.get('latest_mileage')
        km_display = f"{latest_km:,}" if latest_km else "No registrado"
        txt += f"\n📊 *KM al último ingreso:* {km_display} KM"

    await update.message.reply_text(txt, parse_mode="Markdown")
