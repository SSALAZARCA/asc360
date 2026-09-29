"""
Motored Pedidos — Fase 2 "Ingesta", Phase 7 "BACKORDER + DEMANDA_PERDIDA
Transform" (PR7) (sdd/motored-pedidos-ingesta, task 7.2; design ADR-8/ADR-9,
spec "DEMANDA_PERDIDA silent discard of incomplete rows").

Compone `lector` + `columnas` + `resolucion` + `errores` (Phase 3) en el
transform de DEMANDA_PERDIDA. Descarta EN SILENCIO (sin `carga_error`) una
fila sin `Referencia` (relleno), con `Cantidad Solicitada <= 0` o con una
`Referencia` sin resolver (spec §5.7, proposal "rows without referencia or
without quantity > 0 are discarded silently"). Decisión del owner
(2026-09-29) que REEMPLAZA el descarte silencioso para una cantidad vacía,
con error de Excel (`#N/A`, `#NAME?`...) o no numérica: esa fila NO se
carga y queda como `carga_error` visible en el informe previo. Una
`sucursal` sin resolver en una fila por lo demás válida sigue la regla
general de tolerancia por-fila (`carga_error` + `sucursal_id = None` en
staging), igual que VENTAS/INVENTARIO/BACKORDER.

Columnas confirmadas contra el workbook real de producción (`PLANTILLA
PEDIDO SEPTIEMBRE.xlsx`, hoja "Ventas perdidas"): `sucursal`, `sucursal
Drive`, `Referencia`, `Cantidad Solicitada` (710 filas totales). El sheet
real de ESTE ciclo tiene las 710 filas en blanco/`#N/A` -- cero filas con
`Referencia` Y `Cantidad Solicitada > 0` simultáneamente -- confirmando
literalmente la propia descripción del spec ("El archivo trae muchas filas
vacías y `#N/A` de fórmulas") en vez de ser un caso hipotético. Como
NINGUNA fila del archivo real es utilizable este ciclo, el formato de una
columna `sucursal` POBLADA no pudo verificarse end-to-end contra datos
reales -- reportado en el apply-progress para que el orquestador lo
re-confirme cuando el owner tenga un mes con demanda perdida real cargada.

`fecha` NO es una columna del archivo -- DEMANDA_PERDIDA es uno de los 4
tipos que declara período por ADR-9 (single `fecha`, mismo criterio que
`fecha_corte` de INVENTARIO/BACKORDER): este módulo la recibe como
parámetro explícito del caller (Fase 9) en `aplicar`/`construir_statement_
upsert`, nunca por fila.

A diferencia de BACKORDER (una línea puntual por pedido, ver `backorder.
consolidar_lineas`), cada fila de DEMANDA_PERDIDA es una INSTANCIA separada
de demanda perdida para la misma sucursal/referencia en el mismo día --
sumarlas con `agregar_cantidad_solicitada` es correcto, mismo criterio
aditivo que `ventas.agregar_unidades` usa para unidades vendidas.

Deliberadamente FUERA de alcance de esta fase (ver tasks.md Fase 9):
- Wiring a `JobRunner`/supervisor y a la API — Fase 9.
- Persistencia de `sucursal_alias` al resolver un error en la UI — Fase 9.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.motored.models.carga_error import CargaError
from app.motored.models.carga_fila_staging import CargaFilaStaging
from app.motored.models.demanda_perdida import DemandaPerdida
from app.motored.services.ingesta import errores as errores_mod
from app.motored.services.ingesta import numeros as numeros_mod
from app.motored.services.ingesta.resolucion import (
    CacheResolucion,
    resolver_referencia,
    resolver_sucursal,
)

# Nombres CANÓNICOS (no normalizados) tal como los espera `columnas.
# construir_mapa_columnas` -- verificados contra el workbook real de
# producción, hoja "Ventas perdidas" (ver docstring del módulo).
COLUMNAS_ESPERADAS: Tuple[str, ...] = (
    "sucursal",
    "sucursal Drive",
    "Referencia",
    "Cantidad Solicitada",
)

CODIGO_CANTIDAD_SOLICITADA_INVALIDA = "CANTIDAD_SOLICITADA_INVALIDA"

_CLAVE_UPSERT = ("fecha", "sucursal_id", "referencia_id", "origen")


def _extraer(fila_raw: Sequence[Any], mapa: Dict[str, int], nombre: str) -> Any:
    idx = mapa.get(nombre)
    if idx is None or idx >= len(fila_raw):
        return None
    return fila_raw[idx]


def _texto(valor: Any) -> Optional[str]:
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto or None


def _resolver_cantidad_solicitada(
    fila_raw: Sequence[Any], mapa_columnas: Dict[str, int], carga_id: uuid.UUID, numero_fila: int
) -> Tuple[Optional[Decimal], Optional[CargaError]]:
    """`Cantidad Solicitada` vacía, con error de Excel o no numérica -> error
    de fila (`numeros.resolver_decimal_o_error`); decisión del owner
    (2026-09-29) que reemplaza el descarte silencioso de la spec §5.7 para
    esos casos. Cero y negativa SÍ son numéricas: las descarta en silencio
    el caller (`procesar_fila`)."""
    return numeros_mod.resolver_decimal_o_error(
        _extraer(fila_raw, mapa_columnas, "Cantidad Solicitada"), "Cantidad Solicitada",
        carga_id, numero_fila, CODIGO_CANTIDAD_SOLICITADA_INVALIDA,
        "La cantidad solicitada de la fila no se pudo interpretar como un número.",
    )


def procesar_fila(
    fila_raw: Sequence[Any],
    *,
    numero_fila: int,
    lote: int,
    mapa_columnas: Dict[str, int],
    cache: CacheResolucion,
    carga_id: uuid.UUID,
    proveedor_id: uuid.UUID,
) -> Tuple[Optional[CargaFilaStaging], List[CargaError]]:
    """Procesa UNA fila cruda de DEMANDA_PERDIDA. Retorna `(fila_staging,
    errores)`. Orden de evaluación: `Referencia` vacía es una fila de
    relleno y se descarta EN SILENCIO; luego `Cantidad Solicitada` vacía,
    con error de Excel o no numérica es un error de fila (decisión del owner,
    2026-09-29); una cantidad `<= 0` o una `Referencia` no resuelta se
    descartan EN SILENCIO (spec §5.7, sin tocar sucursal). Solo si todo eso
    pasa se resuelve `sucursal` -- que SÍ sigue la regla general de
    tolerancia por-fila (`carga_error` + `sucursal_id = None` si no
    resuelve)."""
    codigo_referencia = _texto(_extraer(fila_raw, mapa_columnas, "Referencia"))
    if codigo_referencia is None:
        return None, []

    cantidad_solicitada, error_cantidad = _resolver_cantidad_solicitada(
        fila_raw, mapa_columnas, carga_id, numero_fila
    )
    if cantidad_solicitada is None:
        return None, [error_cantidad]
    if cantidad_solicitada <= 0:
        return None, []

    referencia_id = resolver_referencia(cache, codigo_referencia, proveedor_id)
    if referencia_id is None:
        return None, []

    texto_sucursal = _texto(_extraer(fila_raw, mapa_columnas, "sucursal")) or _texto(
        _extraer(fila_raw, mapa_columnas, "sucursal Drive")
    )
    sucursal_id = resolver_sucursal(cache, texto_sucursal)

    errores: List[CargaError] = []
    if sucursal_id is None:
        errores.append(
            errores_mod.error_sucursal_no_encontrada(
                carga_id, numero_fila, "sucursal", texto_sucursal
            )
        )

    payload = {"cantidad_solicitada": str(cantidad_solicitada)}
    fila_staging = CargaFilaStaging(
        carga_id=carga_id,
        fila=numero_fila,
        lote=lote,
        payload=payload,
        sucursal_id=sucursal_id,
        referencia_id=referencia_id,
    )
    return fila_staging, errores


ClaveDemandaPerdida = Tuple[uuid.UUID, uuid.UUID]


def agregar_cantidad_solicitada(
    filas_staging: Sequence[CargaFilaStaging],
) -> Dict[ClaveDemandaPerdida, Decimal]:
    """Suma `cantidad_solicitada` por `(sucursal_id, referencia_id)` --
    cada fila es una instancia independiente de demanda perdida, sumarlas
    es correcto (mismo criterio aditivo que `ventas.agregar_unidades`).
    Filas sin sucursal o sin referencia resuelta (`None`) se EXCLUYEN --
    una sucursal sin resolver aquí YA fue reportada como `carga_error` en
    `procesar_fila` (a diferencia de una referencia sin resolver, que nunca
    llega a staging en absoluto)."""
    totales: Dict[ClaveDemandaPerdida, Decimal] = {}
    for fila in filas_staging:
        if fila.sucursal_id is None or fila.referencia_id is None:
            continue
        clave: ClaveDemandaPerdida = (fila.sucursal_id, fila.referencia_id)
        cantidad = Decimal(fila.payload["cantidad_solicitada"])
        totales[clave] = totales.get(clave, Decimal("0")) + cantidad
    return totales


def construir_statement_upsert(
    totales: Dict[ClaveDemandaPerdida, Decimal], fecha: date, carga_id: uuid.UUID
):
    """`INSERT ... ON CONFLICT DO UPDATE SET cantidad_solicitada = EXCLUDED.
    cantidad_solicitada` -- NUNCA `cantidad_solicitada = cantidad_solicitada
    + EXCLUDED.cantidad_solicitada` (mismo patrón REPLACE-not-sum que
    `ventas.construir_statement_upsert`/`inventario.construir_statement_
    upsert`/`backorder.construir_statement_upsert`). Retorna `None` si no
    hay nada que aplicar."""
    if not totales:
        return None

    valores = [
        {
            "id": uuid.uuid4(),
            "fecha": fecha,
            "sucursal_id": sucursal_id,
            "referencia_id": referencia_id,
            "cantidad_solicitada": cantidad_solicitada,
            "carga_id": carga_id,
            "origen": "EXCEL",
        }
        for (sucursal_id, referencia_id), cantidad_solicitada in totales.items()
    ]
    stmt = pg_insert(DemandaPerdida).values(valores)
    return stmt.on_conflict_do_update(
        index_elements=list(_CLAVE_UPSERT),
        set_={
            "cantidad_solicitada": stmt.excluded.cantidad_solicitada,
            "carga_id": stmt.excluded.carga_id,
        },
    )


async def aplicar(
    session, totales: Dict[ClaveDemandaPerdida, Decimal], fecha: date, carga_id: uuid.UUID
) -> None:
    """Ejecuta el upsert como UNA sola sentencia set-based (ADR-2b) -- nunca
    fila por fila. No hace `commit()`: responsabilidad del caller (Fase 9)."""
    stmt = construir_statement_upsert(totales, fecha, carga_id)
    if stmt is not None:
        await session.execute(stmt)
