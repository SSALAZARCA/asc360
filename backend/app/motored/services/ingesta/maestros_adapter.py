"""
Motored Pedidos — Fase 2 "Ingesta", Phase 9 "Adapter + API" (PR9), task 9.1
(sdd/motored-pedidos-ingesta; design ADR-5, spec "Bulk Excel upload is
all-or-nothing" / "carga_error model and CSV export").

ADR-5: los tipos `MAESTRO_*` (`MAESTRO_REFERENCIAS`, `MAESTRO_BODEGAS`) NO
se re-implementan como pipeline tolerante -- se enrutan, SIN MODIFICAR NADA,
a la misma cadena todo-o-nada de Fase 1 (`carga_excel.parse_excel_rows` +
`carga.procesar_carga`/`validators.validate_rows`), que sigue siendo la
única fuente de verdad para esa política de ejecución (owner decision #1,
Fase 1). Esta capa es delgada A PROPÓSITO: no valida nada por su cuenta, no
agrega tolerancia por-fila, y no expone ninguna de las affordances del
camino tolerante de movimientos (batch "crear referencia", aplicar
parcial) -- esas quedan deshabilitadas del lado servidor para `MAESTRO_*`,
nunca simplemente ocultas en la UI (ADR-5: "Tolerant-only affordances ...
are disabled server-side for MAESTRO_*, not merely hidden").

Lo único que este módulo agrega sobre Fase 1: espeja `CargaResultado.
errores` (que hoy sólo vive en memoria, como respuesta HTTP) hacia
`carga_error` (tabla persistente, spec "carga_error model and CSV export")
-- así la grilla de errores y `errores.csv` son UNA sola superficie
compartida para ambas políticas de ejecución, aunque la ejecución detrás
sea distinta (ADR-5: "reporting is shared, execution semantics are not").

`procesar_carga` (Fase 1) ya hace su propio `commit()` en el camino válido,
sin cambios. Este adaptador hace el commit SIMÉTRICO del lado de errores:
a diferencia de los 6 tipos de movimiento (que difieren su escritura a un
staging + job de Fase 9), un `MAESTRO_*` no tiene staging ni job -- es
síncrono dentro del mismo request -- así que ambos desenlaces posibles de
una sola llamada a `procesar_maestro` quedan persistidos al retornar.
"""
from __future__ import annotations

import uuid
from typing import Dict, List, Optional

from app.motored.models.carga_error import CargaError
from app.motored.schemas.carga import CargaResultado
from app.motored.services import carga as carga_mod
from app.motored.services.carga_excel import parse_excel_rows
from app.motored.services.ingesta import errores as errores_mod

CODIGO_ERROR_VALIDACION_MAESTRO = "VALIDACION_MAESTRO"

# Sólo estos dos `tipo` son parte de la historia compartida de Fase 2 (spec
# "Shared drop zone and history for all carga types"). `sucursal`/
# `proveedor` siguen en la carga masiva propia de Fase 1 (spec "Sucursal/
# proveedor uploads are absent from this history") y NO pasan por acá.
_ENTIDAD_POR_TIPO: Dict[str, str] = {
    "MAESTRO_REFERENCIAS": "referencia",
    "MAESTRO_BODEGAS": "bodega",
}


class TipoMaestroNoSoportadoError(Exception):
    """`tipo` no es uno de los dos `MAESTRO_*` que este adaptador enruta."""


def resolver_entidad(tipo: str) -> str:
    """Traduce un `carga_archivo.tipo` MAESTRO_* a la `entidad` que esperan
    `parse_excel_rows`/`procesar_carga` (Fase 1)."""
    entidad = _ENTIDAD_POR_TIPO.get(tipo)
    if entidad is None:
        raise TipoMaestroNoSoportadoError(
            f"'{tipo}' no es un tipo MAESTRO_* soportado por el adaptador de Fase 2."
        )
    return entidad


def _espejar_errores(carga_id: uuid.UUID, resultado: CargaResultado) -> List[CargaError]:
    """Construye una fila `carga_error` por cada `CargaErrorRow` de Fase 1
    -- ver docstring del módulo. `columna`/`valor` quedan en `None`:
    `CargaResultado.errores` sólo trae `fila`/`motivo`, sin la columna/valor
    de origen que sí conocen los errores por-fila del camino tolerante de
    movimientos."""
    return [
        errores_mod.construir_error(
            carga_id, error.fila, None, None, CODIGO_ERROR_VALIDACION_MAESTRO, error.motivo,
        )
        for error in resultado.errores
    ]


async def procesar_maestro(
    db,
    carga_id: uuid.UUID,
    tipo: str,
    filename: Optional[str],
    file_bytes: bytes,
    usuario_id: Optional[uuid.UUID] = None,
) -> CargaResultado:
    """Punto de entrada ADR-5 para un `carga_archivo` de tipo `MAESTRO_*`.
    Enruta a Fase 1 sin modificarla (`parse_excel_rows` + `procesar_carga`)
    y espeja los errores resultantes hacia `carga_error` -- ver docstring
    del módulo para el porqué del commit simétrico. Cualquier excepción
    propia del parseo de Fase 1 (p.ej. `ColumnaObligatoriaFaltanteError`)
    se propaga intacta: este adaptador no agrega ni oculta ningún manejo de
    errores de parseo, sólo enruta."""
    entidad = resolver_entidad(tipo)
    filas = parse_excel_rows(entidad, filename, file_bytes)
    resultado = await carga_mod.procesar_carga(db, entidad, filas, usuario_id)

    if not resultado.ok:
        for error_carga in _espejar_errores(carga_id, resultado):
            db.add(error_carga)
        await db.commit()

    return resultado
