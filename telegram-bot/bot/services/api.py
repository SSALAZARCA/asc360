import httpx
from core.config import BACKEND_URL, SONIA_BOT_SECRET, logger

async def get_pending_users() -> list:
    """Obtiene la lista de usuarios pendientes de aprobación del Backend."""
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(
                f"{BACKEND_URL}/users/pending",
                headers={"x-sonia-secret": SONIA_BOT_SECRET},
                timeout=10.0
            )
            if res.status_code == 200:
                return res.json()
            logger.warning(f"get_pending_users: {res.status_code} — {res.text}")
            return []
        except Exception as e:
            logger.error(f"Error HTTP get_pending_users: {e}")
            return []

async def set_user_status(user_id: str, new_status: str) -> dict:
    """Aprueba o rechaza a un usuario en el Backend."""
    async with httpx.AsyncClient() as client:
        try:
            res = await client.patch(
                f"{BACKEND_URL}/users/{user_id}/status",
                json={"status": new_status},
                headers={"x-sonia-secret": SONIA_BOT_SECRET},
                timeout=10.0
            )
            if res.status_code == 200:
                return res.json()
            return {}
        except Exception as e:
            logger.error(f"Error HTTP set_user_status: {e}")
            return {}

async def register_tenant_batch(payloads: list) -> tuple:
    """Envia un listado masivo de Tenants (Centros) para ser creados."""
    inserted, skipped, errors = 0, 0, 0
    async with httpx.AsyncClient() as client:
        for payload in payloads:
            try:
                res = await client.post(f"{BACKEND_URL}/tenants/", json=payload, timeout=5.0)
                if res.status_code in (200, 201):
                    inserted += 1
                elif res.status_code == 409:
                    skipped += 1
                else:
                    logger.error(f"Error registrando tenant: {res.text}")
                    errors += 1
            except Exception as e:
                logger.error(f"HTTP Error tenant_batch: {e}")
                errors += 1
    return inserted, skipped, errors

async def get_all_tenants() -> list:
    """Obtiene todos los tenants de la red usando el endpoint interno del bot."""
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(
                f"{BACKEND_URL}/tenants/bot-list",
                headers={"x-sonia-secret": SONIA_BOT_SECRET},
                timeout=10.0
            )
            if res.status_code == 200:
                return res.json()
            logger.warning(f"get_all_tenants: status {res.status_code} — {res.text}")
            return []
        except Exception as e:
            logger.error(f"Error HTTP get_all_tenants: {e}")
            return []

async def get_admin_dashboard() -> dict:
    """Obtiene el dashboard de motocicletas a nivel nacional."""
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(f"{BACKEND_URL}/orders/dashboard/admin", timeout=10.0)
            if res.status_code == 200:
                return res.json()
            return None
        except Exception as e:
            logger.error(f"Error HTTP get_admin_dashboard: {e}")
            return None

async def get_tenant_active_orders(tenant_id: str) -> list:
    """Órdenes activas pertenecientes a un Tenant ID (Admin Local)."""
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(f"{BACKEND_URL}/orders/active/tenant/{tenant_id}", timeout=10.0)
            if res.status_code == 200:
                return res.json()
            return None
        except Exception:
            return None

async def get_technician_active_orders(technician_id: str) -> list:
    """Órdenes activas de un mecánico en específico."""
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(f"{BACKEND_URL}/orders/active/technician/{technician_id}", timeout=10.0)
            if res.status_code == 200:
                return res.json()
            return None
        except Exception:
            return None

async def resolve_order_by_plate(technician_id: str, plate: str) -> str:
    """Busca el order_id de la moto activa del técnico según su placa."""
    orders = await get_technician_active_orders(technician_id)
    if not orders: return None
    plate = plate.upper().strip()
    for o in orders:
        if o.get("plate", "").upper() == plate or o.get("vehicle", {}).get("plate", "").upper() == plate:
            return o["id"]
    return None

async def update_order_status(
    order_id: str,
    status: str,
    technician_id: str = None,
    diagnosis: str = None,
    parts: list = None,
    recorded_by_telegram_id: str = None
) -> bool:
    """Actualiza el estado de una orden. Acepta diagnóstico y repuestos opcionales."""
    payload = {"status": status}
    if technician_id:
        payload["technician_id"] = technician_id
    if diagnosis:
        payload["diagnosis"] = diagnosis
    if parts:
        payload["parts"] = parts
    if recorded_by_telegram_id:
        payload["recorded_by_telegram_id"] = recorded_by_telegram_id

    async with httpx.AsyncClient() as client:
        try:
            res = await client.put(
                f"{BACKEND_URL}/orders/{order_id}/status",
                json=payload,
                headers={"x-sonia-secret": SONIA_BOT_SECRET},
                timeout=10.0
            )
            return res.status_code == 200
        except Exception:
            return False


async def post_work_log(order_id: str, diagnosis: str, media_urls: list = None, telegram_id: str = None) -> bool:
    """Registra un diagnóstico/nota de trabajo en una orden."""
    payload = {
        "diagnosis": diagnosis,
        "media_urls": media_urls or [],
        "recorded_by_telegram_id": telegram_id
    }
    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(
                f"{BACKEND_URL}/orders/{order_id}/work-log",
                json=payload,
                timeout=10.0
            )
            return res.status_code == 201
        except Exception as e:
            logger.error(f"Error post_work_log: {e}")
            return False


async def post_order_parts(order_id: str, parts: list) -> bool:
    """Registra repuestos requeridos en una orden. parts = lista de dicts {reference, qty, part_type}."""
    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(
                f"{BACKEND_URL}/orders/{order_id}/parts",
                json=parts,
                timeout=10.0
            )
            return res.status_code == 201
        except Exception as e:
            logger.error(f"Error post_order_parts: {e}")
            return False


async def register_user(payload: dict) -> dict:
    """Crea un nuevo usuario en estado pending. Uso exclusivo del flujo de auto-registro."""
    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(
                f"{BACKEND_URL}/users/",
                json=payload,
                headers={"x-sonia-secret": SONIA_BOT_SECRET},
                timeout=10.0
            )
            if res.status_code in (200, 201):
                return res.json()
            logger.error(f"register_user: {res.status_code} — {res.text}")
            return {}
        except Exception as e:
            logger.error(f"Error register_user: {e}")
            return {}


async def get_superadmin_telegram_ids() -> list:
    """Devuelve los telegram_ids de todos los superadmins activos."""
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(
                f"{BACKEND_URL}/users/superadmins/telegram-ids",
                headers={"x-sonia-secret": SONIA_BOT_SECRET},
                timeout=10.0
            )
            if res.status_code == 200:
                return res.json()
            logger.warning(f"get_superadmin_telegram_ids: {res.status_code}")
            return []
        except Exception as e:
            logger.error(f"Error get_superadmin_telegram_ids: {e}")
            return []


async def search_parts_catalog(order_id: str, description: str) -> list:
    """Busca secciones del catálogo de despiece según descripción del técnico."""
    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(
                f"{BACKEND_URL}/parts/search",
                json={"order_id": order_id, "description": description},
                headers={"x-sonia-secret": SONIA_BOT_SECRET},
                timeout=20.0,
            )
            if res.status_code == 200:
                return res.json()
            logger.warning(f"search_parts_catalog: {res.status_code} — {res.text}")
            return []
        except Exception as e:
            logger.error(f"Error search_parts_catalog: {e}")
            return []


async def get_part_by_number(section_id: str, order_num: str) -> dict:
    """Obtiene una parte por su número de posición en el diagrama."""
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(
                f"{BACKEND_URL}/parts/section/{section_id}/item/{order_num}",
                headers={"x-sonia-secret": SONIA_BOT_SECRET},
                timeout=10.0,
            )
            if res.status_code == 200:
                return res.json()
            return None
        except Exception as e:
            logger.error(f"Error get_part_by_number: {e}")
            return None


async def get_part_by_factory_code(factory_code: str) -> dict:
    """Busca una parte por su código de fábrica (fallback cuando no se encuentra en diagrama)."""
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(
                f"{BACKEND_URL}/parts/factory/{factory_code}",
                headers={"x-sonia-secret": SONIA_BOT_SECRET},
                timeout=10.0,
            )
            if res.status_code == 200:
                return res.json()
            return None
        except Exception as e:
            logger.error(f"Error get_part_by_factory_code: {e}")
            return None


async def get_catalog_models_for_bot() -> list:
    """Modelos UM que ya tienen catálogo de despiece cargado."""
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(
                f"{BACKEND_URL}/parts/bot/catalog-models",
                headers={"x-sonia-secret": SONIA_BOT_SECRET},
                timeout=10.0,
            )
            if res.status_code == 200:
                return res.json()
            logger.warning(f"get_catalog_models_for_bot: {res.status_code} — {res.text}")
            return []
        except Exception as e:
            logger.error(f"Error get_catalog_models_for_bot: {e}")
            return []


async def search_parts_by_model(model_code: str, description: str) -> list:
    """Busca secciones del catálogo usando model_code directamente (sin order_id)."""
    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(
                f"{BACKEND_URL}/parts/search-by-model",
                json={"model_code": model_code, "description": description},
                headers={"x-sonia-secret": SONIA_BOT_SECRET},
                timeout=20.0,
            )
            if res.status_code == 200:
                return res.json()
            logger.warning(f"search_parts_by_model: {res.status_code} — {res.text}")
            return []
        except Exception as e:
            logger.error(f"Error search_parts_by_model: {e}")
            return []


async def get_part_by_code(model_code: str, order_num: str) -> dict:
    """Busca una parte por modelo y código de posición del diagrama (ej: B1-3)."""
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(
                f"{BACKEND_URL}/parts/model/{model_code}/item/{order_num}",
                headers={"x-sonia-secret": SONIA_BOT_SECRET},
                timeout=10.0,
            )
            if res.status_code == 200:
                return res.json()
            return None
        except Exception as e:
            logger.error(f"Error get_part_by_code: {e}")
            return None


async def get_tenant_config(tenant_id: str) -> dict:
    """Obtiene la configuración del taller (diagnosis_reminder_minutes, etc.)."""
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(
                f"{BACKEND_URL}/tenants/{tenant_id}/config",
                headers={"x-sonia-secret": SONIA_BOT_SECRET},
                timeout=10.0
            )
            if res.status_code == 200:
                return res.json()
            return {"diagnosis_reminder_minutes": 60}
        except Exception as e:
            logger.error(f"Error get_tenant_config: {e}")
            return {"diagnosis_reminder_minutes": 60}
