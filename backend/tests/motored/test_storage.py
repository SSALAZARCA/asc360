"""
Motored Pedidos — Fase 2 "Ingesta" (sdd/motored-pedidos-ingesta, ADR-6).

Tests para `services/storage.py`, el wrapper de MinIO. No hay un servidor
MinIO real disponible en la suite -- se mockea el cliente `Minio` mismo
(pasado explícitamente via el parámetro `client`), siguiendo el patrón
"mockear el cliente" porque el repo no tiene un precedente propio de mock
de MinIO a nivel de test unitario (los tests existentes de otras
features -- ej. `tests/orders/test_evidence_photo_download.py` -- mockean
la función de más alto nivel del servicio invocante, no el cliente MinIO en
sí).
"""
import hashlib
import inspect
import io
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from minio.error import ServerError

from app.config import settings
from app.motored.services import storage


def test_construir_ruta_objeto_matches_the_designed_convention():
    carga_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    ruta = storage.construir_ruta_objeto("VENTAS", carga_id, "2026", "09")
    assert ruta == f"VENTAS/2026/09/{carga_id}.xlsx"


def test_subir_archivo_computes_sha256_matching_hashlib_on_a_known_input():
    contenido = b"contenido-de-prueba-" * 1000
    esperado = hashlib.sha256(contenido).hexdigest()
    mock_client = MagicMock()
    carga_id = uuid.uuid4()

    resultado = storage.subir_archivo(
        carga_id=carga_id,
        tipo="VENTAS",
        entrada=io.BytesIO(contenido),
        ahora=datetime(2026, 9, 21, tzinfo=timezone.utc),
        client=mock_client,
    )

    assert resultado.hash_sha256 == esperado
    assert resultado.ruta_objeto == f"VENTAS/2026/09/{carga_id}.xlsx"


def test_subir_archivo_calls_put_object_with_bucket_key_and_streaming_params():
    contenido = b"x" * 500
    mock_client = MagicMock()
    carga_id = uuid.uuid4()

    storage.subir_archivo(
        carga_id=carga_id,
        tipo="INVENTARIO",
        entrada=io.BytesIO(contenido),
        ahora=datetime(2026, 1, 5, tzinfo=timezone.utc),
        client=mock_client,
    )

    mock_client.put_object.assert_called_once()
    args, kwargs = mock_client.put_object.call_args
    assert args[0] == settings.MOTORED_MINIO_BUCKET
    assert args[1] == f"INVENTARIO/2026/01/{carga_id}.xlsx"
    assert kwargs["length"] == -1
    assert kwargs["part_size"] == 10 * 1024 * 1024


def test_subir_archivo_reads_in_bounded_chunks_never_the_whole_file_at_once():
    """Guard contra bufferear el archivo completo en memoria (el caso real
    citado por el diseño: un archivo de producción de 76 MB)."""
    contenido = b"y" * (storage._CHUNK_SIZE * 3 + 10)
    reader = io.BytesIO(contenido)
    original_read = reader.read
    calls = []

    def tracked_read(size=-1):
        calls.append(size)
        return original_read(size)

    reader.read = tracked_read
    mock_client = MagicMock()

    storage.subir_archivo(
        carga_id=uuid.uuid4(),
        tipo="VENTAS",
        entrada=reader,
        ahora=datetime(2026, 1, 1, tzinfo=timezone.utc),
        client=mock_client,
    )

    assert len(calls) > 1
    assert all(size == storage._CHUNK_SIZE for size in calls[:-1])


def test_build_client_uses_settings_with_no_hardcoded_secret_default(monkeypatch):
    captured = {}

    class FakeMinio:
        def __init__(self, endpoint, access_key, secret_key, secure):
            captured.update(endpoint=endpoint, access_key=access_key, secret_key=secret_key, secure=secure)

    monkeypatch.setattr(storage, "Minio", FakeMinio)

    client = storage._build_client()

    assert captured["endpoint"] == settings.MINIO_ENDPOINT
    assert captured["access_key"] == settings.MINIO_ACCESS_KEY
    assert captured["secret_key"] == settings.MINIO_SECRET_KEY
    assert captured["secure"] == settings.MINIO_SECURE
    assert isinstance(client, FakeMinio)


def test_subir_archivo_wraps_minio_errors_in_a_domain_exception():
    """Un `MinioException` (servidor caído, bucket faltante, respuesta
    inválida) nunca debe propagar crudo fuera de `subir_archivo` -- mismo
    contrato que `CargaExcelError` en `carga_excel.py`."""
    mock_client = MagicMock()
    mock_client.put_object.side_effect = ServerError("servicio no disponible", 503)

    with pytest.raises(storage.SubidaArchivoError):
        storage.subir_archivo(
            carga_id=uuid.uuid4(),
            tipo="VENTAS",
            entrada=io.BytesIO(b"contenido"),
            ahora=datetime(2026, 9, 21, tzinfo=timezone.utc),
            client=mock_client,
        )


def test_module_does_not_import_storage_service_or_hardcode_a_secret_default():
    """ADR-6: `services/storage_service.py` lee env directo con defaults
    hardcodeados (ej. un literal 'umadmin123') -- inaceptable bajo la
    restricción de esta fase. Guard contra reintroducir ese patrón: ningún
    `import`/`from` real de `storage_service` (mencionarlo en un docstring
    explicando por qué NO se usa es intencional y no debe fallar este
    guard), y ningún literal de credencial hardcodeado."""
    source = inspect.getsource(storage)
    import_lines = [line.strip() for line in source.splitlines() if line.strip().startswith(("import ", "from "))]
    assert not any("storage_service" in line for line in import_lines)
    assert "umadmin123" not in source
