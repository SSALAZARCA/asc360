"""
Motored Pedidos — Fase 2 "Ingesta", Phase 7 "BACKORDER + DEMANDA_PERDIDA
Transform" (PR7) (sdd/motored-pedidos-ingesta, task 7.2; design ADR-8/ADR-9,
spec "DEMANDA_PERDIDA silent discard of incomplete rows").

Compone `lector` + `columnas` + `resolucion` + `errores` (Phase 3) en el
transform de DEMANDA_PERDIDA: descarta EN SILENCIO (sin `carga_error`, la
ÚNICA excepción documentada a la tolerancia por-fila del resto del pipeline)
cualquier fila sin una `Referencia` resoluble o sin `Cantidad Solicitada
> 0` (spec §5.7, proposal "DEMANDA_PERDIDA: cantidad_solicitada is the
field used; rows without referencia or without quantity > 0 are discarded
silently, not reported as errors"). Esa excepción está ACOTADA a esas dos
condiciones -- una `sucursal` sin resolver en una fila POR LO DEMÁS válida
SÍ sigue la regla general de tolerancia por-fila (`carga_error` +
`sucursal_id = None` en staging), exactamente igual que VENTAS/INVENTARIO/
BACKORDER.

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
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.motored.models.carga_error import CargaError
from app.motored.models.carga_fila_staging import CargaFilaStaging
from app.motored.models.demanda_perdida import DemandaPerdida
from app.motored.services.ingesta import errores as errores_mod
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

_CLAVE_UPSERT = ("fecha", "sucursal_id", "referencia_id")


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
    fila_raw: Sequence[Any], mapa_columnas: Dict[str, int]
) -> Optional[Decimal]:
    """Ausente, no numérica, cero o negativa: TODAS colapsan al mismo
    resultado (`None`) -- spec §5.7 exige descarte SILENCIOSO para
    cualquiera de esos casos, a diferencia de VENTAS/INVENTARIO/BACKORDER
    (que sí emiten un `carga_error` tipado para un valor no-numérico).
    Nunca propaga `decimal.InvalidOperation`."""
    cantidad_raw = _extraer(fila_raw, mapa_columnas, "Cantidad Solicitada")
    if cantidad_raw is None:
        return None
    try:
        cantidad = Decimal(str(cantidad_raw))
    except InvalidOperation:
        return None
    return cantidad if cantidad > 0 else None


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
    errores)`. Orden de evaluación, en línea con la excepción de descarte
    silencioso (spec §5.7): primero `Cantidad Solicitada > 0`, luego
    `Referencia` resoluble -- si CUALQUIERA de las dos falla, la fila se
    descarta EN SILENCIO, `([], None)`, sin tocar sucursal ni emitir ningún
    `carga_error`. Solo si ambas pasan se resuelve `sucursal` -- que SÍ
    sigue la regla general de tolerancia por-fila (`carga_error` +
    `sucursal_id = None` si no resuelve)."""
    cantidad_solicitada = _resolver_cantidad_solicitada(fila_raw, mapa_columnas)
    if cantidad_solicitada is None:
        return None, []

    codigo_referencia = _texto(_extraer(fila_raw, mapa_columnas, "Referencia"))
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
