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
SONIA_BOT_SECRET = os.getenv("SONIA_BOT_SECRET", "sonia-internal-secret-2024")
FAKE_TENANT = "c9a40552-3eb6-4cb4-bfff-6aacaead3ca7" # Tenant de prueba para entorno desarrollo

# Control de caché de autenticación
USER_CACHE_TTL_SECONDS = int(os.getenv("USER_CACHE_TTL_SECONDS", "3600"))

# Control de reintentos OpenAI
OPENAI_MAX_RETRIES = int(os.getenv("OPENAI_MAX_RETRIES", "3"))

# Feature flag: clasificador de intenciones unificado (voz + texto)
USE_UNIFIED_INTENT = os.getenv("USE_UNIFIED_INTENT", "false").lower() == "true"
