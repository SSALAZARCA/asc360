import os
import io
import logging
from datetime import timedelta
from minio import Minio
from minio.error import S3Error

logger = logging.getLogger(__name__)

# Mismas variables de entorno que pdf_service.py
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "umadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "umadmin123")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"

IMPORTS_BUCKET = "um-import-docs"

minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=MINIO_SECURE,
)


def ensure_bucket(bucket_name: str) -> None:
    try:
        if not minio_client.bucket_exists(bucket_name):
            minio_client.make_bucket(bucket_name)
            logger.info(f"Bucket creado: {bucket_name}")
    except S3Error as e:
        logger.error(f"Error creando bucket {bucket_name}: {e}")
        raise


async def upload_bytes(
    bucket: str,
    object_name: str,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> str:
    """Sube bytes a MinIO y retorna el object_name (no la URL)."""
    ensure_bucket(bucket)
    minio_client.put_object(
        bucket,
        object_name,
        io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    return object_name


def get_presigned_url(
    bucket: str,
    object_name: str,
    expires_hours: int = 2,
) -> str:
    """Genera una URL pre-firmada para descarga directa."""
    url = minio_client.presigned_get_object(
        bucket,
        object_name,
        expires=timedelta(hours=expires_hours),
    )
    # En entorno local MinIO puede devolver la URL interna (minio:9000).
    # Se reemplaza por localhost para que el browser pueda acceder.
    minio_public_host = os.getenv("MINIO_PUBLIC_HOST", "localhost:9000")
    url = url.replace(MINIO_ENDPOINT, minio_public_host)
    return url


async def get_bytes(bucket: str, object_name: str) -> bytes | None:
    """Descarga un objeto de MinIO y retorna sus bytes."""
    try:
        response = minio_client.get_object(bucket, object_name)
        data = response.read()
        response.close()
        response.release_conn()
        return data
    except S3Error as e:
        logger.error(f"Error descargando {object_name} de {bucket}: {e}")
        return None
