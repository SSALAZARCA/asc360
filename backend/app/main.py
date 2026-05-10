from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.config import settings
from app.core.limiter import limiter

is_production = settings.ENVIRONMENT == "production"

app = FastAPI(
    title="UM Colombia - Red de Servicio API",
    description="Backend para gestión de órdenes de taller, pedidos B2B e integraciones con Telegram y Softway.",
    version="1.0.0",
    # En producción los docs están deshabilitados — son información gratis para atacantes
    docs_url=None if is_production else "/docs",
    redoc_url=None if is_production else "/redoc",
    openapi_url=None if is_production else "/openapi.json",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Sonia-Secret", "X-Tenant-ID"],
)

@app.get("/health")
async def health_check():
    return {
        "status": "ok", 
        "service": "um_backend", 
        "version": app.version
    }

from app.api.v1.router import api_router

# Rutas se incluyen más adelante (Ej: app.include_router(api_router, prefix="/api/v1"))
app.include_router(api_router, prefix="/api/v1")
