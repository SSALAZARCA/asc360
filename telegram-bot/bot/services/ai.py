"""
GUÍA DE VOZ DE SONIA
====================
Quién es Sonia: asesora de servicio experta y amigable. Colombiana, directa, cálida.
Habla como una colega, no como un chatbot.

REGLAS:
- Nunca dice "procesando", "extrayendo", "clasificando", "estructurando"
- Nunca dice "Sonia al habla:" ni se refiere a sí misma en tercera persona
- Sin tecnicismos al usuario: nada de UUIDs, estados en inglés, errores técnicos
- Confirmación antes de actuar: "Te escuché, voy con la recepción de la NOI82G..."
- Máximo 2-3 líneas por mensaje en interacciones normales

BIEN: "Dale, ya busco el historial de la ABC123..."
MAL:  "Extrayendo y estructurando motivos... ⚙️"
"""

import os
import json
import asyncio
import base64
import tempfile
from openai import AsyncOpenAI
from core.config import logger, OPENAI_MAX_RETRIES

aclient = AsyncOpenAI()


class AIServiceError(Exception):
    """Excepción lanzada cuando OpenAI agota los reintentos disponibles."""
    pass


async def _call_openai_with_retry(coro_factory, max_retries: int = None):
    """
    Wrapper con backoff exponencial para llamadas a OpenAI.

    Args:
        coro_factory: Callable sin argumentos que retorna una coroutine.
                      Debe ser un lambda que CREA la coroutine cada vez.
        max_retries: Número de reintentos (default: OPENAI_MAX_RETRIES de config).

    Raises:
        AIServiceError: Si se agotan todos los reintentos.
    """
    if max_retries is None:
        max_retries = OPENAI_MAX_RETRIES

    last_exception = None
    for attempt in range(max_retries + 1):
        try:
            return await coro_factory()
        except Exception as e:
            last_exception = e
            if attempt < max_retries:
                wait_seconds = 2 ** attempt  # 1s, 2s, 4s...
                logger.warning(f"OpenAI reintento {attempt + 1}/{max_retries + 1}: {type(e).__name__}. Esperando {wait_seconds}s...")
                await asyncio.sleep(wait_seconds)
            else:
                logger.error(f"OpenAI agotó {max_retries + 1} intentos: {e}")
                raise AIServiceError(f"OpenAI no disponible tras {max_retries + 1} intentos") from e


# Intenciones disponibles por rol
ROLE_INTENTS = {
    "superadmin": [
        "START_RECEPTION", "VIEW_LIFECYCLE", "ACTIVE_ORDERS", "CHANGE_STATUS",
        "PENDING_USERS", "APPROVE_USER", "REJECT_USER", "LOAD_TENANTS", "OPEN_PANEL",
        "GREETING", "CANCEL", "UNKNOWN"
    ],
    "jefe_taller": [
        "START_RECEPTION", "VIEW_LIFECYCLE", "ACTIVE_ORDERS", "CHANGE_STATUS",
        "GREETING", "CANCEL", "UNKNOWN"
    ],
    "technician": [
        "START_RECEPTION", "ACTIVE_ORDERS", "CHANGE_STATUS",
        "GREETING", "CANCEL", "UNKNOWN"
    ],
}

UNIFIED_INTENT_SYSTEM_PROMPT = """Eres el clasificador de intenciones del bot Sonia para talleres de motocicletas UM Colombia.

Analiza el mensaje del usuario y clasifica su intención en UNA de las siguientes categorías.
Solo puedes elegir intenciones PERMITIDAS para el rol actual: {allowed_intents_block}

CATÁLOGO DE INTENCIONES:
- START_RECEPTION: Quiere ingresar/recepcionar una moto al taller. Ej: "recibir moto", "nueva recepción", "llegó la moto de placa XYZ".
- VIEW_LIFECYCLE: Quiere consultar la hoja de vida o historial de una moto. Extrae la placa si la menciona.
- ACTIVE_ORDERS: Quiere ver sus órdenes activas, pendientes o motos asignadas.
- CHANGE_STATUS: Quiere cambiar el estado de una orden. REQUIERE placa y estado. Ej: "la NOI82G ya está lista".
- PENDING_USERS: Quiere revisar solicitudes de ingreso pendientes.
- APPROVE_USER: Quiere aprobar a alguien. Extrae el nombre en target_name.
- REJECT_USER: Quiere rechazar a alguien. Extrae el nombre en target_name.
- LOAD_TENANTS: Quiere cargar Excel de centros de servicio.
- OPEN_PANEL: Quiere ver el panel o menú de administración.
- GREETING: Saludo sin intención operativa. Ej: "hola", "buenas".
- CANCEL: Quiere cancelar la operación actual.
- UNKNOWN: No se puede clasificar con certeza.

ESTADOS VÁLIDOS (solo para CHANGE_STATUS):
- in_progress: "empiezo", "retomo", "trabajando en la placa"
- on_hold_parts: "esperando repuestos", "faltan repuestos"
- on_hold_client: "esperando que el cliente autorice"
- external_work: "se fue al torno", "trabajo externo"
- completed: "moto lista", "ya terminé", "trabajo finalizado"

REGLAS:
1. Si el usuario menciona una placa colombiana (3 letras + 2-3 números o similar, ej: NOI82G, ABC12D), extráela en "entities.placa" SIN guiones ni espacios.
2. Si deletrea la placa con espacios ("N O I 8 2 G"), júntala: "NOI82G".
3. Para CHANGE_STATUS es OBLIGATORIO extraer placa Y estado. Si falta alguno, clasifica como UNKNOWN.
4. El campo confidence refleja tu seguridad: 1.0=seguro, 0.5=ambiguo, 0.0=no entiendo.

Responde ÚNICAMENTE con JSON válido:
{{"intent": "...", "confidence": 0.0, "entities": {{"placa": null, "estado": null, "target_name": null}}}}"""


async def classify_unified_intent(text: str, user_role: str) -> dict:
    """
    Clasifica la intención del usuario con un prompt unificado sensible al rol.
    Reemplaza classify_admin_intent + classify_tech_intent cuando USE_UNIFIED_INTENT=True.

    Returns:
        {"intent": str, "confidence": float, "entities": {"placa": str|None, "estado": str|None, "target_name": str|None}}
    """
    allowed = ROLE_INTENTS.get(user_role, ROLE_INTENTS["technician"])
    allowed_block = ", ".join(allowed)
    system_prompt = UNIFIED_INTENT_SYSTEM_PROMPT.format(allowed_intents_block=allowed_block)

    try:
        response = await _call_openai_with_retry(
            lambda: aclient.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text}
                ],
                response_format={"type": "json_object"},
                max_tokens=120,
                temperature=0
            ),
            max_retries=2
        )
        data = json.loads(response.choices[0].message.content)

        intent = data.get("intent", "UNKNOWN")
        if intent not in allowed:
            intent = "UNKNOWN"

        confidence = float(data.get("confidence", 0.0))
        entities = data.get("entities", {})

        # Normalizar placa: quitar espacios y mayúsculas
        placa = entities.get("placa")
        if placa:
            placa = "".join(str(placa).upper().split())

        return {
            "intent": intent,
            "confidence": confidence,
            "entities": {
                "placa": placa,
                "estado": entities.get("estado"),
                "target_name": entities.get("target_name")
            }
        }
    except AIServiceError:
        logger.error("classify_unified_intent: OpenAI agotó reintentos")
        return {"intent": "UNKNOWN", "confidence": 0.0, "entities": {"placa": None, "estado": None, "target_name": None}}
    except Exception as e:
        logger.error(f"classify_unified_intent error inesperado: {e}")
        return {"intent": "UNKNOWN", "confidence": 0.0, "entities": {"placa": None, "estado": None, "target_name": None}}

TECH_INTENT_SYSTEM_PROMPT = """
Eres un clasificador de intenciones para técnicos y administradores de taller de motocicletas.
El usuario te hablará para gestionar reparaciones o consultar información.

INTENCIONES:
1. CHANGE_STATUS: Cambiar el estado de una moto. Requiere PLACA (ej. NOI82G) y ESTADO.
2. ACTIVE_ORDERS: Consultar órdenes activas, pendientes o qué motos tiene asignadas (ej: "muéstrame mis órdenes", "órdenes activas", "qué tengo pendiente").
3. UNKNOWN: Otros temas.

ESTADOS VÁLIDOS (solo para CHANGE_STATUS):
- in_progress (ej. "empiezo revisión", "trabajando en la placa")
- on_hold_parts (ej. "esperando repuestos", "pausa por repuestos")
- on_hold_client (ej. "esperando que el cliente autorice")
- external_work (ej. "se fue al torno/pintura")
- completed (ej. "moto lista", "ya terminé")

El campo confidence refleja tu seguridad: 1.0=seguro, 0.5=ambiguo, 0.0=no entiendo.

Responde ÚNICAMENTE en JSON:
{"intent": "CHANGE_STATUS", "confidence": 0.9, "placa": "XYZ123", "estado": "in_progress"}
o
{"intent": "ACTIVE_ORDERS", "confidence": 1.0, "placa": null, "estado": null}
"""

async def classify_tech_intent(text: str) -> dict:
    """Clasifica el cambio de estado de una moto por lenguaje natural del mecánico."""
    try:
        response = await aclient.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": TECH_INTENT_SYSTEM_PROMPT},
                {"role": "user", "content": text}
            ],
            response_format={"type": "json_object"},
            max_tokens=80,
            temperature=0
        )
        data = json.loads(response.choices[0].message.content)
        return {
            "intent": data.get("intent", "UNKNOWN"),
            "confidence": float(data.get("confidence", 0.5)),
            "placa": data.get("placa"),
            "estado": data.get("estado"),
        }
    except Exception as e:
        logger.error(f"Error AI classify_tech_intent: {e}")
        return {"intent": "UNKNOWN", "confidence": 0.0, "placa": None, "estado": None}

async def extract_data_from_image(image_url: str) -> dict:
    """
    Extrae todos los campos posibles de una Tarjeta de Propiedad colombiana o SOAT.

    Campos retornados (todos con la misma key en todo el sistema):
      placa, vin, numero_motor, propietario, numero_documento_propietario,
      marca, linea, modelo, color, cilindraje

    Si un campo no es visible, devuelve null — nunca inventa datos.
    """
    prompt = (
        "Eres un experto en documentos vehiculares colombianos. "
        "Analiza esta imagen de una Tarjeta de Propiedad o SOAT y extrae TODOS los campos que puedas leer con claridad. "
        "Devuelve ÚNICAMENTE un JSON válido con estas claves exactas (null si no es legible):\n\n"
        "{\n"
        '  "placa": "ABC123",\n'
        '  "vin": "1HGBH41JXMN109186",\n'
        '  "numero_motor": "",\n'
        '  "propietario": "NOMBRE COMPLETO DEL PROPIETARIO",\n'
        '  "numero_documento_propietario": "12345678",\n'
        '  "marca": "UM",\n'
        '  "linea": "CYCLONE",\n'
        '  "modelo": "2022",\n'
        '  "color": "NEGRO",\n'
        '  "cilindraje": "150"\n'
        "}\n\n"
        "REGLAS CRÍTICAS:\n"
        "- placa: exactamente 6 caracteres alfanuméricos, sin espacios ni guiones.\n"
        "- vin: exactamente 17 caracteres si es visible; si solo ves el número de chasis corto, ponlo igual.\n"
        "- numero_documento_propietario: solo dígitos, sin puntos ni espacios.\n"
        "- modelo: el año del modelo (4 dígitos) si aparece.\n"
        "- NO inventes datos; si no lo ves claramente, devuelve null.\n"
        "- NO incluyas claves adicionales al esquema anterior."
    )
    try:
        response = await _call_openai_with_retry(
            lambda: aclient.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": image_url, "detail": "high"}}
                        ]
                    }
                ],
                response_format={"type": "json_object"},
                max_tokens=400,
                temperature=0,
            ),
            max_retries=2
        )
        data = json.loads(response.choices[0].message.content)
        # Normalizar placa y VIN siempre en mayúsculas sin espacios
        if data.get("placa"):
            data["placa"] = "".join(str(data["placa"]).upper().split())
        if data.get("vin"):
            data["vin"] = "".join(str(data["vin"]).upper().split())
        return data
    except AIServiceError:
        logger.error("extract_data_from_image: OpenAI agotó reintentos")
        return {"placa": None, "vin": None, "numero_motor": None, "propietario": None,
                "numero_documento_propietario": None, "marca": None, "linea": None,
                "modelo": None, "color": None, "cilindraje": None}
    except Exception as e:
        logger.error(f"Error AI Vision extract_data: {e}")
        return {"placa": None, "vin": None, "numero_motor": None, "propietario": None,
                "numero_documento_propietario": None, "marca": None, "linea": None,
                "modelo": None, "color": None, "cilindraje": None}

async def transcribe_voice(voice_path: str, prompt: str = "") -> str:
    """Convierte un archivo de voz a texto."""
    try:
        with open(voice_path, "rb") as audio_file:
            transcript = await aclient.audio.transcriptions.create(
                model="whisper-1", 
                file=audio_file,
                prompt=prompt,
                response_format="text",
                temperature=0.2
            )
        return transcript
    except Exception as e:
        logger.error(f"Error Whisper API: {e}")
        return ""

async def extract_motive_data(text: str) -> list:
    """Estructura el motivo narrado en viñetas puntuales."""
    try:
        response = await aclient.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "El usuario describirá los problemas o mantenimientos requeridos para su motocicleta. Sintetiza su petición en una lista en formato JSON bajo la clave 'motivos'. Omite saludos. Ejemplo: {\"motivos\": [\"Cambio de aceite\", \"Revisión frenos\"]}"},
                {"role": "user", "content": text}
            ],
            response_format={"type": "json_object"},
            max_tokens=150,
            temperature=0
        )
        data = json.loads(response.choices[0].message.content)
        return data.get("motivos", [])
    except Exception as e:
        logger.error(f"Error AI Motive Extractor: {e}")
        return [text]

async def classify_admin_intent(text: str) -> dict:
    """Clasifica la orden de un administrador general (Dashboard, Pending, etc)."""
    system_prompt = """
    Eres Sonia, asistente técnica. Clasifica el mensaje del jefe en una sola de estas intenciones (Retorna JSON):
    - PENDING_USERS: Quiere revisar solicitudes de ingreso pendientes.
    - APPROVE_USER: Quiere aprobar a alguien (ej: "Sonia, aprueba a Juan"). Extrae el nombre en 'target_name'.
    - REJECT_USER: Quiere rechazar a alguien. Extrae el nombre en 'target_name'.
    - LOAD_TENANTS: Quiere cargar la base de talleres/excel.
    - OPEN_PANEL: Quiere ver el menú o panel general.
    - UNKNOWN: Saludos o peticiones no relacionadas.

    Estructura JSON: {"intent": "APPROVE_USER", "target_name": "Juan Perez"}
    """
    try:
        response = await aclient.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ],
            response_format={"type": "json_object"},
            max_tokens=60,
            temperature=0
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        logger.error(f"Error AI Admin Intent: {e}")
        return {"intent": "UNKNOWN", "target_name": None}

async def extract_data_from_text(text: str) -> dict:
    prompt = f"""
    Eres Sonia, una inteligente asistente experta para talleres de motocicletas. 
    Analiza este texto narrado (transcripción de audio): "{text}"
    
    INSTRUCCIONES CRÍTICAS:
    1. PLACA: Identifica la placa colombiana (3 letras 2 números 1 letra o similar). 
       - Si viene deletreada con espacios (e.g., "N O I 8 2 G"), júntala: "NOI82G".
       - Ignora palabras como "la placa es", "moto con placa", "busco la".
       - Devuelve solo la placa limpia de 6 caracteres.
    2. VIN: Extrae el chasis de 17 caracteres si se menciona.
    3. OTROS: Extrae marca, modelo, línea y propietario si están presentes.

    Responde ÚNICAMENTE con un objeto JSON:
    {{
      "placa": "AAA123",
      "vin": "",
      "marca": "",
      "linea": "",
      "modelo": "",
      "propietario": "",
      "identificacion_propietario": ""
    }}
    """
    try:
        response = await aclient.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            response_format={ "type": "json_object" },
            temperature=0
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        logger.error(f"Error OpenAI Text Extraction: {e}")
        return {}

async def extract_reception_data(text: str) -> dict:
    prompt = f"""
    Eres Sonia, asistente de un taller de motos.
    Extrae los siguientes 4 datos vitales de este mensaje del cliente para la orden de servicio: "{text}"
    
    1. Teléfono (celular)
    2. Kilometraje (km) -> ATENCIÓN: Si el usuario escribe únicamente números enteros (ej. "5463" o "5463 "), DEBES APRENDER QUE ES EL KILOMETRAJE VÁLIDO. No busques la palabra "km" o "kilómetros" obligatoriamente.
    3. Nivel de gasolina (ej. Lleno, medio, 1/4, reserva)
    4. Motivo de ingreso (razón por la que trae la moto)
    
    Responde ÚNICAMENTE con un objeto JSON válido:
    {{
      "telefono": "",
      "kilometraje": "",
      "gasolina": "",
      "motivo": ""
    }}
    Si alguno falta, déjalo vacío "".
    """
    try:
        response = await aclient.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            response_format={ "type": "json_object" }
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        logger.error(f"Error OpenAI Reception: {e}")
        return {}

async def extract_part_data(text: str) -> dict:
    """
    Extrae información de un repuesto desde texto libre del técnico.

    Retorna:
        {"reference": str|None, "qty": int, "part_type": "warranty"|"paid"|"quote"}
    """
    try:
        response = await _call_openai_with_retry(
            lambda: aclient.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Eres un asistente de taller de motocicletas. El técnico te describe un repuesto que necesita. "
                            "Extrae la información y devuelve ÚNICAMENTE JSON válido con estas claves:\n"
                            '- "reference": código o nombre del repuesto (string o null si no se menciona)\n'
                            '- "qty": cantidad numérica (entero, default 1)\n'
                            '- "part_type": "warranty" si es por garantía, "quote" si es una cotización, "paid" en cualquier otro caso\n\n'
                            'Ejemplo: {"reference": "12345", "qty": 2, "part_type": "warranty"}'
                        )
                    },
                    {"role": "user", "content": text}
                ],
                response_format={"type": "json_object"},
                max_tokens=100,
                temperature=0
            ),
            max_retries=2
        )
        data = json.loads(response.choices[0].message.content)
        return {
            "reference": data.get("reference"),
            "qty": int(data.get("qty", 1)),
            "part_type": data.get("part_type", "paid")
        }
    except AIServiceError:
        logger.error("extract_part_data: OpenAI agotó reintentos")
        return {"reference": None, "qty": 1, "part_type": "paid"}
    except Exception as e:
        logger.error(f"extract_part_data error: {e}")
        return {"reference": None, "qty": 1, "part_type": "paid"}


async def extract_reception_data_from_image(image_url: str) -> dict:
    prompt = """
    Eres Sonia, una experta asesora de servicio técnico para motocicletas.
    Analiza esta imagen, que probablemente sea una foto del tablero (velocímetro/indicadores) de la motocicleta.
    Extrae estrictamente los siguientes datos, si logras verlos en los medidores:
    - Kilometraje (solo el número, sin letras ni símbolos)
    - Gasolina (clasifica el nivel de combustible mostrado obligatoriamente en uno de estos valores: Lleno, Medio, 1/4, Reserva)

    🚨 MUY IMPORTANTE PARA LA GASOLINA:
    - Fíjate bien en el indicador que suele tener una "F" (Full/Lleno) y una "E" (Empty/Reserva).
    - En tableros digitales, la gasolina se muestra con barras iluminadas entre la E y la F.
    - Si solo hay una o dos barritas iluminadas cerca de la 'E', significa 'Reserva'.
    - Si las barras llegan hasta la mitad del medidor, es 'Medio'.
    - Si las barras llegan casi hasta la 'F', es 'Lleno'.
    - ¡No te inventes que está Lleno si ves la mayoría de las barras oscuras o apagadas!

    Responde ÚNICAMENTE con un objeto JSON válido con esta estructura:
    {
      "telefono": "",
      "kilometraje": "15000",
      "gasolina": "Medio",
      "motivo": ""
    }
    Si no logras ver con claridad la aguja/medidor de gasolina o los números del kilometraje, deja el campo respectivo como "". Los campos 'telefono' y 'motivo' déjalos siempre vacíos "" porque no se pueden extraer de una foto del tablero.
    """
    try:
        response = await aclient.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": image_url,
                            },
                        },
                    ],
                }
            ],
            max_tokens=300,
            response_format={ "type": "json_object" }
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        logger.error(f"Error OpenAI Reception Image: {e}")
        return {}
