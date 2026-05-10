import base64
import io
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from openai import AsyncOpenAI
from pydantic import BaseModel

from app.api.deps import CurrentUser, get_current_user
from app.config import settings

router = APIRouter(prefix="/mini-app/ai", tags=["mini-app-ai"])

_openai = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


async def _image_to_data_uri(file: UploadFile) -> str:
    content = await file.read()
    b64 = base64.b64encode(content).decode()
    mime = file.content_type or "image/jpeg"
    return f"data:{mime};base64,{b64}"


# ── 1. Transcribir audio ──────────────────────────────────────────────────────

@router.post("/transcribe")
async def transcribe_audio(
    audio: UploadFile = File(...),
    _: CurrentUser = Depends(get_current_user),
):
    content = await audio.read()
    audio_tuple = (audio.filename or "audio.ogg", io.BytesIO(content), audio.content_type or "audio/ogg")
    try:
        transcript = await _openai.audio.transcriptions.create(
            model="whisper-1",
            file=audio_tuple,
            response_format="text",
            temperature=0.2,
        )
        return {"text": transcript}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcripción fallida: {e}")


# ── 2. Extraer datos de Tarjeta de Propiedad / SOAT ──────────────────────────

@router.post("/extract-document")
async def extract_document(
    image: UploadFile = File(...),
    _: CurrentUser = Depends(get_current_user),
):
    data_uri = await _image_to_data_uri(image)
    prompt = (
        "Eres un experto en documentos vehiculares colombianos. "
        "Analiza esta imagen de una Tarjeta de Propiedad o SOAT y extrae TODOS los campos legibles. "
        "Devuelve ÚNICAMENTE JSON con estas claves exactas (null si no es legible):\n"
        '{"placa":null,"vin":null,"numero_motor":null,"propietario":null,'
        '"numero_documento_propietario":null,"marca":null,"linea":null,'
        '"modelo":null,"color":null,"cilindraje":null}\n\n'
        "REGLAS:\n"
        "- placa: 6 caracteres alfanuméricos sin espacios ni guiones.\n"
        "- vin: 17 caracteres si es visible.\n"
        "- numero_documento_propietario: solo dígitos.\n"
        "- modelo: año del modelo (4 dígitos).\n"
        "- NO inventes datos; si no ves claramente, devuelve null."
    )
    try:
        response = await _openai.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_uri, "detail": "high"}},
                ],
            }],
            response_format={"type": "json_object"},
            max_tokens=400,
            temperature=0,
        )
        data = json.loads(response.choices[0].message.content)
        if data.get("placa"):
            data["placa"] = "".join(str(data["placa"]).upper().split())
        if data.get("vin"):
            data["vin"] = "".join(str(data["vin"]).upper().split())
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extracción de documento fallida: {e}")


# ── 3. Extraer KM y gasolina de foto del tablero ─────────────────────────────

@router.post("/extract-odometer")
async def extract_odometer(
    image: UploadFile = File(...),
    _: CurrentUser = Depends(get_current_user),
):
    data_uri = await _image_to_data_uri(image)
    prompt = (
        "Eres Sonia, experta en motocicletas. Analiza esta foto del tablero. "
        "Extrae el kilometraje (solo número) y el nivel de gasolina.\n\n"
        "GASOLINA — clasifica obligatoriamente en uno de: Lleno, Medio, 1/4, Reserva.\n"
        "- F = Full/Lleno, E = Empty/Reserva.\n"
        "- Pocas barras cerca de E → Reserva. Barras a la mitad → Medio. Casi en F → Lleno.\n"
        "- No inventes Lleno si la mayoría de barras están apagadas.\n\n"
        'Responde ÚNICAMENTE con JSON: {"kilometraje": "15000", "gasolina": "Medio"}\n'
        "Si no ves claramente un campo, devuelve string vacío."
    )
    try:
        response = await _openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            }],
            response_format={"type": "json_object"},
            max_tokens=100,
            temperature=0,
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extracción de tablero fallida: {e}")


# ── 4. Clasificar intención (lenguaje natural → intent + placa + estado) ──────

_ROLE_INTENTS: dict[str, list[str]] = {
    "superadmin":  ["START_RECEPTION", "VIEW_LIFECYCLE", "ACTIVE_ORDERS", "CHANGE_STATUS",
                    "PENDING_USERS", "APPROVE_USER", "REJECT_USER", "GREETING", "CANCEL", "UNKNOWN"],
    "jefe_taller": ["START_RECEPTION", "VIEW_LIFECYCLE", "ACTIVE_ORDERS", "CHANGE_STATUS",
                    "GREETING", "CANCEL", "UNKNOWN"],
    "advisor":     ["START_RECEPTION", "VIEW_LIFECYCLE", "ACTIVE_ORDERS", "CHANGE_STATUS",
                    "GREETING", "CANCEL", "UNKNOWN"],
    "technician":  ["START_RECEPTION", "ACTIVE_ORDERS", "CHANGE_STATUS",
                    "GREETING", "CANCEL", "UNKNOWN"],
}

class IntentRequest(BaseModel):
    text: str
    role: str = "technician"


@router.post("/extract-intent")
async def extract_intent(
    body: IntentRequest,
    _: CurrentUser = Depends(get_current_user),
):
    allowed = _ROLE_INTENTS.get(body.role, _ROLE_INTENTS["technician"])
    system_prompt = (
        "Eres el clasificador de intenciones de la Mini App de talleres UM Colombia.\n\n"
        f"Intenciones permitidas para este rol: {', '.join(allowed)}\n\n"
        "CATÁLOGO:\n"
        "- START_RECEPTION: Recepcionar una moto.\n"
        "- VIEW_LIFECYCLE: Ver historial de una moto. Extrae la placa.\n"
        "- ACTIVE_ORDERS: Ver órdenes activas.\n"
        "- CHANGE_STATUS: Cambiar estado de una orden. REQUIERE placa Y estado.\n"
        "- PENDING_USERS: Revisar solicitudes pendientes.\n"
        "- APPROVE_USER: Aprobar usuario. Extrae nombre en target_name.\n"
        "- REJECT_USER: Rechazar usuario. Extrae nombre en target_name.\n"
        "- GREETING: Saludo sin intención operativa.\n"
        "- CANCEL: Cancelar operación.\n"
        "- UNKNOWN: No clasificable.\n\n"
        "ESTADOS VÁLIDOS (solo CHANGE_STATUS): in_progress, on_hold_parts, on_hold_client, external_work, completed\n\n"
        "REGLAS:\n"
        "1. Placa colombiana (ej: NOI82G) → extrae en entities.placa, sin espacios.\n"
        "2. Placa deletreada con espacios → júntala: 'N O I 8 2 G' → 'NOI82G'.\n"
        "3. CHANGE_STATUS sin placa o sin estado → UNKNOWN.\n"
        "4. confidence: 1.0=seguro, 0.5=ambiguo, 0.0=no entiendo.\n\n"
        'Responde ÚNICAMENTE con JSON: {"intent":"...","confidence":0.0,"entities":{"placa":null,"estado":null,"target_name":null}}'
    )
    try:
        response = await _openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": body.text},
            ],
            response_format={"type": "json_object"},
            max_tokens=120,
            temperature=0,
        )
        data = json.loads(response.choices[0].message.content)
        intent = data.get("intent", "UNKNOWN")
        if intent not in allowed:
            intent = "UNKNOWN"
        entities = data.get("entities", {})
        placa = entities.get("placa")
        if placa:
            placa = "".join(str(placa).upper().split())
        return {
            "intent": intent,
            "confidence": float(data.get("confidence", 0.0)),
            "entities": {
                "placa": placa,
                "estado": entities.get("estado"),
                "target_name": entities.get("target_name"),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Clasificación fallida: {e}")


# ── 5. Extraer motivos y tipo de servicio ─────────────────────────────────────

class TextRequest(BaseModel):
    text: str


@router.post("/extract-motive")
async def extract_motive(
    body: TextRequest,
    _: CurrentUser = Depends(get_current_user),
):
    system_prompt = (
        "Eres el asistente de recepción de un taller de motocicletas UM Colombia.\n\n"
        "El usuario describirá los problemas o mantenimientos requeridos para su moto.\n"
        "Tu tarea es:\n"
        "1. Sintetizar su petición en una lista bajo la clave \"motivos\".\n"
        "2. Clasificar el tipo de servicio bajo la clave \"service_type\".\n\n"
        "TIPOS DE SERVICIO (aplica el de MAYOR prioridad si hay varios):\n"
        "- \"warranty\": Fallas cubiertas por garantía de fábrica, defectos de fabricación, "
        "problemas que el cliente atribuye a garantía.\n"
        "- \"km_review\": Mantenimientos periódicos por kilometraje (1000km, 3000km, 6000km, 12000km, etc.), "
        "servicios programados, revisiones de intervalo.\n"
        "- \"regular\": Reparaciones mecánicas, eléctricas, diagnósticos, trabajos que NO son garantía "
        "ni revisión de km ni cambio de partes de desgaste.\n"
        "- \"quick\": Cambios de partes de desgaste: aceite, filtro de aceite, filtro de aire, pastas de freno, "
        "cadena, piñón, corona, guayas, cables de embrague o freno, bujía, bombillos/luces, llantas/neumáticos, "
        "batería, rodamientos de rueda, líquido de frenos, refrigerante, correa de transmisión, empuñaduras, espejos.\n\n"
        "PRIORIDAD: warranty > km_review > regular > quick\n"
        "Si el motivo encaja en varios tipos, elegí el de mayor prioridad.\n\n"
        'Respondé ÚNICAMENTE con JSON válido: {"motivos": ["motivo 1", "motivo 2"], "service_type": "regular"}'
    )
    try:
        response = await _openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": body.text},
            ],
            response_format={"type": "json_object"},
            max_tokens=250,
            temperature=0,
        )
        data = json.loads(response.choices[0].message.content)
        return {
            "motivos": data.get("motivos", [body.text]),
            "service_type": data.get("service_type", "regular"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extracción de motivos fallida: {e}")


# ── 6. Extraer lista de accesorios ────────────────────────────────────────────

@router.post("/extract-accessories")
async def extract_accessories(
    body: TextRequest,
    _: CurrentUser = Depends(get_current_user),
):
    system_prompt = (
        "Eres el asistente de recepción de un taller de motocicletas UM Colombia. "
        "El asesor describe los accesorios que el cliente deja con su moto. "
        "Separa en una lista de ítems, máximo 6 palabras cada uno. "
        "No incluyas la moto misma. Si no hay nada, devuelve lista vacía. "
        'Responde ÚNICAMENTE con JSON: {"items": ["item 1", "item 2"]}'
    )
    try:
        response = await _openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": body.text},
            ],
            response_format={"type": "json_object"},
            max_tokens=200,
            temperature=0,
        )
        data = json.loads(response.choices[0].message.content)
        items = data.get("items", [])
        return {"accessories": [str(i).strip() for i in items if str(i).strip()]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extracción de accesorios fallida: {e}")


# ── 7. Identificar repuesto desde foto ────────────────────────────────────────

@router.post("/identify-part")
async def identify_part(
    image: UploadFile = File(...),
    _: CurrentUser = Depends(get_current_user),
):
    data_uri = await _image_to_data_uri(image)
    prompt = (
        "Eres un experto técnico en repuestos de motocicletas UM Colombia. "
        "Analiza esta imagen e identifica el repuesto o componente mostrado. "
        "Devuelve ÚNICAMENTE JSON con:\n"
        '- "description": descripción en español del repuesto (máximo 10 palabras)\n'
        '- "suggested_sections": lista de 1-3 nombres de secciones del catálogo donde buscar '
        '(ej: ["Motor", "Frenos", "Sistema eléctrico"])\n'
        '- "confidence": certeza de 0.0 a 1.0\n\n'
        "Si la imagen no muestra un repuesto de moto claramente, devuelve confidence 0.0 y listas vacías."
    )
    try:
        response = await _openai.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_uri, "detail": "high"}},
                ],
            }],
            response_format={"type": "json_object"},
            max_tokens=200,
            temperature=0,
        )
        data = json.loads(response.choices[0].message.content)
        return {
            "description": data.get("description", ""),
            "suggested_sections": data.get("suggested_sections", []),
            "confidence": float(data.get("confidence", 0.0)),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Identificación de repuesto fallida: {e}")
