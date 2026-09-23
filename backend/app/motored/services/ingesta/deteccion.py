"""
Motored Pedidos — Fase 3 "Cargas: Tipo Declarado" (sdd/motored-cargas-tipo-
declarado; design D1 "`_verificar_tipo_o_400` shape").

Hasta este cambio, este módulo era un DETECTOR: escaneaba las primeras filas
de un archivo y elegía, sin que nadie lo pidiera, cuál de 6 tipos de
movimiento era (spec previa "detect tipo by header signature", `sdd/
motored-pedidos-ingesta`). El owner revirtió esa parte de la decisión #4 de
esa spec (ver `sdd/motored-cargas-tipo-declarado/proposal`, decisión #1):
`tipo` ahora lo DECLARA la pestaña que inició la subida, nunca se infiere.

Este módulo pasa de "¿cuál de los 6 es?" a "¿el archivo efectivamente ES el
tipo declarado?" -- misma matemática de firma (`_FIRMAS_POR_TIPO`,
`UMBRAL_DETECCION`, muestreo acotado de filas vía `extraer_filas_muestra`,
sin cambios), pero la decisión ahora es SÍ/NO sobre UN tipo, nunca "cuál"
entre varios -- por eso `_FIRMAS_POR_TIPO` pasó de tupla-con-orden-de-
desempate a diccionario keyed por tipo: ya no hace falta desempatar entre
tipos que compiten por el mismo archivo, cada `POST /cargas` solo evalúa el
tipo que el caller declaró.

`MAESTRO_REFERENCIAS`/`MAESTRO_BODEGAS` siguen sin firma acá -- desde este
cambio son estructuralmente irrecibibles en `POST /cargas` (ver `api/
cargas.py`, allow-list contra `orquestador.TIPOS_MOVIMIENTO`), así que nunca
llegan a declararse como `tipo_declarado` acá.
"""
from __future__ import annotations

import io
from typing import Any, Dict, List, Sequence, Tuple

import openpyxl

from app.motored.services.ingesta import backorder as backorder_mod
from app.motored.services.ingesta import demanda_perdida as demanda_perdida_mod
from app.motored.services.ingesta import facturas as facturas_mod
from app.motored.services.ingesta import ingresos as ingresos_mod
from app.motored.services.ingesta import inventario as inventario_mod
from app.motored.services.ingesta import ventas as ventas_mod
from app.motored.services.ingesta.lector import LecturaMovimientoError
from app.motored.services.texto import normalizar_encabezado

_FIRMAS_POR_TIPO: Dict[str, Tuple[str, ...]] = {
    "VENTAS": ventas_mod.COLUMNAS_ESPERADAS,
    "INVENTARIO": inventario_mod.COLUMNAS_ESPERADAS,
    "BACKORDER": backorder_mod.COLUMNAS_ESPERADAS,
    "FACTURAS_PEDIDOS": facturas_mod.COLUMNAS_ESPERADAS,
    "INGRESOS_FACTURAS": ingresos_mod.COLUMNAS_ESPERADAS,
    "DEMANDA_PERDIDA": demanda_perdida_mod.COLUMNAS_ESPERADAS,
}

UMBRAL_DETECCION = 0.6
_FILAS_MAXIMAS_ESCANEADAS = 20


class TipoNoCoincideError(Exception):
    """El archivo no verifica contra `tipo_declarado`. Distingue los dos
    casos que la spec exige poder diferenciar en el mensaje (spec "No-
    match-at-all is distinguishable from wrong-type mismatch"):

    - `sin_coincidencia=True`: NINGUNA fila escaneada matcheó ni una sola
      columna esperada del tipo declarado (ratio 0 en todas) -- el archivo
      no se parece a nada conocido. `columnas_faltantes` queda vacía: no
      hay una "mejor fila" de la cual reportar faltantes específicos.
    - `sin_coincidencia=False`: alguna fila SÍ tuvo columnas en común, pero
      el mejor ratio encontrado quedó debajo de `UMBRAL_DETECCION` -- el
      caso típico es "este archivo es de OTRO tipo de movimiento".
      `columnas_faltantes` nombra, de la fila con mejor ratio, qué columnas
      esperadas del tipo declarado NO aparecieron."""

    def __init__(self, tipo_declarado: str, sin_coincidencia: bool, columnas_faltantes: Sequence[str]):
        self.tipo_declarado = tipo_declarado
        self.sin_coincidencia = sin_coincidencia
        self.columnas_faltantes = list(columnas_faltantes)
        if sin_coincidencia:
            mensaje = (
                f"El archivo no se parece a ningún tipo de movimiento conocido "
                f"(se declaró {tipo_declarado})."
            )
        else:
            mensaje = (
                f"El archivo no coincide con el tipo declarado ({tipo_declarado}). "
                f"Faltan columnas: {', '.join(self.columnas_faltantes)}."
            )
        super().__init__(mensaje)


def verificar_tipo(tipo_declarado: str, filas_muestra: Sequence[Sequence[Any]]) -> None:
    """Levanta `TipoNoCoincideError` si `filas_muestra` no verifica contra
    `tipo_declarado`; no retorna nada si sí verifica. Escanea a lo sumo las
    primeras `_FILAS_MAXIMAS_ESCANEADAS` filas (idéntico bound al `detectar_
    tipo` original) y acepta apenas UNA fila alcance `UMBRAL_DETECCION` --
    no hace falta que sea la primera, archivos reales a veces traen una
    fila de título/metadata antes del encabezado real.

    `tipo_declarado` DEBE ser una de las claves de `_FIRMAS_POR_TIPO` -- el
    allow-list de `api/cargas.py::subir_carga` ya lo garantiza antes de
    llamar acá; un valor fuera de esas 6 claves es un error de programación
    (`KeyError`), no un caso de negocio que este módulo deba manejar."""
    columnas_esperadas = _FIRMAS_POR_TIPO[tipo_declarado]
    normalizados_esperados: Dict[str, str] = {
        normalizar_encabezado(c, quitar_separadores=True): c for c in columnas_esperadas
    }

    mejor_ratio = 0.0
    mejor_faltantes: List[str] = list(columnas_esperadas)
    for fila in filas_muestra[:_FILAS_MAXIMAS_ESCANEADAS]:
        normalizados_fila = {normalizar_encabezado(v, quitar_separadores=True) for v in fila}
        coincidencias = set(normalizados_esperados) & normalizados_fila
        ratio = len(coincidencias) / len(normalizados_esperados)
        if ratio > mejor_ratio:
            mejor_ratio = ratio
            mejor_faltantes = [
                original
                for normalizado, original in normalizados_esperados.items()
                if normalizado not in coincidencias
            ]
        if mejor_ratio >= UMBRAL_DETECCION:
            return

    if mejor_ratio == 0.0:
        raise TipoNoCoincideError(tipo_declarado, sin_coincidencia=True, columnas_faltantes=[])
    raise TipoNoCoincideError(
        tipo_declarado, sin_coincidencia=False, columnas_faltantes=mejor_faltantes
    )


def extraer_filas_muestra(
    file_bytes: bytes, limite: int = _FILAS_MAXIMAS_ESCANEADAS
) -> List[Sequence[Any]]:
    """Lee, SÍNCRONAMENTE, a lo sumo las primeras `limite` filas del archivo
    -- usado por `api/cargas.py` en el request de subida (`POST /cargas`),
    ANTES de que exista ningún `carga_archivo` que un job en background
    pudiera procesar. Deliberadamente NO usa `lector.leer_lotes` (async,
    pensado para streamear TODO el archivo vía `POOL_INGESTA`) -- acá solo
    hace falta un puñado de filas para verificar el tipo, una lectura
    acotada y síncrona es más simple y más barata. Nunca deja escapar una
    excepción cruda de `openpyxl` -- mismo contrato que `lector._abrir_
    workbook`. Sin cambios de comportamiento en este cutover (compartida
    entre detección y verificación)."""
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
