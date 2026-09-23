"""
Motored Pedidos — Fase 2 "Ingesta" (sdd/motored-pedidos-ingesta, ADR-6):
wrapper de MinIO para los archivos de carga (`carga_archivo`).

Implementación clean-room: NO importa `app.services.storage_service`, que
lee variables de entorno directamente con un default hardcodeado para el
secreto de MinIO -- inaceptable bajo la restricción "sin defaults de
credenciales" de esta fase. Este módulo construye su PROPIO cliente
`Minio` a partir de `settings` (mismas `MINIO_ENDPOINT`/`MINIO_ACCESS_KEY`/
`MINIO_SECRET_KEY`/`MINIO_SECURE` que ya usa asc360 para su propio MinIO --
Motored reutiliza el mismo servidor/credenciales, pero escribe en su
PROPIO bucket, `settings.MOTORED_MINIO_BUCKET` -- el mismo patrón "misma
infra, datos aislados" que Fase 1 ya usa para el Postgres compartido con
bases de datos separadas).

Convención de key: `{tipo}/{yyyy}/{mm}/{carga_id}.xlsx`.
"""
import hashlib
import tempfile
import uuid
from datetime import datetime, timezone
from typing import BinaryIO, NamedTuple, Optional

from minio import Minio
from minio.error import MinioException

from app.config import settings

# 10 MB: tamaño de parte para `put_object(length=-1, part_size=...)`, que
# habilita subida multipart en streaming -- un archivo real de producción
# de 76 MB nunca se buferea completo en memoria.
_PART_SIZE = 10 * 1024 * 1024

# Tamaño de cada lectura desde `entrada` hacia el spooled temp file. Bounded
# read: nunca `entrada.read()` sin límite.
_CHUNK_SIZE = 1024 * 1024


class SubidaArchivoError(Exception):
    """Envuelve cualquier `MinioException` (bucket faltante, servidor caído,
    respuesta inválida) que ocurra durante `subir_archivo`, para que el
    caller nunca reciba una excepción cruda del SDK de MinIO -- mismo
    contrato que `CargaExcelError` en `carga_excel.py` para el flujo de
    parseo de maestros."""


class ResultadoSubida(NamedTuple):
    """Los dos campos que `carga_archivo` ya tiene columnas para (Fase 1):
    `ruta_objeto` y `hash_sha256`."""

    ruta_objeto: str
    hash_sha256: str


def _build_client() -> Minio:
    """Cliente MinIO propio de Motored -- nunca importa ni reutiliza el
    cliente global de `app.services.storage_service` (ADR-6)."""
    return Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
    )


def construir_ruta_objeto(tipo: str, carga_id: uuid.UUID, yyyy: str, mm: str) -> str:
    return f"{tipo}/{yyyy}/{mm}/{carga_id}.xlsx"


def subir_archivo(
    carga_id: uuid.UUID,
    tipo: str,
    entrada: BinaryIO,
    ahora: Optional[datetime] = None,
    client: Optional[Minio] = None,
) -> ResultadoSubida:
    """Streamea `entrada` (ya posicionado al inicio) hacia un
    `SpooledTemporaryFile` en lotes de `_CHUNK_SIZE`, calculando un
    `hashlib.sha256` corriente en la MISMA pasada -- nunca lee el archivo
    completo a memoria antes de subirlo. Sube con
    `put_object(length=-1, part_size=_PART_SIZE)`, que delega en el SDK de
    MinIO el streaming multipart.

    `ahora` (default `datetime.now(timezone.utc)`) determina `{yyyy}/{mm}`
    en la key -- parametrizable para que los tests sean deterministas sin
    mockear el reloj global. `client` permite inyectar un `Minio` (real o
    mock) sin tocar `settings`; si se omite, se construye uno propio vía
    `_build_client()`."""
    cliente = client if client is not None else _build_client()
    momento = ahora if ahora is not None else datetime.now(timezone.utc)
    ruta = construir_ruta_objeto(tipo, carga_id, f"{momento:%Y}", f"{momento:%m}")

    hasher = hashlib.sha256()
    try:
        with tempfile.SpooledTemporaryFile(max_size=_PART_SIZE) as buffer:
            while True:
                chunk = entrada.read(_CHUNK_SIZE)
                if not chunk:
                    break
                hasher.update(chunk)
                buffer.write(chunk)
            buffer.seek(0)
            cliente.put_object(
                settings.MOTORED_MINIO_BUCKET,
                ruta,
                buffer,
                length=-1,
                part_size=_PART_SIZE,
            )
    except MinioException as exc:
        raise SubidaArchivoError(f"No se pudo subir el archivo a MinIO: {exc}") from exc

    return ResultadoSubida(ruta_objeto=ruta, hash_sha256=hasher.hexdigest())


class DescargaArchivoError(Exception):
    """Envuelve cualquier `MinioException` (objeto inexistente, servidor
    caído) que ocurra durante `descargar_archivo` -- mismo contrato que
    `SubidaArchivoError`: el caller (Fase 9, `services/ingesta/
    orquestador.py`) nunca recibe una excepción cruda del SDK de MinIO."""


def descargar_archivo(ruta_objeto: str, client: Optional[Minio] = None) -> bytes:
    """Contraparte de lectura de `subir_archivo` (Fase 9, task 9.4): trae de
    vuelta el `.xlsx` ya subido para que el job de dry-run pueda parsearlo.
    A diferencia de la subida (streameada por diseño para un archivo de
    76 MB), acá SÍ se materializa el archivo completo en memoria -- es
    exactamente lo que `services/ingesta/lector.py::leer_lotes` ya espera
    recibir (`file_bytes: bytes`), y el propio lector es quien mantiene
    acotado el uso de memoria fila a fila desde ese punto en adelante."""
    cliente = client if client is not None else _build_client()
    try:
        respuesta = cliente.get_object(settings.MOTORED_MINIO_BUCKET, ruta_objeto)
        try:
            return respuesta.read()
        finally:
            respuesta.close()
            respuesta.release_conn()
    except MinioException as exc:
        raise DescargaArchivoError(f"No se pudo descargar el archivo de MinIO: {exc}") from exc
