"""
Motored Pedidos — Ingesta: plantillas `.xlsx` de los 6 tipos de movimiento.

El encabezado de cada plantilla sale de las MISMAS columnas que el backend
usa para verificar y leer un archivo subido (`COLUMNAS_ESPERADAS` de cada
transform, más las `COLUMNAS_OPCIONALES` de BACKORDER), así que una
plantilla descargada nunca puede desalinearse de lo que el backend acepta:
única fuente de verdad, sin copia en el frontend.
"""
from __future__ import annotations

import io
from typing import Tuple

from openpyxl import Workbook

from app.motored.services.ingesta import deteccion


def columnas_plantilla(tipo: str) -> Tuple[str, ...]:
    """Columnas obligatorias del `tipo` seguidas de las opcionales (p.ej.
    `Fecha Creación` de BACKORDER). `KeyError` si `tipo` no es uno de los 6
    tipos de movimiento."""
    opcionales = deteccion.COLUMNAS_OPCIONALES_POR_TIPO.get(tipo, ())
    return deteccion.columnas_esperadas_de(tipo) + opcionales


def generar_plantilla_xlsx(tipo: str) -> bytes:
    """`.xlsx` de una sola hoja con el encabezado del `tipo` en la fila 1."""
    workbook = Workbook()
    workbook.active.append(list(columnas_plantilla(tipo)))
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
