"""
Motored Pedidos — Fase 2 "Ingesta", Phase 3 "Movement Schema + Shared Infra"
(sdd/motored-pedidos-ingesta, task 3.2; design §Data Flow, §File Changes,
ADR-1/ADR-2b).

Lector STREAMING de archivos de movimiento: abre el `.xlsx` con `openpyxl`
en `read_only=True` (nunca materializa la hoja completa -- mismo criterio
que `carga_excel.py`) y produce lotes ("lotes") de a lo sumo
`settings.MOTORED_INGESTA_LOTE` (2 000 default) filas, UNO POR VEZ. Cada
lote se lee con una llamada SEPARADA a `run_in_executor(POOL_INGESTA, ...)`
-- el executor dedicado de un solo thread que ya declara
`services/trabajos/supervisor.py` (ADR-1) -- así el event loop recupera el
control entre lote y lote (para que el caller pueda `await
session.execute(...)` sin bloquear) y nunca se acumulan más de un lote de
filas en memoria a la vez, el mismo bound que protege la memoria para un
archivo de ~305 901 filas (design §Risks).

Deliberadamente NO sabe nada de encabezados/columnas -- eso es
`columnas.py` (task 3.3). Este módulo solo entrega filas crudas en lotes;
Fase 4+ es quien compone lector + columnas + resolucion + errores en un
transform real.
"""
from __future__ import annotations

import asyncio
import io
from typing import Any, AsyncIterator, List, Optional, Sequence

import openpyxl

from app.config import settings
from app.motored.services.trabajos.supervisor import POOL_INGESTA


class LecturaMovimientoError(Exception):
    """Envuelve cualquier fallo de `openpyxl` al abrir/leer un archivo de
    movimiento -- mismo contrato que `CargaExcelError`/`SubidaArchivoError`:
    el caller nunca recibe una excepción cruda de una librería de terceros."""


def _abrir_workbook(file_bytes: bytes):
    try:
        return openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
    except Exception as exc:  # cualquier fallo de openpyxl -> excepción de dominio
        raise LecturaMovimientoError(
            "No se pudo leer el archivo. Verificá que sea un .xlsx válido."
        ) from exc


class _LectorMovimiento:
    """Envuelve un workbook `openpyxl` abierto en `read_only=True` y expone
    `siguiente_lote(tamano)`/`cerrar()`. TODOS sus métodos son SÍNCRONOS y
    deben correr en `POOL_INGESTA` -- nunca se llaman directamente desde el
    event loop (eso lo garantiza `leer_lotes`, el único punto de entrada
    async del módulo)."""

    def __init__(self, file_bytes: bytes):
        self._workbook = _abrir_workbook(file_bytes)
        self._filas_iter = self._workbook.active.iter_rows(values_only=True)

    def siguiente_lote(self, tamano: int) -> List[Sequence[Any]]:
        lote: List[Sequence[Any]] = []
        for fila in self._filas_iter:
            lote.append(fila)
            if len(lote) >= tamano:
                break
        return lote

    def cerrar(self) -> None:
        self._workbook.close()


async def leer_lotes(
    file_bytes: bytes, tamano_lote: Optional[int] = None
) -> AsyncIterator[List[Sequence[Any]]]:
    """Lee `file_bytes` en `POOL_INGESTA` y produce, lote por lote, listas
    de a lo sumo `tamano_lote` filas (default `settings.MOTORED_INGESTA_
    LOTE`). Cierra el workbook (también en el executor) tanto en el camino
    feliz como si el consumidor corta la iteración antes de agotarla."""
    tamano = tamano_lote if tamano_lote is not None else settings.MOTORED_INGESTA_LOTE
    loop = asyncio.get_event_loop()

    lector_obj = await loop.run_in_executor(POOL_INGESTA, _LectorMovimiento, file_bytes)
    try:
        while True:
            lote = await loop.run_in_executor(POOL_INGESTA, lector_obj.siguiente_lote, tamano)
            if not lote:
                break
            yield lote
    finally:
        await loop.run_in_executor(POOL_INGESTA, lector_obj.cerrar)
