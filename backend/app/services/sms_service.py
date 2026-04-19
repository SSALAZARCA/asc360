import logging
import os

logger = logging.getLogger(__name__)

SMS_PROVIDER = os.getenv("SMS_PROVIDER", "stub")  # "stub" | "twilio" | etc.


async def send_otp_sms(phone: str, code: str) -> bool:
    """
    Envía el código OTP al teléfono del cliente.
    En modo stub, imprime en logs y retorna True.
    Cuando se defina el proveedor, reemplazar el bloque del provider aquí.
    """
    if SMS_PROVIDER == "stub":
        logger.warning(f"[SMS STUB] OTP para {phone}: {code}")
        return True

    # TODO: implementar proveedor real aquí
    # if SMS_PROVIDER == "twilio":
    #     ...
    logger.error(f"Proveedor SMS '{SMS_PROVIDER}' no implementado")
    return False
