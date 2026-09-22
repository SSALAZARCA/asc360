"""
Fase 2 "Ingesta", Phase 3 "Movement Schema + Shared Infra" (sdd/motored-
pedidos-ingesta, task 3.2) — `services/ingesta/lector.py`.

Streaming genuino: `leer_lotes` nunca materializa el archivo completo en
memoria de una sola vez -- cada lote se lee con una llamada SEPARADA a
`POOL_INGESTA` (el executor dedicado de un solo thread que ya declara
`services/trabajos/supervisor.py`, ADR-1), cediendo el control al event
loop entre lote y lote. Sin Postgres real: fixtures `.xlsx` generadas en
memoria con `openpyxl`.
"""
import io
import threading

import openpyxl
import pytest

from app.motored.services.ingesta import lector


def _build_xlsx_bytes(filas: list) -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    for fila in filas:
        sheet.append(fila)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


async def test_leer_lotes_splits_rows_into_batches_of_the_requested_size():
    file_bytes = _build_xlsx_bytes([[f"fila{i}"] for i in range(5)])

    lotes = [lote async for lote in lector.leer_lotes(file_bytes, tamano_lote=2)]

    assert [len(lote) for lote in lotes] == [2, 2, 1]


async def test_leer_lotes_preserves_row_order_and_values():
    file_bytes = _build_xlsx_bytes([["a", 1], ["b", 2], ["c", 3]])

    lotes = [lote async for lote in lector.leer_lotes(file_bytes, tamano_lote=2)]

    todas_las_filas = [fila for lote in lotes for fila in lote]
    assert todas_las_filas == [("a", 1), ("b", 2), ("c", 3)]


async def test_leer_lotes_defaults_to_configured_lote_size(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "MOTORED_INGESTA_LOTE", 3)
    file_bytes = _build_xlsx_bytes([[i] for i in range(7)])

    lotes = [lote async for lote in lector.leer_lotes(file_bytes)]

    assert [len(lote) for lote in lotes] == [3, 3, 1]


async def test_leer_lotes_on_empty_sheet_yields_nothing():
    file_bytes = _build_xlsx_bytes([])

    lotes = [lote async for lote in lector.leer_lotes(file_bytes, tamano_lote=2)]

    assert lotes == []


async def test_leer_lotes_runs_the_blocking_read_on_the_dedicated_ingesta_thread():
    file_bytes = _build_xlsx_bytes([[i] for i in range(4)])
    thread_names = []

    class _LectorInstrumentado(lector._LectorMovimiento):
        def siguiente_lote(self, tamano):
            thread_names.append(threading.current_thread().name)
            return super().siguiente_lote(tamano)

    import app.motored.services.ingesta.lector as lector_module

    original = lector_module._LectorMovimiento
    lector_module._LectorMovimiento = _LectorInstrumentado
    try:
        [lote async for lote in lector.leer_lotes(file_bytes, tamano_lote=2)]
    finally:
        lector_module._LectorMovimiento = original

    assert thread_names
    assert all(name.startswith("motored-ingesta") for name in thread_names)


async def test_leer_lotes_wraps_openpyxl_failures_in_a_domain_exception():
    with pytest.raises(lector.LecturaMovimientoError):
        [lote async for lote in lector.leer_lotes(b"no es un xlsx valido", tamano_lote=2)]
