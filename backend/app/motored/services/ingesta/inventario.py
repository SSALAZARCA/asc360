"""
Motored Pedidos — Fase 2 "Ingesta", Phase 6 "INVENTARIO Transform" (PR6)
(sdd/motored-pedidos-ingesta, task 6.1; design ADR-3/ADR-8/ADR-9, spec
"INVENTARIO bodega-principal consolidation and 90-day retention").

Compone `lector` + `columnas` + `resolucion` + `errores` (Phase 3) en el
transform de INVENTARIO: resuelve bodega -> sucursal (la consolidación
bodega-principal, `BA066 -> BA061`, YA la hace el cache de ADR-8 --
`resolucion.construir_cache`/`resolver_sucursal` -- este módulo nunca vuelve
a mirar el código de bodega ni ningún campo de "bodega principal" del propio
archivo), suma existencias por `(sucursal_id, referencia_id)` y hace el
upsert REPLACE-not-sum keyed a `(fecha_corte, sucursal_id, referencia_id)`
(spec "A same-fecha_corte reload replaces, not accumulates").

Columnas confirmadas contra el workbook real de producción (`PLANTILLA
PEDIDO SEPTIEMBRE.xlsx`, hoja "inventario actual"): `Referencia`, `Bodega`,
`Desc.bodega`, `Existencia` (singular, no "Existencias" -- ese es el nombre
de la COLUMNA DE TABLA en `inventario_snapshot`, no el de la celda del
archivo). El archivo también trae `Bodega sucursal consolidada`/
`BODEGAPRIN`, pero ADR-8 es explícito: la consolidación se resuelve DENTRO
del cache contra los maestros propios (`bodega.bodega_principal`), nunca
confiando en lo que el propio ERP reporta en esas dos columnas -- que además
se observó inconsistente en datos reales (una fila con `Bodega=BA091`
reportó `BODEGAPRIN=BA911`, un código distinto al de la propia bodega).

`fecha_corte` NO es una columna del archivo -- INVENTARIO es uno de los
4 tipos que declara período por ADR-9, y como el archivo no trae ninguna
columna de fecha (confirmado: el header no tiene `ULT FECHA COMPRA` como
fecha de corte, sino la última fecha de compra de cada ítem, un campo de
negocio distinto), `fecha_corte` es EXCLUSIVAMENTE el valor declarado por el
usuario al subir (`carga_archivo.periodo_desde == periodo_hasta`, design
"Declares? Required (single fecha_corte)"). Este módulo lo recibe como
parámetro explícito del caller (Fase 9), igual que VENTAS recibe
`tipos_inventario_incluidos`/`proveedor_id` (ver `ventas.py`, sección
"Deviations").

El último bloque de filas del archivo real (795 de 56 532) llega
completamente en blanco -- remanentes de fórmulas de Excel más allá de los
datos reales, no filas inválidas -- por eso una `Referencia` ausente se
descarta EN SILENCIO (ni staging ni `carga_error`), el mismo contrato de
"no es una fila real" que VENTAS ya usa para sus filtros de negocio
(`_pasa_filtros_negocio`).

Deliberadamente FUERA de alcance de esta fase (ver tasks.md Fase 9/12):
- Wiring a `JobRunner`/supervisor y a la API — Fase 9.
- Persistir en `carga_error` un rechazo `E-CARGA-021` como fila real de
  `carga_archivo` — `fecha_corte_fuera_de_ventana` solo CALCULA el
  veredicto puro; decidir `estado`/`log` sigue siendo del caller (Fase 9).
- El purgado físico de filas con más de 90 días (`services/retencion.py`,
  Fase 12) — este módulo nunca borra nada, solo aplica/reemplaza.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import delete, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import settings
from app.motored.models.carga_error import CargaError
from app.motored.models.carga_fila_staging import CargaFilaStaging
from app.motored.models.inventario_detalle import InventarioDetalle
from app.motored.models.inventario_snapshot import InventarioSnapshot
from app.motored.services.ingesta import errores as errores_mod
from app.motored.services.ingesta import numeros as numeros_mod
# El costo usa la misma limpieza de dinero y el mismo tope de `Numeric(16, 2)`
# que los valores de VENTAS (`$1.234.567`, formato colombiano).
from app.motored.services.ingesta import ventas as ventas_mod
from app.motored.services.ingesta.resolucion import (
    CacheResolucion,
    resolver_referencia,
    resolver_sucursal_por_codigo_o_nombre,
)

# Nombres CANÓNICOS (no normalizados) tal como los espera `columnas.
# construir_mapa_columnas` -- verificados contra el workbook real de
# producción, hoja "inventario actual" (ver docstring del módulo).
COLUMNAS_ESPERADAS: Tuple[str, ...] = (
    "Referencia",
    "Bodega",
    "Desc.bodega",
    "Existencia",
    # Costo promedio unitario por bodega (`inventario_detalle`): obligatoria
    # desde 2026-10-01. Un archivo viejo de 4 columnas se detecta como
    # INVENTARIO (4/5) y se rechaza por esta columna faltante.
    "Costo prom. uni.",
)

# `inventario_detalle.bodega` es String(20).
_LARGO_MAX_BODEGA = 20
TAMANO_LOTE_DETALLE = 1000

CODIGO_EXISTENCIA_INVALIDA = "EXISTENCIA_INVALIDA"
CODIGO_FECHA_CORTE_FUERA_DE_VENTANA = "E-CARGA-021"

_CLAVE_UPSERT = ("fecha_corte", "sucursal_id", "referencia_id")


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


def _resolver_existencia_o_error(
    fila_raw: Sequence[Any], mapa_columnas: Dict[str, int], carga_id: uuid.UUID, numero_fila: int
) -> Tuple[Optional[Decimal], Optional[CargaError]]:
    """`Existencia` vacía, con error de Excel o no numérica nunca debe
    propagar un `decimal.InvalidOperation` crudo ni convertirse en un cero
    silencioso (decisión del owner, 2026-09-29, que reemplaza el "vacío =
    0" anterior): la fila queda como `carga_error` (ver `numeros.
    resolver_decimal_o_error`). Un `0` real es un valor válido."""
    return numeros_mod.resolver_decimal_o_error(
        _extraer(fila_raw, mapa_columnas, "Existencia"), "Existencia", carga_id,
        numero_fila, CODIGO_EXISTENCIA_INVALIDA,
        "La existencia de la fila no se pudo interpretar como un número.",
    )


def _resolver_costo(fila_raw: Sequence[Any], mapa_columnas: Dict[str, int]) -> Optional[Decimal]:
    """`Costo prom. uni.` de la fila (dinero colombiano, ver `numeros.py`).
    NUNCA rechaza la fila ni afecta la existencia: una celda en blanco, con
    error de Excel, no numerica o demasiado grande queda en `None`. Un
    negativo se conserva tal cual (el ERP los exporta); el lector de costos
    excluye todo valor NULL o <= 0."""
    valor = ventas_mod._limpiar_moneda(_extraer(fila_raw, mapa_columnas, "Costo prom. uni."))
    try:
        costo = numeros_mod.parsear_decimal(valor)
    except (numeros_mod.CeldaFaltanteError, numeros_mod.CeldaInvalidaError):
        return None
    if abs(costo) >= ventas_mod._VALOR_MAX_ABS:
        return None
    return costo


def _resolver_claves(
    fila_raw: Sequence[Any],
    mapa_columnas: Dict[str, int],
    cache: CacheResolucion,
    carga_id: uuid.UUID,
    numero_fila: int,
    proveedor_id: uuid.UUID,
) -> Tuple[Optional[uuid.UUID], Optional[uuid.UUID], List[CargaError]]:
    """Resuelve sucursal/referencia contra el cache de ADR-8 -- idéntico
    contrato de tolerancia por-fila que `ventas._resolver_claves`: sucursal
    y/o referencia sin resolver NO abortan la fila, se retorna el/los id(s)
    en `None` junto con el `carga_error` correspondiente."""
    desc_bodega = _texto(_extraer(fila_raw, mapa_columnas, "Desc.bodega"))
    codigo_bodega = _texto(_extraer(fila_raw, mapa_columnas, "Bodega"))
    # `valor` del error sigue siendo el nombre (o el codigo si no hay nombre): es el
    # texto que "Mapear a" guarda como `sucursal_alias`. El codigo va en el mensaje.
    texto_sucursal = desc_bodega or codigo_bodega
    sucursal_id = resolver_sucursal_por_codigo_o_nombre(cache, codigo_bodega, desc_bodega)

    codigo_referencia = _texto(_extraer(fila_raw, mapa_columnas, "Referencia"))
    referencia_id = resolver_referencia(cache, codigo_referencia)

    errores: List[CargaError] = []
    if sucursal_id is None:
        errores.append(
            errores_mod.error_sucursal_no_encontrada(
                carga_id, numero_fila, "Desc.bodega", texto_sucursal,
                codigo_bodega=codigo_bodega,
            )
        )
    if referencia_id is None:
        errores.append(
            errores_mod.error_referencia_no_encontrada(
                carga_id, numero_fila, "Referencia", codigo_referencia
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
) -> Tuple[Optional[CargaFilaStaging], List[CargaError]]:
    """Procesa UNA fila cruda de INVENTARIO. Retorna `(fila_staging,
    errores)`. Una `Referencia` vacía es una fila de relleno (cola del
    archivo real, ver docstring del módulo) y se descarta EN SILENCIO --
    nunca genera `REFERENCIA_NO_ENCONTRADA`."""
    codigo_referencia = _texto(_extraer(fila_raw, mapa_columnas, "Referencia"))
    if codigo_referencia is None:
        return None, []

    existencia, error_existencia = _resolver_existencia_o_error(
        fila_raw, mapa_columnas, carga_id, numero_fila
    )
    if existencia is None:
        return None, [error_existencia]

    sucursal_id, referencia_id, errores = _resolver_claves(
        fila_raw, mapa_columnas, cache, carga_id, numero_fila, proveedor_id
    )

    costo = _resolver_costo(fila_raw, mapa_columnas)
    bodega = (_texto(_extraer(fila_raw, mapa_columnas, "Bodega")) or "")[:_LARGO_MAX_BODEGA]
    payload = {
        "existencia": str(existencia),
        "bodega": bodega,
        "costo": None if costo is None else str(costo),
    }
    fila_staging = CargaFilaStaging(
        carga_id=carga_id,
        fila=numero_fila,
        lote=lote,
        payload=payload,
        sucursal_id=sucursal_id,
        referencia_id=referencia_id,
    )
    return fila_staging, errores


ClaveInventarioSnapshot = Tuple[uuid.UUID, uuid.UUID]


def consolidar_existencias(
    filas_staging: Sequence[CargaFilaStaging],
) -> Dict[ClaveInventarioSnapshot, Decimal]:
    """Consolidación bodega-principal (T13, spec "A secondary bodega's stock
    rolls into the principal"): suma `existencia` por `(sucursal_id,
    referencia_id)`. La consolidación en sí ya ocurrió al resolver cada fila
    -- una bodega secundaria y su principal resuelven a la MISMA
    `sucursal_id` vía el cache de ADR-8 -- esta función solo agrupa lo que
    ya comparte esa clave. Filas sin sucursal o sin referencia resuelta
    (`None`) se EXCLUYEN, ya reportadas como `carga_error` en
    `procesar_fila`."""
    totales: Dict[ClaveInventarioSnapshot, Decimal] = {}
    for fila in filas_staging:
        if fila.sucursal_id is None or fila.referencia_id is None:
            continue
        clave: ClaveInventarioSnapshot = (fila.sucursal_id, fila.referencia_id)
        existencia = Decimal(fila.payload["existencia"])
        totales[clave] = totales.get(clave, Decimal("0")) + existencia
    return totales


def construir_statement_upsert(
    consolidado: Dict[ClaveInventarioSnapshot, Decimal], fecha_corte: date, carga_id: uuid.UUID
):
    """`INSERT ... ON CONFLICT DO UPDATE SET existencias = EXCLUDED.
    existencias` -- NUNCA `existencias = existencias + EXCLUDED.
    existencias` (spec "A same-fecha_corte reload replaces, not
    accumulates"), mismo patrón REPLACE-not-sum que `ventas.
    construir_statement_upsert` usa para ADR-4. Retorna `None` si no hay
    nada que aplicar."""
    if not consolidado:
        return None

    valores = [
        {
            "id": uuid.uuid4(),
            "fecha_corte": fecha_corte,
            "sucursal_id": sucursal_id,
            "referencia_id": referencia_id,
            "existencias": existencias,
            "carga_id": carga_id,
        }
        for (sucursal_id, referencia_id), existencias in consolidado.items()
    ]
    stmt = pg_insert(InventarioSnapshot).values(valores)
    return stmt.on_conflict_do_update(
        index_elements=list(_CLAVE_UPSERT),
        set_={"existencias": stmt.excluded.existencias, "carga_id": stmt.excluded.carga_id},
    )


async def aplicar(
    session,
    consolidado: Dict[ClaveInventarioSnapshot, Decimal],
    fecha_corte: date,
    carga_id: uuid.UUID,
) -> None:
    """Ejecuta el upsert como UNA sola sentencia set-based (ADR-2b) -- nunca
    fila por fila. No hace `commit()`: responsabilidad del caller (Fase 9)."""
    stmt = construir_statement_upsert(consolidado, fecha_corte, carga_id)
    if stmt is not None:
        await session.execute(stmt)


def construir_detalle(
    filas_staging: Sequence[CargaFilaStaging], fecha_corte: date, carga_id: uuid.UUID
) -> List[Dict[str, Any]]:
    """Una fila de `inventario_detalle` por fila staged: la bodega fisica cruda
    con su existencia y costo. Excluye lo mismo que el snapshot (sucursal o
    referencia sin resolver) y las filas staged por una version anterior,
    que no traen `bodega`."""
    detalle: List[Dict[str, Any]] = []
    for fila in filas_staging:
        if fila.sucursal_id is None or fila.referencia_id is None:
            continue
        payload = fila.payload
        if "bodega" not in payload:
            continue
        costo = payload.get("costo")
        detalle.append({
            "id": uuid.uuid4(),
            "carga_id": carga_id,
            "fecha_corte": fecha_corte,
            "sucursal_id": fila.sucursal_id,
            "referencia_id": fila.referencia_id,
            "bodega": payload["bodega"],
            "existencia": Decimal(payload["existencia"]),
            "costo_unitario": None if costo is None else Decimal(costo),
        })
    return detalle


async def aplicar_detalle(
    session,
    filas_staging: Sequence[CargaFilaStaging],
    fecha_corte: date,
    carga_id: uuid.UUID,
) -> None:
    """Escribe `inventario_detalle` en la MISMA transaccion que el upsert del
    snapshot (sin `commit()`). Delete-on-replace: borra el detalle de cada
    (fecha_corte, sucursal) presente en ESTA carga y lo inserta de nuevo, por
    lotes. Anular una carga nunca lo borra."""
    detalle = construir_detalle(filas_staging, fecha_corte, carga_id)
    if not detalle:
        return
    sucursales = list({d["sucursal_id"] for d in detalle})
    await session.execute(
        delete(InventarioDetalle).where(
            tuple_(InventarioDetalle.fecha_corte, InventarioDetalle.sucursal_id).in_(
                [(fecha_corte, sucursal_id) for sucursal_id in sucursales]
            )
        )
    )
    for inicio in range(0, len(detalle), TAMANO_LOTE_DETALLE):
        await session.execute(
            pg_insert(InventarioDetalle).values(detalle[inicio:inicio + TAMANO_LOTE_DETALLE])
        )


def fecha_corte_fuera_de_ventana(
    fecha_corte: date,
    fecha_corte_maxima_existente: Optional[date],
    dias_retencion: Optional[int] = None,
) -> bool:
    """ADR-3/design "An INVENTARIO load whose declared fecha_corte is
    already outside the window is rejected at validation (E-CARGA-021)".

    La ventana está anclada a la `fecha_corte` MÁXIMA ya existente en
    `inventario_snapshot` -- NUNCA a `now()` (mismo ancla que usa el purgado
    de ADR-3, "anchored to the newest fecha_corte, not to now()", para que
    ambos chequeos compartan el mismo criterio de qué es "vigente"). Sin
    ninguna `fecha_corte` previa (primer load del sistema, tabla vacía) no
    hay ventana contra la cual comparar -- SIEMPRE `False`, porque esta
    misma fecha_corte se convertirá en la máxima."""
    if fecha_corte_maxima_existente is None:
        return False
    dias = dias_retencion if dias_retencion is not None else settings.MOTORED_RETENCION_DIAS
    limite = fecha_corte_maxima_existente - timedelta(days=dias)
    return fecha_corte < limite
