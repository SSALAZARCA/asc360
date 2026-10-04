"""
Motored: envio de un mensaje por la Bot API de Telegram con el bot de Lore.

Mismo enfoque que `app/services/notification_service.py` (httpx directo,
timeout finito) pero con el token de Lore (`LORE_BOT_TOKEN`), nunca el de
UM. El proceso lore-bot no participa.

Seguridad: la URL de la Bot API lleva el token, y los mensajes de las
excepciones de httpx la incluyen; por eso NUNCA se loguea la excepcion ni su
traceback, solo el nombre de su tipo. El chat se loguea enmascarado.
`enviar_mensaje` no lanza jamas.
"""
import logging
from typing import Optional

import httpx

logger = logging.getLogger("motored.avisos_telegram")
# httpx loguea la URL (con el token) a nivel INFO: se fija en WARNING.
logging.getLogger("httpx").setLevel(logging.WARNING)

TELEGRAM_API_BASE = "https://api.telegram.org"
TIMEOUT_SEGUNDOS = 10.0


def _enmascarar(chat_id: int) -> str:
    return "***" + str(chat_id)[-3:]


async def enviar_mensaje(
    token: str, chat_id: int, texto: str,
    cliente: Optional[httpx.AsyncClient] = None,
) -> bool:
    """`True` si Telegram aceptó el mensaje; `False` ante cualquier error."""
    url = f"{TELEGRAM_API_BASE}/bot{token}/sendMessage"
    try:
        if cliente is None:
            async with httpx.AsyncClient(timeout=TIMEOUT_SEGUNDOS) as propio:
                respuesta = await propio.post(
                    url, json={"chat_id": chat_id, "text": texto})
        else:
            respuesta = await cliente.post(
                url, json={"chat_id": chat_id, "text": texto})
        respuesta.raise_for_status()
    except Exception as error:  # noqa: BLE001 -- nunca hacia el loop
        logger.warning(
            "aviso de antigüedad: Telegram falló para el chat %s (%s)",
            _enmascarar(chat_id), type(error).__name__)
        return False
    return True
