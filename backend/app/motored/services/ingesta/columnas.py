"""
Motored Pedidos — Fase 2 "Ingesta", Phase 3 "Movement Schema + Shared Infra"
(sdd/motored-pedidos-ingesta, task 3.3; design §Testing Strategy, spec
"Column and date parsing contract for movement files").

Tres responsabilidades puras, sin acceso a base de datos ni al archivo:

1. `encontrar_fila_encabezado`: ubica la fila de encabezado real como la
   primera con >=60% de las columnas esperadas presentes (spec "Header row
   is found past leading title rows") -- los archivos de movimiento suelen
   traer filas de título antes del encabezado real.
2. `construir_mapa_columnas`: mapea por NOMBRE normalizado, nunca por
   posición (spec "columns MUST be mapped by normalized name ... never by
   position").
3. `convertir_fecha_excel`/`FechaExcelImplausibleError`: un serial de Excel
   que convierte a un año fuera de 2015-2100 es SIEMPRE un error, nunca un
   valor silenciosamente aceptado (spec "Implausible converted date is an
   error").

Usa `texto.normalizar_encabezado(..., quitar_separadores=True)` (ADR-7) --
el mismo modo que Fase 2 necesita para encabezados de movimiento como
"Dct.referencia", y que ya incluye el trim requerido por spec ("Space-padded
branch name still matches" aplica al mismo criterio de comparación).
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any, Dict, Sequence

from app.motored.services.texto import normalizar_encabezado

# Época de Excel (con el bug histórico del año bisiesto 1900 incluido, el
# mismo que usa el propio Excel/openpyxl al convertir un serial a fecha).
_EPOCA_EXCEL = date(1899, 12, 30)

_ANIO_MINIMO_PLAUSIBLE = 2015
_ANIO_MAXIMO_PLAUSIBLE = 2100


class EncabezadoNoEncontradoError(Exception):
    """Ninguna fila escaneada alcanza el umbral de match -- el archivo no
    tiene un encabezado reconocible para el tipo esperado."""


class FechaExcelImplausibleError(Exception):
    """El serial convierte a un año fuera de 2015-2100 -- spec 'Implausible
    converted date is an error': nunca se acepta en silencio, la fila se
    rechaza (`carga_error`, no una excepción no manejada hasta el caller)."""


def construir_mapa_columnas(
    fila_encabezado: Sequence[Any], columnas_esperadas: Sequence[str]
) -> Dict[str, int]:
    """Retorna {nombre_esperado_ORIGINAL (tal cual vino en `columnas_
    esperadas`) -> índice_de_columna (0-based)} para cada columna esperada
    presente en `fila_encabezado`. La clave de retorno es la forma legible
    original (p.ej. `"cantidad inv."`), no la forma normalizada
    internamente (`"cantidadinv"`) -- el caller siempre indexa por el
    nombre canónico que declaró, nunca por su forma comprimida. Columnas
    del archivo que no matchean ninguna esperada se ignoran. El primer
    índice que matchea una clave gana si hay duplicados en el encabezado."""
    nombre_original_por_normalizado = {
        normalizar_encabezado(c, quitar_separadores=True): c for c in columnas_esperadas
    }
    mapa: Dict[str, int] = {}
    for idx, valor in enumerate(fila_encabezado):
        clave_normalizada = normalizar_encabezado(valor, quitar_separadores=True)
        nombre_original = nombre_original_por_normalizado.get(clave_normalizada)
        if nombre_original is not None and nombre_original not in mapa:
            mapa[nombre_original] = idx
    return mapa


def _ratio_de_match(fila: Sequence[Any], normalizados_esperados: set) -> float:
    normalizados_fila = {normalizar_encabezado(v, quitar_separadores=True) for v in fila}
    coincidencias = len(normalizados_esperados & normalizados_fila)
    return coincidencias / len(normalizados_esperados)


def encontrar_fila_encabezado(
    filas: Sequence[Sequence[Any]], columnas_esperadas: Sequence[str], umbral: float = 0.6
) -> int:
    """Escanea `filas` en orden y retorna el índice (0-based) de la PRIMERA
    fila cuyo ratio de columnas esperadas presentes es >= `umbral` (default
    60%, spec). Filas de título/vacías antes del encabezado real quedan
    naturalmente por debajo del umbral y se saltean. Lanza
    `EncabezadoNoEncontradoError` si ninguna fila alcanza el umbral."""
    normalizados_esperados = {
        normalizar_encabezado(c, quitar_separadores=True) for c in columnas_esperadas
    }
    if not normalizados_esperados:
        raise EncabezadoNoEncontradoError("No hay columnas esperadas para buscar un encabezado.")

    for idx, fila in enumerate(filas):
        if _ratio_de_match(fila, normalizados_esperados) >= umbral:
            return idx

    raise EncabezadoNoEncontradoError(
        f"No se encontró una fila de encabezado con al menos "
        f"{umbral:.0%} de las columnas esperadas."
    )


def convertir_fecha_excel(valor_serial: float) -> date:
    """Convierte un serial numérico de Excel a `date`, rechazando cualquier
    resultado fuera de 2015-2100 (spec). `math.trunc` en vez de `int()`
    directo sobre negativos no es una preocupación acá -- un serial
    negativo ya cae muy por debajo de 2015 y se rechaza igual."""
    dias = math.trunc(valor_serial)
    fecha = _EPOCA_EXCEL + timedelta(days=dias)
    if not (_ANIO_MINIMO_PLAUSIBLE <= fecha.year <= _ANIO_MAXIMO_PLAUSIBLE):
        raise FechaExcelImplausibleError(
            f"Fecha implausible: el serial {valor_serial} convierte a {fecha.isoformat()}, "
            f"fuera del rango {_ANIO_MINIMO_PLAUSIBLE}-{_ANIO_MAXIMO_PLAUSIBLE}."
        )
    return fecha
