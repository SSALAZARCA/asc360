"""
Motored Pedidos — Fase 2 "Ingesta", Phase 3 "Movement Schema + Shared Infra"
(sdd/motored-pedidos-ingesta, task 3.5; design §Schema, spec "carga_error
model and CSV export").

Emisor de `carga_error` (`construir_error`, más los dos atajos con código
mínimo requerido por spec: `SUCURSAL_NO_ENCONTRADA`/
`REFERENCIA_NO_ENCONTRADA`) y export CSV. `construir_error` solo CONSTRUYE
el objeto -- nunca hace `session.add`/`commit`: el caller (Fase 4+, un
transform real) decide cuándo persistir, igual que ADR-2b hace con
`carga_fila_staging` (inserción set-based por lote, un commit por lote).

`generar_csv_errores` neutraliza cualquier valor que empiece con
`=`, `+`, `-` o `@` prefijándolo con `'` -- la mitigación estándar de
inyección de fórmulas CSV (spec: "neutralizing leading `=`, `+`, `-`, `@`
in any field"): Excel/Sheets tratan una celda que empieza con `'` como
texto literal, nunca como fórmula.
"""
from __future__ import annotations

import csv
import io
import uuid
from typing import Any, Iterable, Optional

from app.motored.models.carga_error import CargaError

CODIGO_SUCURSAL_NO_ENCONTRADA = "SUCURSAL_NO_ENCONTRADA"
CODIGO_REFERENCIA_NO_ENCONTRADA = "REFERENCIA_NO_ENCONTRADA"

_PREFIJOS_PELIGROSOS = ("=", "+", "-", "@")
_ENCABEZADOS_CSV = ("fila", "columna", "valor", "codigo_error", "mensaje")


def construir_error(
    carga_id: uuid.UUID,
    fila: int,
    columna: Optional[str],
    valor: Optional[str],
    codigo_error: str,
    mensaje: str,
) -> CargaError:
    """Construye una fila `carga_error` SIN persistirla -- ver docstring
    del módulo. `id`/`created_at` los aplica SQLAlchemy al momento del
    `add()`/flush real, igual que cualquier otro modelo Motored."""
    return CargaError(
        carga_id=carga_id,
        fila=fila,
        columna=columna,
        valor=valor,
        codigo_error=codigo_error,
        mensaje=mensaje,
    )


def error_sucursal_no_encontrada(
    carga_id: uuid.UUID, fila: int, columna: Optional[str], valor: Optional[str]
) -> CargaError:
    return construir_error(
        carga_id, fila, columna, valor, CODIGO_SUCURSAL_NO_ENCONTRADA,
        f"No se encontró una sucursal para el texto '{valor}'.",
    )


def error_referencia_no_encontrada(
    carga_id: uuid.UUID, fila: int, columna: Optional[str], valor: Optional[str]
) -> CargaError:
    return construir_error(
        carga_id, fila, columna, valor, CODIGO_REFERENCIA_NO_ENCONTRADA,
        f"No se encontró una referencia para el código '{valor}'.",
    )


def _neutralizar_valor_csv(valor: Any) -> Any:
    """Antepone `'` a cualquier string que empiece con `=`/`+`/`-`/`@` --
    nunca toca valores `None` ni no-string (p.ej. `fila`, un `int`)."""
    if isinstance(valor, str) and valor.startswith(_PREFIJOS_PELIGROSOS):
        return f"'{valor}"
    return valor


def generar_csv_errores(errores: Iterable[CargaError]) -> str:
    """Genera el CSV completo de `carga_error` (spec: "The full error set
    MUST be downloadable as CSV"). Usa `csv.writer` -- nunca concatenación
    manual de strings -- para que comas/comillas dentro de `valor`/
    `mensaje` se escapen correctamente además de neutralizarse."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(_ENCABEZADOS_CSV)
    for error in errores:
        writer.writerow(
            [
                error.fila,
                error.columna,
                _neutralizar_valor_csv(error.valor),
                error.codigo_error,
                error.mensaje,
            ]
        )
    return buffer.getvalue()
