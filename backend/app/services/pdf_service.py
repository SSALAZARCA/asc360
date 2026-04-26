import os
import io
import uuid
import logging
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML
from minio import Minio

logger = logging.getLogger(__name__)

_GAS_BAR_WIDTHS = {"Lleno": 100, "3/4": 75, "Medio": 50, "1/4": 25, "Reserva": 10}

def _gas_to_percent(gas_level: str) -> int:
    return _GAS_BAR_WIDTHS.get(gas_level, 50)

def _fix_photo_urls_for_weasyprint(photos: list) -> list:
    """Reemplaza localhost:9000 por minio:9000 para que WeasyPrint dentro de Docker pueda cargar las imágenes."""
    result = []
    for p in photos:
        if isinstance(p, dict) and p.get("url"):
            fixed = dict(p)
            fixed["url"] = fixed["url"].replace("http://localhost:9000", f"http://{MINIO_ENDPOINT}")
            result.append(fixed)
        else:
            result.append(p)
    return result

# Configuración de S3 / MinIO
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "umadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "umadmin123")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"
BUCKET_NAME = "um-service-docs"

minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=MINIO_SECURE
)

def ensure_bucket_exists():
    try:
        if not minio_client.bucket_exists(BUCKET_NAME):
            minio_client.make_bucket(BUCKET_NAME)
    except Exception as e:
        logger.error(f"Error checking/creating MinIO bucket: {e}")

# Inicializamos el entorno de plantillas HTML
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), '..', 'html_templates')
jinja_env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))

async def generate_and_upload_reception_pdf(
    order_data: dict,
    reception_data: dict,
    vehicle_data: dict,
    client_data: dict,
    tenant_data: dict = None,
) -> str:
    ensure_bucket_exists()

    template = jinja_env.get_template("reception_act.html")
    tenant_data = tenant_data or {}

    gas_level = reception_data.get("gas_level", "")
    raw_photos = reception_data.get("damage_photos_urls", []) or []

    context = {
        "order_id": order_data.get("id", "PENDING"),
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        # Taller
        "tenant_name":  tenant_data.get("name", "UM Colombia"),
        "tenant_nit":   tenant_data.get("nit", ""),
        "tenant_phone": tenant_data.get("phone", ""),
        "tenant_city":  tenant_data.get("city", ""),
        # Cliente / Vehículo
        "owner_name":    client_data.get("full_name", "N/A"),
        "owner_id":      client_data.get("identification", "N/A"),
        "owner_email":   client_data.get("email") or "",
        "owner_phone":   client_data.get("phone") or "",
        "vehicle_model": vehicle_data.get("model", "N/A"),
        "vehicle_plate": vehicle_data.get("plate", "N/A"),
        "vehicle_vin":   vehicle_data.get("vin", "N/A"),
        "vehicle_motor": vehicle_data.get("motor", ""),
        "vehicle_color": vehicle_data.get("color", ""),
        # Recepción
        "mileage_km":    reception_data.get("mileage_km", 0),
        "gas_level":     gas_level,
        "fuel_bar_width": _gas_to_percent(gas_level),
        "service_type":  order_data.get("service_type", "regular"),
        "customer_notes":       reception_data.get("customer_notes", ""),
        "warranty_warnings":    reception_data.get("warranty_warnings", ""),
        "intake_answers":       reception_data.get("intake_answers", []),
        "accessories":          reception_data.get("accessories", []),
        "general_observations": reception_data.get("general_observations"),
        "damage_photos_urls":   _fix_photo_urls_for_weasyprint(raw_photos),
        # Técnico (opcional)
        "technician_name": order_data.get("technician_name", ""),
        # Firma
        "accepted_at":    order_data.get("accepted_at"),
        "accepted_phone": order_data.get("accepted_phone"),
        "bypass_at":      order_data.get("bypass_at"),
        "bypass_by_name": order_data.get("bypass_by_name"),
    }

    # Renderizar HTML a String
    html_out = template.render(context)
    
    # WeasyPrint es CPU-bound y sincrónico — lo corremos en un thread pool
    # para no bloquear el event loop de asyncio mientras se genera el PDF.
    import asyncio
    from functools import partial
    loop = asyncio.get_event_loop()
    pdf_bytes = await loop.run_in_executor(
        None,  # usa el ThreadPoolExecutor por defecto
        partial(HTML(string=html_out).write_pdf)
    )
    pdf_stream = io.BytesIO(pdf_bytes)
    
    # Subir a MinIO
    object_name = f"receptions/{datetime.now().year}/{datetime.now().month}/act_{uuid.uuid4()}.pdf"
    
    try:
        minio_client.put_object(
            BUCKET_NAME,
            object_name,
            pdf_stream,
            length=len(pdf_bytes),
            content_type="application/pdf"
        )
        from datetime import timedelta
        
        # Generar URL con firma temporal de lectura (2 horas)
        presigned_url = minio_client.presigned_get_object(
            BUCKET_NAME,
            object_name,
            expires=timedelta(hours=2)
        )
        
        # Hack local: El backend corre en docker (host "minio"), pero el bot en el host de windows.
        # Intercambiamos el host para que el request del bot funcione desde fuera de la red Docker.
        pdf_url = presigned_url.replace(f"http://{MINIO_ENDPOINT}", "http://localhost:9000")
        
        return pdf_url
    except Exception as e:
        logger.error(f"Error uploading PDF to MinIO: {e}")
        return ""

async def upload_file_to_minio(file_bytes: bytes, file_name: str, content_type: str) -> str:
    """Sube un archivo genérico (ej. Foto de la Moto) y retorna su URL estática."""
    ensure_bucket_exists()
    
    stream = io.BytesIO(file_bytes)
    object_name = f"evidences/{datetime.now().year}/{datetime.now().month}/{uuid.uuid4()}_{file_name}"
    
    try:
        minio_client.put_object(
            BUCKET_NAME,
            object_name,
            stream,
            length=len(file_bytes),
            content_type=content_type
        )
        file_url = f"http://localhost:9000/{BUCKET_NAME}/{object_name}"
        return file_url
    except Exception as e:
        logger.error(f"Error uploading file {file_name} to MinIO: {e}")
        return ""

async def get_pdf_stream_from_minio(object_name: str) -> bytes:
    """Extrae un archivo directamente del bucket de MinIO devolviendo sus bytes."""
    try:
        response = minio_client.get_object(BUCKET_NAME, object_name)
        data = response.read()
        response.close()
        response.release_conn()
        return data
    except Exception as e:
        logger.error(f"Error extrayendo {object_name} de MinIO: {e}")
        return None
