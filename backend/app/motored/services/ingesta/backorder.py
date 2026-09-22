"""
Motored Pedidos — Fase 2 "Ingesta", Phase 7 "BACKORDER + DEMANDA_PERDIDA
Transform" (PR7) (sdd/motored-pedidos-ingesta, task 7.1; design ADR-8/ADR-9,
spec "BACKORDER pending-quantity filter").

Compone `lector` + `columnas` + `resolucion` + `errores` (Phase 3) en el
transform de BACKORDER: filtra por `estado` vigente y `cantidad_pendiente
> 0` (regla de negocio, spec "solo suman las líneas con `cantidad_pendiente
> 0`"), resuelve sucursal por `SIC` (con `Sucursal` como respaldo cuando el
SIC no matchea, spec §5.3 "verificación cruzada") y referencia contra el
cache de ADR-8, arma la fila de `carga_fila_staging` (ADR-2) y, en
`Aplicar`, consolida por la clave natural `(sucursal_id, referencia_id,
numero_pedido)` y hace el upsert REPLACE-not-sum de ADR-4 (`ON CONFLICT DO
UPDATE SET cantidad_pendiente = EXCLUDED.cantidad_pendiente`, nunca `+=`)
keyed a `(fecha_corte, sucursal_id, referencia_id, numero_pedido)`.

Columnas confirmadas contra el workbook real de producción (`PLANTILLA
PEDIDO SEPTIEMBRE.xlsx`, hoja "backorder"): `SIC`, `Sucursal`, `Número del
pedido`, `Estado del pedido`, `Referencia Parte`, `Cantidad Pendiente`
(2 430 filas; 814 con `Estado del pedido = 'BACKORDER'`, el resto un bloque
de filas totalmente en blanco al final del sheet -- el mismo patrón de
"relleno de fórmulas de Excel" que Phase 6 encontró en INVENTARIO). A
diferencia de INVENTARIO, acá NO hace falta un descarte especial por
columna vacía: un `Estado del pedido` en blanco ya falla la pertenencia a
`estados_backorder_vigentes`, y una `Cantidad Pendiente` en blanco ya falla
`> 0` -- ambos son los mismos filtros de negocio que YA discriminarían una
fila real con esos valores, así que el bloque de relleno se descarta gratis,
sin lógica adicional (mismo principio que `ventas._pasa_filtros_negocio`:
un filtro de negocio nunca genera `carga_error`, solo excluye).

`SIC` resuelve vía `resolucion.resolver_sucursal_por_sic` (Phase 7 agrega
este lookup a `resolucion.py` -- BACKORDER es el único tipo de archivo cuyo
código de sucursal viene del sistema del PROVEEDOR, no del propio ERP/
maestro de bodegas, así que el `resolver_sucursal` existente por TEXTO no
podía servir sin forzar un matching incorrecto). `Sucursal` (el nombre) es
el respaldo cuando el SIC no resuelve -- mismo patrón primario+respaldo que
VENTAS/INVENTARIO ya usan para `Desc.bodega`/`Bodega`, y además es lo que el
spec llama "verificación cruzada" para esta columna.

`fecha_corte` NO es una columna del archivo -- BACKORDER es uno de los 4
tipos que declara período por ADR-9 (single `fecha_corte`, igual que
INVENTARIO): el archivo real trae `Fecha Creación`/`Fecha Aprobación` (la
fecha del PEDIDO, un dato de negocio distinto), nunca una fecha de corte de
la carga. Este módulo lo recibe como parámetro explícito del caller
(Fase 9), igual que INVENTARIO recibe su propio `fecha_corte` (ver
`inventario.py`, mismo criterio). `estados_backorder_vigentes` lo recibe el
caller como parámetro explícito (default `['BACKORDER']` vive en
`parametro_metodologia`, resuelto por Fase 9), igual que VENTAS recibe
`tipos_inventario_incluidos` -- ver `ventas.py`, sección "Deviations".

Deliberadamente FUERA de alcance de esta fase (ver tasks.md Fase 9):
- Wiring a `JobRunner`/supervisor y a la API — Fase 9.
- El chequeo "PARCIAL" de cross-check de ADR-9 para BACKORDER (advertir si
  alguna `Fecha Creación` es posterior al `fecha_corte` declarado) — no es
  parte de la lista de tareas 7.1 de esta fase; solo INVENTARIO/DEMANDA_
  PERDIDA/BACKORDER declaran período de forma "dura" (un solo valor
  recibido como parámetro), el cross-check parcial de ADR-9 queda para
  cuando Fase 9 tenga el `carga_archivo.log` real donde registrarlo.
- Persistencia de `sucursal_alias` al resolver un error en la UI — Fase 9.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.motored.models.backorder_linea import BackorderLinea
from app.motored.models.carga_error import CargaError
from app.motored.models.carga_fila_staging import CargaFilaStaging
from app.motored.services.ingesta import errores as errores_mod
from app.motored.services.ingesta.resolucion import (
    CacheResolucion,
    resolver_referencia,
    resolver_sucursal,
    resolver_sucursal_por_sic,
)

# Nombres CANÓNICOS (no normalizados) tal como los espera `columnas.
# construir_mapa_columnas` -- verificados contra el workbook real de
# producción, hoja "backorder" (ver docstring del módulo).
COLUMNAS_ESPERADAS: Tuple[str, ...] = (
    "SIC",
    "Sucursal",
    "Número del pedido",
    "Estado del pedido",
    "Referencia Parte",
    "Cantidad Pendiente",
)

CODIGO_CANTIDAD_PENDIENTE_INVALIDA = "CANTIDAD_PENDIENTE_INVALIDA"

_CLAVE_UPSERT = ("fecha_corte", "sucursal_id", "referencia_id", "numero_pedido")


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


def _pasa_filtro_estado(
    fila_raw: Sequence[Any],
    mapa_columnas: Dict[str, int],
    estados_backorder_vigentes: Sequence[str],
) -> bool:
    """`Estado del pedido` fuera de `estados_backorder_vigentes` (default
    `['BACKORDER']`) -- filtro de negocio, no una fila inválida: nunca
    genera `carga_error` (mismo contrato que `ventas._pasa_filtros_
    negocio`)."""
    estado = _texto(_extraer(fila_raw, mapa_columnas, "Estado del pedido"))
    return estado in estados_backorder_vigentes


def _resolver_cantidad_pendiente_o_error(
    fila_raw: Sequence[Any], mapa_columnas: Dict[str, int], carga_id: uuid.UUID, numero_fila: int
) -> Tuple[Optional[Decimal], Optional[CargaError]]:
    """`Cantidad Pendiente` no numérica nunca debe propagar un `decimal.
    InvalidOperation` crudo -- mismo contrato de tolerancia por-fila que
    `ventas._resolver_cantidad_o_error`/`inventario._resolver_existencia_
    o_error`. Ausente (`None`) es distinto de inválida: se trata como cero,
    lo que hace que el filtro `> 0` del caller la descarte igual que
    cualquier línea sin pendiente real."""
    cantidad_raw = _extraer(fila_raw, mapa_columnas, "Cantidad Pendiente")
    if cantidad_raw is None:
        return Decimal("0"), None
    try:
        return Decimal(str(cantidad_raw)), None
    except InvalidOperation:
        error = errores_mod.construir_error(
            carga_id, numero_fila, "Cantidad Pendiente", _texto(cantidad_raw),
            CODIGO_CANTIDAD_PENDIENTE_INVALIDA,
            "La cantidad pendiente de la fila no se pudo interpretar como un número.",
        )
        return None, error


def _resolver_claves(
    fila_raw: Sequence[Any],
    mapa_columnas: Dict[str, int],
    cache: CacheResolucion,
    carga_id: uuid.UUID,
    numero_fila: int,
    proveedor_id: uuid.UUID,
) -> Tuple[Optional[uuid.UUID], Optional[uuid.UUID], List[CargaError]]:
    """Resuelve sucursal (SIC primero, `Sucursal` como respaldo -- spec
    §5.3) y referencia contra el cache de ADR-8. Idéntico contrato de
    tolerancia por-fila que `ventas._resolver_claves`/`inventario._resolver_
    claves`: sucursal y/o referencia sin resolver NO abortan la fila."""
    sic = _texto(_extraer(fila_raw, mapa_columnas, "SIC"))
    texto_sucursal = _texto(_extraer(fila_raw, mapa_columnas, "Sucursal"))
    sucursal_id = resolver_sucursal_por_sic(cache, sic)
    if sucursal_id is None:
        sucursal_id = resolver_sucursal(cache, texto_sucursal)

    codigo_referencia = _texto(_extraer(fila_raw, mapa_columnas, "Referencia Parte"))
    referencia_id = resolver_referencia(cache, codigo_referencia, proveedor_id)

    errores: List[CargaError] = []
    if sucursal_id is None:
        errores.append(
            errores_mod.error_sucursal_no_encontrada(carga_id, numero_fila, "SIC", sic)
        )
    if referencia_id is None:
        errores.append(
            errores_mod.error_referencia_no_encontrada(
                carga_id, numero_fila, "Referencia Parte", codigo_referencia
            )
        )
    return sucursal_id, referencia_id, errores


def procesar_fila(
    fila_raw: Sequence[Any],
    *,
    numero_fila: int,
    lote: int,
    mapa_columnas: Dict[str, int],
    cache: CacheResolucion,
    carga_id: uuid.UUID,
    proveedor_id: uuid.UUID,
    estados_backorder_vigentes: Sequence[str],
) -> Tuple[Optional[CargaFilaStaging], List[CargaError]]:
    """Procesa UNA fila cruda de BACKORDER. Retorna `(fila_staging,
    errores)` orquestando: filtro de `estado` -> resolución de `Cantidad
    Pendiente` (error tipado si no es numérica) -> filtro `> 0` -> resolución
    de claves (SIC/Sucursal/Referencia Parte)."""
    if not _pasa_filtro_estado(fila_raw, mapa_columnas, estados_backorder_vigentes):
        return None, []

    cantidad_pendiente, error_cantidad = _resolver_cantidad_pendiente_o_error(
        fila_raw, mapa_columnas, carga_id, numero_fila
    )
    if cantidad_pendiente is None:
        return None, [error_cantidad]
    if cantidad_pendiente <= 0:
        return None, []

    numero_pedido = _texto(_extraer(fila_raw, mapa_columnas, "Número del pedido"))

    sucursal_id, referencia_id, errores = _resolver_claves(
        fila_raw, mapa_columnas, cache, carga_id, numero_fila, proveedor_id
    )

    payload = {"cantidad_pendiente": str(cantidad_pendiente), "numero_pedido": numero_pedido}
    fila_staging = CargaFilaStaging(
        carga_id=carga_id,
        fila=numero_fila,
        lote=lote,
        payload=payload,
        sucursal_id=sucursal_id,
        referencia_id=referencia_id,
    )
    return fila_staging, errores


ClaveBackorderLinea = Tuple[uuid.UUID, uuid.UUID, str]


def consolidar_lineas(
    filas_staging: Sequence[CargaFilaStaging],
) -> Dict[ClaveBackorderLinea, Decimal]:
    """Agrupa por la clave natural `(sucursal_id, referencia_id,
    numero_pedido)` -- SIN sumar duplicados: `cantidad_pendiente` es un
    valor puntual (el estado ACTUAL de una línea de pedido específica), no
    una cantidad acumulable como las unidades vendidas de VENTAS o las
    existencias de INVENTARIO. Si la MISMA clave apareciera dos veces en un
    mismo archivo (no observado en el workbook real de producción: 814
    líneas, 814 claves únicas), la última fila procesada gana -- el mismo
    criterio "más reciente pisa" que ADR-4 usa entre cargas distintas,
    aplicado acá dentro de una sola carga. Filas sin sucursal o sin
    referencia resuelta (`None`) se EXCLUYEN, ya reportadas como
    `carga_error` en `procesar_fila`."""
    totales: Dict[ClaveBackorderLinea, Decimal] = {}
    for fila in filas_staging:
        if fila.sucursal_id is None or fila.referencia_id is None:
            continue
        payload = fila.payload
        clave: ClaveBackorderLinea = (
            fila.sucursal_id, fila.referencia_id, payload["numero_pedido"],
        )
        totales[clave] = Decimal(payload["cantidad_pendiente"])
    return totales


def construir_statement_upsert(
    consolidado: Dict[ClaveBackorderLinea, Decimal], fecha_corte: date, carga_id: uuid.UUID
):
    """`INSERT ... ON CONFLICT DO UPDATE SET cantidad_pendiente = EXCLUDED.
    cantidad_pendiente` -- NUNCA `cantidad_pendiente = cantidad_pendiente +
    EXCLUDED.cantidad_pendiente` (mismo patrón REPLACE-not-sum que
    `ventas.construir_statement_upsert`/`inventario.construir_statement_
    upsert`). `estado` se fija a `'BACKORDER'`: solo las líneas que ya
    pasaron el filtro `estados_backorder_vigentes` de `procesar_fila`
    llegan hasta acá. Retorna `None` si no hay nada que aplicar."""
    if not consolidado:
        return None

    valores = [
        {
            "id": uuid.uuid4(),
            "fecha_corte": fecha_corte,
            "sucursal_id": sucursal_id,
            "referencia_id": referencia_id,
            "numero_pedido": numero_pedido,
            "estado": "BACKORDER",
            "cantidad_pendiente": cantidad_pendiente,
            "carga_id": carga_id,
        }
        for (sucursal_id, referencia_id, numero_pedido), cantidad_pendiente in consolidado.items()
    ]
    stmt = pg_insert(BackorderLinea).values(valores)
    return stmt.on_conflict_do_update(
        index_elements=list(_CLAVE_UPSERT),
        set_={
            "cantidad_pendiente": stmt.excluded.cantidad_pendiente,
            "estado": stmt.excluded.estado,
            "carga_id": stmt.excluded.carga_id,
        },
    )


async def aplicar(
    session,
    consolidado: Dict[ClaveBackorderLinea, Decimal],
    fecha_corte: date,
    carga_id: uuid.UUID,
) -> None:
    """Ejecuta el upsert como UNA sola sentencia set-based (ADR-2b) -- nunca
    fila por fila. No hace `commit()`: responsabilidad del caller (Fase 9)."""
    stmt = construir_statement_upsert(consolidado, fecha_corte, carga_id)
    if stmt is not None:
        await session.execute(stmt)
