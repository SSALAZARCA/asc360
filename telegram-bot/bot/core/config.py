import os
import logging
from dotenv import load_dotenv, find_dotenv

# Cargar variables de entorno
load_dotenv(find_dotenv(usecwd=True))

# Configuración de Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuraciones de API
BACKEND_URL = os.getenv("API_URL", "http://backend:8000/api/v1")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
SONIA_BOT_SECRET = os.getenv("SONIA_BOT_SECRET")
if not SONIA_BOT_SECRET:
    raise ValueError("SONIA_BOT_SECRET must be set via environment variable — no default allowed")
FAKE_TENANT = os.getenv("FAKE_TENANT", "")

# Control de caché de autenticación
USER_CACHE_TTL_SECONDS = int(os.getenv("USER_CACHE_TTL_SECONDS", "300"))

# Control de reintentos OpenAI
OPENAI_MAX_RETRIES = int(os.getenv("OPENAI_MAX_RETRIES", "3"))

# Feature flag: clasificador de intenciones unificado (voz + texto)
USE_UNIFIED_INTENT = os.getenv("USE_UNIFIED_INTENT", "false").lower() == "true"
