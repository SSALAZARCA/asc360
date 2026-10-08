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

`ALIAS_COLUMNAS` lists other header names accepted for an expected column
(owner decision, 2026-10-08: the ERP export of "Ingresos de facturas" says
"Docto. referencia" where the template says "Dct.referencia"). The alias
only counts for a type that expects the canonical column, and the
canonical name wins when a header carries both.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from app.motored.services.texto import normalizar_encabezado

# Época de Excel (con el bug histórico del año bisiesto 1900 incluido, el
# mismo que usa el propio Excel/openpyxl al convertir un serial a fecha).
_EPOCA_EXCEL = date(1899, 12, 30)

_ANIO_MINIMO_PLAUSIBLE = 2015
_ANIO_MAXIMO_PLAUSIBLE = 2100

# Canonical expected column -> other header names that mean the same.
ALIAS_COLUMNAS: Dict[str, Tuple[str, ...]] = {
    "Dct.referencia": ("Docto. referencia",),
}


class EncabezadoNoEncontradoError(Exception):
    """Ninguna fila escaneada alcanza el umbral de match -- el archivo no
    tiene un encabezado reconocible para el tipo esperado."""


class EncabezadoDuplicadoError(Exception):
    """Una columna esperada aparece más de una vez en el encabezado: no hay
    forma de saber cuál es la buena, así que el archivo completo se rechaza
    (nunca se toma "la primera" en silencio). `columnas` lista los nombres
    canónicos duplicados."""

    def __init__(self, columnas: Sequence[str]):
        self.columnas = list(columnas)
        super().__init__(
            "El encabezado tiene columnas duplicadas: "
            f"{', '.join(self.columnas)}. "
            "Dejá una sola columna de cada una y volvé a cargar el archivo."
        )


class FechaExcelImplausibleError(Exception):
    """El serial convierte a un año fuera de 2015-2100 -- spec 'Implausible
    converted date is an error': nunca se acepta en silencio, la fila se
    rechaza (`carga_error`, no una excepción no manejada hasta el caller)."""


def _normalizar(valor: Any) -> str:
    return normalizar_encabezado(valor, quitar_separadores=True)


def formas_aceptadas(columna: str) -> Set[str]:
    """Normalized header forms accepted for the expected `columna`: its own
    name plus its `ALIAS_COLUMNAS` entries."""
    nombres = (columna, *ALIAS_COLUMNAS.get(columna, ()))
    return {_normalizar(nombre) for nombre in nombres}


def columnas_presentes(
    fila: Sequence[Any], columnas_esperadas: Sequence[str]
) -> List[str]:
    """Expected columns (canonical names, in their declared order) found in
    `fila` under their own name or an alias."""
    normalizados_fila = {_normalizar(v) for v in fila}
    return [
        c for c in columnas_esperadas
        if formas_aceptadas(c) & normalizados_fila
    ]


def _indices_por_forma(
    fila_encabezado: Sequence[Any],
) -> Dict[str, List[int]]:
    indices: Dict[str, List[int]] = {}
    for idx, valor in enumerate(fila_encabezado):
        indices.setdefault(_normalizar(valor), []).append(idx)
    return indices


def construir_mapa_columnas(
    fila_encabezado: Sequence[Any], columnas_esperadas: Sequence[str]
) -> Dict[str, int]:
    """Retorna {nombre_esperado_ORIGINAL (tal cual vino en `columnas_
    esperadas`) -> índice_de_columna (0-based)} para cada columna esperada
    presente en `fila_encabezado`. La clave de retorno es la forma legible
    original (p.ej. `"cantidad inv."`), no la forma normalizada
    internamente (`"cantidadinv"`) -- el caller siempre indexa por el
    nombre canónico que declaró, nunca por su forma comprimida. Columnas
    del archivo que no matchean ninguna esperada se ignoran. Una columna
    esperada sin su nombre propio se busca por sus `ALIAS_COLUMNAS`. Una
    columna ESPERADA repetida en el encabezado (bajo el mismo nombre)
    lanza `EncabezadoDuplicadoError`; duplicados de columnas no esperadas
    se ignoran."""
    indices = _indices_por_forma(fila_encabezado)
    mapa: Dict[str, int] = {}
    duplicadas: List[str] = []
    for columna in columnas_esperadas:
        nombres = (columna, *ALIAS_COLUMNAS.get(columna, ()))
        for nombre in nombres:
            encontrados = indices.get(_normalizar(nombre), [])
            if not encontrados:
                continue
            mapa[columna] = encontrados[0]
            if len(encontrados) > 1 and columna not in duplicadas:
                duplicadas.append(columna)
            break
    if duplicadas:
        raise EncabezadoDuplicadoError(duplicadas)
    return mapa


def _ratio_de_match(
    fila: Sequence[Any], columnas_esperadas: Sequence[str]
) -> float:
    presentes = columnas_presentes(fila, columnas_esperadas)
    return len(presentes) / len(columnas_esperadas)


def mejor_ratio_de_encabezado(
    filas: Sequence[Sequence[Any]], columnas_esperadas: Sequence[str]
) -> float:
    """Mayor ratio de columnas esperadas presentes entre `filas` (0.0 si no
    hay filas o columnas). Sirve para comparar QUÉ tan bien encaja cada hoja
    de un libro con un tipo: una hoja de VENTAS trae 3 de las 4 columnas de
    INVENTARIO (75%), pero solo la hoja de inventario las trae todas."""
    if not columnas_esperadas:
        return 0.0
    return max(
        (_ratio_de_match(fila, columnas_esperadas) for fila in filas),
        default=0.0,
    )


def encontrar_fila_encabezado(
    filas: Sequence[Sequence[Any]],
    columnas_esperadas: Sequence[str],
    umbral: float = 0.6,
) -> int:
    """Escanea `filas` en orden y retorna el índice (0-based) de la PRIMERA
    fila cuyo ratio de columnas esperadas presentes es >= `umbral` (default
    60%, spec). Filas de título/vacías antes del encabezado real quedan
    naturalmente por debajo del umbral y se saltean. Lanza
    `EncabezadoNoEncontradoError` si ninguna fila alcanza el umbral."""
    if not columnas_esperadas:
        raise EncabezadoNoEncontradoError(
            "No hay columnas esperadas para buscar un encabezado."
        )

    for idx, fila in enumerate(filas):
        if _ratio_de_match(fila, columnas_esperadas) >= umbral:
            return idx

    raise EncabezadoNoEncontradoError(
        f"No se encontró una fila de encabezado con al menos "
        f"{umbral:.0%} de las columnas esperadas."
    )


def a_fecha(valor: Any) -> Optional[date]:
    """Normaliza una celda de fecha a un `date` PURO: openpyxl (`data_only=
    True`) entrega `datetime` (subclase de `date`) para una celda con formato
    de fecha, y su `isoformat()` ("2026-07-15T00:00:00") no se puede volver a
    leer con `date.fromisoformat` al aplicar. Cualquier otro valor -> `None`.
    Único punto donde las transforms convierten una celda a fecha."""
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    return None


def anio_es_plausible(anio: int) -> bool:
    """Mismo umbral 2015-2100 que `convertir_fecha_excel`, expuesto para que
    un caller que YA tiene un `date`/`datetime` (openpyxl con `data_only=
    True` convierte una celda con formato de fecha directamente, sin pasar
    por un serial -- ver `services/ingesta/ventas.py::_resolver_fecha`,
    confirmado contra el workbook real de producción) no tenga que
    reinventar el rango."""
    return _ANIO_MINIMO_PLAUSIBLE <= anio <= _ANIO_MAXIMO_PLAUSIBLE


def convertir_fecha_excel(valor_serial: float) -> date:
    """Convierte un serial numérico de Excel a `date`, rechazando cualquier
    resultado fuera de 2015-2100 (spec). `math.trunc` en vez de `int()`
    directo sobre negativos no es una preocupación acá -- un serial
    negativo ya cae muy por debajo de 2015 y se rechaza igual."""
    dias = math.trunc(valor_serial)
    fecha = _EPOCA_EXCEL + timedelta(days=dias)
    if not anio_es_plausible(fecha.year):
        raise FechaExcelImplausibleError(
            f"Fecha implausible: el serial {valor_serial} convierte a "
            f"{fecha.isoformat()}, fuera del rango "
            f"{_ANIO_MINIMO_PLAUSIBLE}-{_ANIO_MAXIMO_PLAUSIBLE}."
        )
    return fecha
