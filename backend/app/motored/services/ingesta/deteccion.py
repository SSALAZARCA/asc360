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
from typing import Any, Dict, List, Optional, Sequence, Tuple

import openpyxl

from app.motored.services.ingesta import backorder as backorder_mod
from app.motored.services.ingesta import columnas as columnas_mod
from app.motored.services.ingesta import demanda_perdida as demanda_perdida_mod
from app.motored.services.ingesta import facturas as facturas_mod
from app.motored.services.ingesta import ingresos as ingresos_mod
from app.motored.services.ingesta import inventario as inventario_mod
from app.motored.services.ingesta import ventas as ventas_mod
from app.motored.services.ingesta.lector import (
    LecturaMovimientoError, elegir_hoja,
)

_FIRMAS_POR_TIPO: Dict[str, Tuple[str, ...]] = {
    "VENTAS": ventas_mod.COLUMNAS_ESPERADAS,
    "INVENTARIO": inventario_mod.COLUMNAS_ESPERADAS,
    "BACKORDER": backorder_mod.COLUMNAS_ESPERADAS,
    "FACTURAS_PEDIDOS": facturas_mod.COLUMNAS_ESPERADAS,
    "INGRESOS_FACTURAS": ingresos_mod.COLUMNAS_ESPERADAS,
    "DEMANDA_PERDIDA": demanda_perdida_mod.COLUMNAS_ESPERADAS,
}

# Columnas que un tipo puede traer pero no exige (`orquestador` no aborta si
# faltan; `plantillas` las agrega al encabezado). Única definición.
COLUMNAS_OPCIONALES_POR_TIPO: Dict[str, Tuple[str, ...]] = {
    "VENTAS": ventas_mod.COLUMNAS_OPCIONALES,
    "BACKORDER": backorder_mod.COLUMNAS_OPCIONALES,
    "FACTURAS_PEDIDOS": facturas_mod.COLUMNAS_OPCIONALES,
}

# Tab names exactly as the UI shows them (`frontend/components/motored/
# cargas/tiposCarga.js`), for the wrong-tab message.
ETIQUETAS_TIPO: Dict[str, str] = {
    "VENTAS": "Ventas",
    "INVENTARIO": "Inventario",
    "BACKORDER": "Backorder",
    "DEMANDA_PERDIDA": "Demanda perdida",
    "FACTURAS_PEDIDOS": "Facturas de pedidos",
    "INGRESOS_FACTURAS": "Ingresos de facturas",
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

    def __init__(
        self,
        tipo_declarado: str,
        sin_coincidencia: bool,
        columnas_faltantes: Sequence[str],
    ):
        self.tipo_declarado = tipo_declarado
        self.sin_coincidencia = sin_coincidencia
        self.columnas_faltantes = list(columnas_faltantes)
        if sin_coincidencia:
            mensaje = (
                "El archivo no se parece a ningún tipo de movimiento "
                f"conocido (se declaró {tipo_declarado})."
            )
        else:
            mensaje = (
                "El archivo no coincide con el tipo declarado "
                f"({tipo_declarado}). Faltan columnas: "
                f"{', '.join(self.columnas_faltantes)}."
            )
        super().__init__(mensaje)

    def mensaje_para_usuario(self) -> str:
        """Spanish message for the uploader: names the tab (as the UI
        labels it) and what the file lacks, and suggests another tab."""
        pestana = ETIQUETAS_TIPO.get(
            self.tipo_declarado, self.tipo_declarado
        )
        if self.sin_coincidencia:
            esperadas = ", ".join(_FIRMAS_POR_TIPO.get(
                self.tipo_declarado, ()
            ))
            falta = f"no tiene ninguna de sus columnas ({esperadas})"
        else:
            faltantes = ", ".join(self.columnas_faltantes)
            falta = f"le faltan las columnas {faltantes}"
        return (
            f"Este archivo no parece de {pestana}: {falta}. "
            "¿Lo quiso subir en otra pestaña?"
        )


def verificar_tipo(
    tipo_declarado: str, filas_muestra: Sequence[Sequence[Any]]
) -> None:
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

    mejor_ratio = 0.0
    mejor_faltantes: List[str] = list(columnas_esperadas)
    for fila in filas_muestra[:_FILAS_MAXIMAS_ESCANEADAS]:
        presentes = columnas_mod.columnas_presentes(fila, columnas_esperadas)
        ratio = len(presentes) / len(columnas_esperadas)
        if ratio > mejor_ratio:
            mejor_ratio = ratio
            mejor_faltantes = [
                c for c in columnas_esperadas if c not in presentes
            ]
        if mejor_ratio >= UMBRAL_DETECCION:
            return

    if mejor_ratio == 0.0:
        raise TipoNoCoincideError(
            tipo_declarado, sin_coincidencia=True, columnas_faltantes=[]
        )
    raise TipoNoCoincideError(
        tipo_declarado, sin_coincidencia=False,
        columnas_faltantes=mejor_faltantes,
    )


def columnas_esperadas_de(tipo: str) -> Tuple[str, ...]:
    """Columnas esperadas del `tipo` declarado (mismo `KeyError` que
    `verificar_tipo` para un tipo fuera de las 6 claves)."""
    return _FIRMAS_POR_TIPO[tipo]


def extraer_filas_muestra(
    file_bytes: bytes,
    limite: int = _FILAS_MAXIMAS_ESCANEADAS,
    columnas_esperadas: Optional[Sequence[str]] = None,
) -> List[Sequence[Any]]:
    """Lee, SÍNCRONAMENTE, a lo sumo las primeras `limite` filas de la hoja
    que `lector.elegir_hoja` selecciona para `columnas_esperadas` (sin
    ellas, la hoja activa). Usado por `api/cargas.py` en el request de
    subida (`POST /cargas`), ANTES de que exista ningún `carga_archivo` que
    un job en background pudiera procesar. Deliberadamente NO usa
    `lector.leer_lotes` (async, pensado para streamear TODO el archivo vía
    `POOL_INGESTA`) -- acá solo hace falta un puñado de filas para
    verificar el tipo, una lectura acotada y síncrona es más simple y más
    barata. Nunca deja escapar una excepción cruda de `openpyxl` -- mismo
    contrato que `lector._abrir_workbook`."""
    try:
        workbook = openpyxl.load_workbook(
            io.BytesIO(file_bytes), data_only=True, read_only=True
        )
        try:
            filas = []
            hoja = elegir_hoja(workbook, columnas_esperadas)
            for idx, fila in enumerate(hoja.iter_rows(values_only=True)):
                if idx >= limite:
                    break
                filas.append(fila)
            return filas
        finally:
            workbook.close()
    except Exception as exc:
        # Cualquier fallo de openpyxl -> excepción de dominio.
        raise LecturaMovimientoError(
            "No se pudo leer el archivo. Verificá que sea un .xlsx válido."
        ) from exc
