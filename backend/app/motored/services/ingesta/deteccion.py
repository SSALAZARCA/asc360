"""
Motored Pedidos — Fase 2 "Ingesta", Phase 9 "Adapter + API" (PR9), task 9.4
(sdd/motored-pedidos-ingesta; design "File type detection with manual
override", API "`POST /cargas` ... detecta `tipo` server-side por firma de
encabezado").

Ningún módulo anterior implementaba la detección de `tipo` por firma de
encabezado -- cada transform (`ventas.py`, `inventario.py`, etc.) YA
declara su propio `COLUMNAS_ESPERADAS`, pensado originalmente solo para
`columnas.encontrar_fila_encabezado` DENTRO de un archivo cuyo tipo ya se
conocía (Phase 3+). Este módulo reutiliza esas mismas tuplas como firma de
detección: escanea las primeras filas del archivo y elige, para la PRIMERA
fila donde algún tipo supera el umbral, el tipo con el ratio más alto de
columnas esperadas presentes (spec "detect tipo by header signature").

`MAESTRO_REFERENCIAS`/`MAESTRO_BODEGAS` DELIBERADAMENTE NO tienen firma acá
-- sus columnas obligatorias (`services/carga_excel.py::ALIASES_POR_
ENTIDAD`) son demasiado genéricas (`codigo` es la ÚNICA obligatoria de
`bodega`) para distinguirse con confianza de un archivo de movimiento real;
un falso positivo en cualquier dirección sería peor que pedirle al usuario
que confirme el tipo a mano -- la spec ya cubre exactamente este caso
("Unrecognized headers force manual selection"). Un archivo maestro sube
con `tipo` sin resolver y el usuario lo completa vía `PATCH /cargas/{id}`,
igual que cualquier archivo con encabezados no reconocidos.
"""
from __future__ import annotations

import io
from typing import Any, List, Optional, Sequence, Tuple

import openpyxl

from app.motored.services.ingesta import backorder as backorder_mod
from app.motored.services.ingesta import demanda_perdida as demanda_perdida_mod
from app.motored.services.ingesta import facturas as facturas_mod
from app.motored.services.ingesta import ingresos as ingresos_mod
from app.motored.services.ingesta import inventario as inventario_mod
from app.motored.services.ingesta import ventas as ventas_mod
from app.motored.services.ingesta.lector import LecturaMovimientoError
from app.motored.services.texto import normalizar_encabezado

# Orden = prioridad de desempate cuando dos tipos alcanzan el MISMO ratio en
# la misma fila -- determinístico (spec "a single deterministic type is
# proposed"), nunca depende del orden de iteración de un dict.
_FIRMAS_POR_TIPO: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("VENTAS", ventas_mod.COLUMNAS_ESPERADAS),
    ("INVENTARIO", inventario_mod.COLUMNAS_ESPERADAS),
    ("BACKORDER", backorder_mod.COLUMNAS_ESPERADAS),
    ("FACTURAS_PEDIDOS", facturas_mod.COLUMNAS_ESPERADAS),
    ("INGRESOS_FACTURAS", ingresos_mod.COLUMNAS_ESPERADAS),
    ("DEMANDA_PERDIDA", demanda_perdida_mod.COLUMNAS_ESPERADAS),
)

UMBRAL_DETECCION = 0.6
_FILAS_MAXIMAS_ESCANEADAS = 20


def detectar_tipo(filas_muestra: Sequence[Sequence[Any]]) -> Optional[str]:
    """Escanea a lo sumo las primeras `_FILAS_MAXIMAS_ESCANEADAS` filas de
    `filas_muestra` y retorna el `tipo` cuyo ratio de columnas esperadas
    matcheadas sea el más alto en la PRIMERA fila donde algún tipo supera
    `UMBRAL_DETECCION` -- `None` si ninguna fila escaneada lo logra para
    ningún tipo (spec "Unrecognized headers force manual selection")."""
    for fila in filas_muestra[:_FILAS_MAXIMAS_ESCANEADAS]:
        normalizados_fila = {normalizar_encabezado(v, quitar_separadores=True) for v in fila}
        mejor_tipo: Optional[str] = None
        mejor_ratio = 0.0
        for tipo, columnas_esperadas in _FIRMAS_POR_TIPO:
            normalizados_esperados = {
                normalizar_encabezado(c, quitar_separadores=True) for c in columnas_esperadas
            }
            ratio = len(normalizados_esperados & normalizados_fila) / len(normalizados_esperados)
            if ratio > mejor_ratio:
                mejor_ratio = ratio
                mejor_tipo = tipo
        if mejor_ratio >= UMBRAL_DETECCION:
            return mejor_tipo
    return None


def extraer_filas_muestra(
    file_bytes: bytes, limite: int = _FILAS_MAXIMAS_ESCANEADAS
) -> List[Sequence[Any]]:
    """Lee, SÍNCRONAMENTE, a lo sumo las primeras `limite` filas del archivo
    -- usado por `api/cargas.py` en el request de subida (`POST /cargas`),
    ANTES de que exista ningún `carga_archivo` que un job en background
    pudiera procesar. Deliberadamente NO usa `lector.leer_lotes` (async,
    pensado para streamear TODO el archivo vía `POOL_INGESTA`) -- acá solo
    hace falta un puñado de filas para detectar el tipo, una lectura acotada
    y síncrona es más simple y más barata. Nunca deja escapar una excepción
    cruda de `openpyxl` -- mismo contrato que `lector._abrir_workbook`."""
    try:
        workbook = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
        try:
            filas = []
            for idx, fila in enumerate(workbook.active.iter_rows(values_only=True)):
                if idx >= limite:
                    break
                filas.append(fila)
            return filas
        finally:
            workbook.close()
    except Exception as exc:  # cualquier fallo de openpyxl -> excepción de dominio
        raise LecturaMovimientoError(
            "No se pudo leer el archivo. Verificá que sea un .xlsx válido."
        ) from exc
