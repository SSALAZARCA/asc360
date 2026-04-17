from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import List

class Settings(BaseSettings):
    # Base de datos
    DATABASE_URL: str = "postgresql+asyncpg://umadmin:umadmin_secret@127.0.0.1:5432/um_service_db"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # MinIO
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "umadmin"
    MINIO_SECRET_KEY: str = "minio_secret_admin"
    MINIO_SECURE: bool = False

    # Secretos y tokens — OBLIGATORIO sobrescribir en producción via .env
    SECRET_KEY: str
    TELEGRAM_BOT_TOKEN: str = ""
    OPENAI_API_KEY: str = ""
    SOFTWAY_API_URL: str = ""
    SONIA_BOT_SECRET: str

    # CORS — acepta cadena separada por comas o lista JSON
    # Ejemplo: ALLOWED_ORIGINS=https://tudominio.com,https://www.tudominio.com
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000"]

    # Entorno — controla comportamiento de docs y debug
    ENVIRONMENT: str = "development"

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_allowed_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    model_config = SettingsConfigDict(env_file="../.env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
