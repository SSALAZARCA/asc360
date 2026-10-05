from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Base de datos — requerido, sin default para forzar configuración explícita
    DATABASE_URL: str

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # MinIO — credenciales requeridas sin default
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str
    MINIO_SECRET_KEY: str
    MINIO_SECURE: bool = False
    MINIO_PUBLIC_URL: str = ""   # URL pública de MinIO (ej: https://minio.dominio.com). Si vacío, usa MINIO_ENDPOINT.

    # Secretos y tokens — OBLIGATORIO sobrescribir en producción via .env
    SECRET_KEY: str
    TELEGRAM_BOT_TOKEN: str = ""
    OPENAI_API_KEY: str = ""
    SOFTWAY_API_URL: str = ""
    SONIA_BOT_SECRET: str

    # CORS — cadena separada por comas
    # Ejemplo: ALLOWED_ORIGINS=https://tudominio.com,https://www.tudominio.com
    ALLOWED_ORIGINS: str = "http://localhost:3000"

    # Entorno — controla comportamiento de docs y debug
    ENVIRONMENT: str = "development"

    # Email de recepción (sdd/reception-email-notification) — apagado por
    # default hasta que se provisionen las credenciales SMTP en Coolify.
    RECEPTION_EMAIL_ENABLED: bool = False
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    SMTP_STARTTLS: bool = True

    # Motored Pedidos (sdd/motored-pedidos-cimientos) — módulo hermano,
    # aislado (DB, secreto y sesión propios). Apagado por default hasta que
    # se aprovisione su propia base de datos en Coolify. Todos opcionales
    # con default seguro para que el arranque de asc360 y su suite de tests
    # (que importan `app.main.app`) no dependan de estas variables.
    MOTORED_ENABLED: bool = False
    MOTORED_DATABASE_URL: str = ""
    MOTORED_SECRET_KEY: str = ""
    MOTORED_MAX_UPLOAD_MB: int = 10
    MOTORED_MAX_UPLOAD_ROWS: int = 50000

    # Motored Pedidos — Fase 2 "Ingesta" (sdd/motored-pedidos-ingesta,
    # ADR-1/1b): tuning del supervisor asyncio en proceso. Todos opcionales
    # con default seguro; ninguno tiene efecto mientras MOTORED_ENABLED sea
    # false, porque el supervisor nunca arranca (ensure_started() es un
    # no-op en ese caso).
    MOTORED_INGESTA_POLL_SEGUNDOS: int = 5
    MOTORED_INGESTA_TIMEOUT_MIN: int = 15
    MOTORED_INGESTA_PAUSA_MS: int = 0
    MOTORED_INGESTA_LOTE: int = 2000
    MOTORED_MINIO_BUCKET: str = "motored-cargas"
    MOTORED_MAX_MOVIMIENTO_UPLOAD_MB: int = 150
    MOTORED_MAX_MOVIMIENTO_ROWS: int = 500000
    # Lee los agregados de ventas del KPI desde las tablas resumen `kpi_*` (cuando estan
    # construidas y al dia) en vez de recorrer venta_detalle. Apagado = consultas en vivo.
    MOTORED_KPI_RESUMEN_ENABLED: bool = False
    # Cuanto espera una carga de ventas (o un cambio de configuracion que deja sucios los
    # resumenes) por el candado de una reconstruccion en curso antes de fallar con un mensaje claro.
    MOTORED_KPI_RESUMEN_LOCK_TIMEOUT_SEGUNDOS: int = 60
    MOTORED_RETENCION_ENABLED: bool = False
    MOTORED_RETENCION_DIAS: int = 90
    MOTORED_INGESTA_PERIODO_TOLERANCIA_PCT: float = 0.5

    # Motored Pedidos — Fase 3 "Motor" (sdd/motored-pedidos-motor, S6b,
    # ADR-5): loop asyncio PROPIO de las corridas, separado del supervisor
    # de cargas de la Fase 2.
    # - MOTORED_CORRIDAS_LOOP_ENABLED: interruptor de emergencia. Con
    #   `false` el loop de corridas no arranca nunca (el de cargas no se
    #   toca); una corrida PENDIENTE espera hasta reactivarlo. Se apaga con
    #   la variable de entorno y un redeploy, sin tocar código. Además
    #   MOTORED_ENABLED=false lo apaga junto con todo el módulo.
    # - MOTORED_CORRIDA_POLL_SEGUNDOS: cada cuánto revisa si hay algo que
    #   reclamar o barrer.
    # - MOTORED_CORRIDA_TIMEOUT_MIN: una corrida CALCULANDO sin latido por
    #   más de esto se considera muerta y el barrido la reintenta.
    # - MOTORED_CORRIDA_MAX_INTENTOS: reclamos antes de dejarla FALLIDA
    #   (E-CORRIDA-031); entre intento e intento espera 30 s * 2^(n-1).
    # - MOTORED_CORRIDA_RETENCION_*: purga diaria de corridas ANULADA,
    #   FALLIDA o BORRADOR con más de N días (nunca CERRADA). Apagada por
    #   defecto.
    MOTORED_CORRIDAS_LOOP_ENABLED: bool = True
    MOTORED_CORRIDA_POLL_SEGUNDOS: int = 5
    MOTORED_CORRIDA_TIMEOUT_MIN: int = 10
    MOTORED_CORRIDA_MAX_INTENTOS: int = 3
    MOTORED_CORRIDA_RETENCION_ENABLED: bool = False
    MOTORED_CORRIDA_RETENCION_DIAS: int = 45

    # Motored Pedidos — bot "Lore" (sdd/motored-ventas-perdidas-bot, Phase
    # 5, design D5): secreto compartido propio para autenticar las llamadas
    # del bot al backend. DEBE ser distinto de `SONIA_BOT_SECRET` (Lore no
    # comparte secretos/tokens con Sonia/UM) y de `MOTORED_SECRET_KEY`/
    # `SECRET_KEY` — ver `app/motored/deps_bot.py::lore_bot_secret_is_safe`.
    # Default vacío para que el arranque de asc360/backend nunca dependa de
    # esta variable (mismo criterio que `MOTORED_SECRET_KEY`).
    LORE_BOT_SECRET: str = ""

    # Motored — aviso anticipado de antigüedad de datos. El backend manda el
    # aviso por Telegram con el bot de Lore, así que lee el MISMO token que
    # el proceso lore-bot (`LORE_BOT_TOKEN`, ya definido en Coolify). Vacío:
    # no se envía nada por Telegram (se avisa en el log una vez) y el banner
    # dentro de la app sigue funcionando.
    # - MOTORED_AVISOS_ANTIGUEDAD_ENABLED: interruptor de emergencia del
    #   loop (con MOTORED_ENABLED=false se apaga junto con todo el módulo).
    # - MOTORED_AVISOS_POLL_SEGUNDOS: cada cuánto revisa si toca avisar.
    LORE_BOT_TOKEN: str = ""
    MOTORED_AVISOS_ANTIGUEDAD_ENABLED: bool = True
    MOTORED_AVISOS_POLL_SEGUNDOS: int = 60

    @property
    def allowed_origins_list(self) -> list:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    model_config = SettingsConfigDict(env_file="../.env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
