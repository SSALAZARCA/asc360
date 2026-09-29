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
import itertools
import logging
from typing import Any, AsyncIterator, List, Optional, Sequence

import openpyxl

from app.config import settings
from app.motored.services.ingesta import columnas as columnas_mod
from app.motored.services.trabajos.supervisor import POOL_INGESTA

logger = logging.getLogger("motored.ingesta.lector")

# Mismo bound que `deteccion._FILAS_MAXIMAS_ESCANEADAS`: el encabezado real
# de un tipo debe aparecer en las primeras filas de su hoja.
_FILAS_ESCANEADAS_POR_HOJA = 20
UMBRAL_HOJA = 0.6


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


def _ratio_de_hoja(hoja, columnas_esperadas: Sequence[str]) -> float:
    filas = itertools.islice(hoja.iter_rows(values_only=True), _FILAS_ESCANEADAS_POR_HOJA)
    return columnas_mod.mejor_ratio_de_encabezado(list(filas), columnas_esperadas)


def elegir_hoja(workbook, columnas_esperadas: Optional[Sequence[str]] = None):
    """Hoja del libro que contiene los datos del tipo declarado: entre las
    hojas cuyo encabezado alcanza el umbral de `columnas.encontrar_fila_
    encabezado` (>= 60% de `columnas_esperadas`), la de MEJOR ratio (la
    hoja de ventas trae 3 de las 4 columnas de inventario, así que "la
    primera que pase el 60%" elegiría la hoja equivocada); a igual ratio,
    la primera. Si hay varias candidatas se registra cuál se usó. Si
    ninguna alcanza el umbral (o no se pasan columnas), se conserva
    `workbook.active`: los mismos errores de tipo/encabezado de siempre.
    Compartida entre el lector y la verificación de tipo de `POST /cargas`
    para que ambos vean la misma hoja."""
    if not columnas_esperadas:
        return workbook.active
    ratios = [(hoja, _ratio_de_hoja(hoja, columnas_esperadas)) for hoja in workbook.worksheets]
    candidatas = [(hoja, ratio) for hoja, ratio in ratios if ratio >= UMBRAL_HOJA]
    if not candidatas:
        return workbook.active
    elegida = max(candidatas, key=lambda par: par[1])[0]
    if len(candidatas) > 1:
        logger.info(
            "Varias hojas coinciden con el tipo declarado (%s); se usa %r.",
            ", ".join(f"{h.title!r}={ratio:.0%}" for h, ratio in candidatas), elegida.title,
        )
    return elegida


class _LectorMovimiento:
    """Envuelve un workbook `openpyxl` abierto en `read_only=True` y expone
    `siguiente_lote(tamano)`/`cerrar()`. TODOS sus métodos son SÍNCRONOS y
    deben correr en `POOL_INGESTA` -- nunca se llaman directamente desde el
    event loop (eso lo garantiza `leer_lotes`, el único punto de entrada
    async del módulo)."""

    def __init__(self, file_bytes: bytes, columnas_esperadas: Optional[Sequence[str]] = None):
        self._workbook = _abrir_workbook(file_bytes)
        hoja = elegir_hoja(self._workbook, columnas_esperadas)
        self._filas_iter = hoja.iter_rows(values_only=True)

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
    file_bytes: bytes,
    tamano_lote: Optional[int] = None,
    columnas_esperadas: Optional[Sequence[str]] = None,
) -> AsyncIterator[List[Sequence[Any]]]:
    """Lee `file_bytes` en `POOL_INGESTA` y produce, lote por lote, listas
    de a lo sumo `tamano_lote` filas (default `settings.MOTORED_INGESTA_
    LOTE`) de la hoja que `elegir_hoja` selecciona para `columnas_esperadas`
    (sin ellas, la hoja activa). Cierra el workbook (también en el executor)
    tanto en el camino feliz como si el consumidor corta la iteración antes
    de agotarla."""
    tamano = tamano_lote if tamano_lote is not None else settings.MOTORED_INGESTA_LOTE
    loop = asyncio.get_event_loop()

    lector_obj = await loop.run_in_executor(
        POOL_INGESTA, _LectorMovimiento, file_bytes, columnas_esperadas
    )
    try:
        while True:
            lote = await loop.run_in_executor(POOL_INGESTA, lector_obj.siguiente_lote, tamano)
            if not lote:
                break
            yield lote
    finally:
        await loop.run_in_executor(POOL_INGESTA, lector_obj.cerrar)
