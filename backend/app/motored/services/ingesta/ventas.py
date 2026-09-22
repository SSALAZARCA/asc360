"""
Motored Pedidos — Fase 2 "Ingesta", Phase 4 "VENTAS Transform" (PR4)
(sdd/motored-pedidos-ingesta, tasks 4.1/4.2; design ADR-2/ADR-2b/ADR-4/ADR-8,
spec "VENTAS net-signed aggregation preserving Módulo origin").

Compone `lector` + `columnas` + `resolucion` + `errores` (Phase 3) en el
PRIMER transform real de Fase 2: filtra por regla de negocio, resuelve
sucursal/referencia contra el cache de ADR-8, arma la fila de
`carga_fila_staging` (ADR-2) y, en `Aplicar`, agrega en memoria y hace el
upsert REPLACE-not-sum de ADR-4 (`ON CONFLICT DO UPDATE SET unidades =
EXCLUDED.unidades`, nunca `+=`) que hace ciertos T17 (idempotencia) y el
caso "meses solapados reemplazan, no acumulan" por construcción: cada
llamada sólo agrega/toca las claves presentes en SU PROPIO staging.

Deliberadamente FUERA de alcance de esta fase (ver tasks.md Fase 5/9):
- ADR-9 (declaración/validación de período): `es_mes_parcial`/
  `dias_transcurridos` en `venta_mensual` quedan presentes-pero-sin-lógica,
  mismo trato que Phase 3 le dio a esas columnas en el modelo.
- Wiring a `JobRunner`/supervisor y a la API (`POST .../aplicar`) — Fase 9.
- Creación automática de referencia bajo `OTROS`
  (`crear_referencias_desconocidas`) — depende de `parametros.resolver()`,
  Fase 9.
- Persistencia de `sucursal_alias` al resolver un error en la UI — Fase 9.

`tipos_inventario_incluidos` y `proveedor_id` los recibe el caller como
parámetros explícitos en vez de leerlos de `parametro_metodologia` o de una
columna del archivo -- ambas resoluciones son de Fase 9 y no se
re-implementan acá (ver apply-progress, sección "Deviations").
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.motored.models.carga_error import CargaError
from app.motored.models.carga_fila_staging import CargaFilaStaging
from app.motored.models.venta_mensual import VentaMensual
from app.motored.services.ingesta import columnas as columnas_mod
from app.motored.services.ingesta import errores as errores_mod
from app.motored.services.ingesta.resolucion import (
    CacheResolucion,
    resolver_referencia,
    resolver_sucursal,
)

# Nombres CANÓNICOS (no normalizados) tal como los espera `columnas.
# construir_mapa_columnas` -- spec §5.1 (columna origen `Referencia`, NO
# `Dct.referencia`: esa es la columna RH de FACTURAS_PEDIDOS/INGRESOS_
# FACTURAS, §5.4/§5.5 -- confirmado además por la firma de detección de
# tipo de archivo del propio spec: "contiene Cantidad inv. + Desc.bodega +
# Referencia -> VENTAS").
COLUMNAS_ESPERADAS: Tuple[str, ...] = (
    "Estado",
    "Módulo",
    "Fecha",
    "Cantidad inv.",
    "Tipo inventario",
    "Desc.bodega",
    "Bodega",
    "Referencia",
)

ESTADO_APROBADA = "Aprobada"
CODIGO_FECHA_INVALIDA = "FECHA_INVALIDA"
CODIGO_CANTIDAD_INVALIDA = "CANTIDAD_INVALIDA"

_CLAVE_UPSERT = ("sucursal_id", "referencia_id", "anio", "mes", "origen")


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


def _resolver_anio_mes(valor_fecha: Any) -> Optional[Tuple[int, int]]:
    """`Fecha` puede llegar de dos formas, dependiendo de si la celda del
    ERP tiene formato de fecha aplicado o no: (a) `openpyxl` con
    `data_only=True` la entrega YA como `date`/`datetime` cuando la celda
    tiene formato de fecha -- confirmado contra el workbook real de
    producción (`PLANTILLA PEDIDO SEPTIEMBRE.xlsx`, hoja "BD ventas
    ultimos 6 meses"), este es el caso real, no el hipotético; (b) un
    serial numérico crudo si la celda está en formato General/Número --
    mismo criterio que `columnas.convertir_fecha_excel`. Cualquier valor
    de un tipo distinto, no numérico, o fuera de 2015-2100 es `None` -- el
    caller lo traduce a `carga_error`, nunca deja escapar la excepción
    cruda (mismo contrato que `carga_excel.py`)."""
    if isinstance(valor_fecha, date):
        if not columnas_mod.anio_es_plausible(valor_fecha.year):
            return None
        return valor_fecha.year, valor_fecha.month
    try:
        fecha = columnas_mod.convertir_fecha_excel(float(valor_fecha))
    except (TypeError, ValueError, columnas_mod.FechaExcelImplausibleError):
        return None
    return fecha.year, fecha.month


def _pasa_filtros_negocio(
    fila_raw: Sequence[Any],
    mapa_columnas: Dict[str, int],
    tipos_inventario_incluidos: Sequence[str],
) -> bool:
    """`Estado != 'Aprobada'` o tipo de inventario no incluido -- spec: esos
    estados "se cuentan y reportan en el log, nunca se suman"; no es una
    fila inválida, no genera `carga_error`."""
    estado = _texto(_extraer(fila_raw, mapa_columnas, "Estado"))
    if estado != ESTADO_APROBADA:
        return False
    tipo_inventario = _texto(_extraer(fila_raw, mapa_columnas, "Tipo inventario"))
    return tipo_inventario in tipos_inventario_incluidos


def _resolver_fecha_o_error(
    fila_raw: Sequence[Any], mapa_columnas: Dict[str, int], carga_id: uuid.UUID, numero_fila: int
) -> Tuple[Optional[Tuple[int, int]], Optional[CargaError]]:
    """`Fecha` implausible/no interpretable -- sin `anio`/`mes` no hay
    payload posible para esa fila (`CODIGO_FECHA_INVALIDA`)."""
    valor_fecha = _extraer(fila_raw, mapa_columnas, "Fecha")
    anio_mes = _resolver_anio_mes(valor_fecha)
    if anio_mes is not None:
        return anio_mes, None
    error = errores_mod.construir_error(
        carga_id, numero_fila, "Fecha", _texto(valor_fecha), CODIGO_FECHA_INVALIDA,
        "La fecha de la fila no se pudo interpretar o cae fuera del rango plausible.",
    )
    return None, error


def _resolver_cantidad_o_error(
    fila_raw: Sequence[Any], mapa_columnas: Dict[str, int], carga_id: uuid.UUID, numero_fila: int
) -> Tuple[Optional[Decimal], Optional[CargaError]]:
    """`Cantidad inv.` no numérica (texto, coma decimal mal formada, etc.)
    nunca debe propagar un `decimal.InvalidOperation` crudo -- mismo
    contrato de tolerancia por-fila que `_resolver_fecha_o_error`
    (`CODIGO_CANTIDAD_INVALIDA`). Ausente (`None`) es distinto de inválida:
    se trata como cero, igual que antes de este fix."""
    cantidad_raw = _extraer(fila_raw, mapa_columnas, "Cantidad inv.")
    if cantidad_raw is None:
        return Decimal("0"), None
    try:
        return Decimal(str(cantidad_raw)), None
    except InvalidOperation:
        error = errores_mod.construir_error(
            carga_id, numero_fila, "Cantidad inv.", _texto(cantidad_raw), CODIGO_CANTIDAD_INVALIDA,
            "La cantidad de la fila no se pudo interpretar como un número.",
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
    """Resuelve sucursal/referencia contra el cache de ADR-8. Sucursal y/o
    referencia sin resolver NO abortan la fila -- spec "Per-row tolerance
    for movement loads": se retorna el/los id(s) en `None` (para que
    `Aplicar` sólo re-resuelva los `NULL`, ADR-2) junto con el
    `carga_error` correspondiente."""
    texto_sucursal = _texto(_extraer(fila_raw, mapa_columnas, "Desc.bodega")) or _texto(
        _extraer(fila_raw, mapa_columnas, "Bodega")
    )
    sucursal_id = resolver_sucursal(cache, texto_sucursal)

    codigo_referencia = _texto(_extraer(fila_raw, mapa_columnas, "Referencia"))
    referencia_id = resolver_referencia(cache, codigo_referencia, proveedor_id)

    errores: List[CargaError] = []
    if sucursal_id is None:
        errores.append(
            errores_mod.error_sucursal_no_encontrada(
                carga_id, numero_fila, "Desc.bodega", texto_sucursal
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
    tipos_inventario_incluidos: Sequence[str],
) -> Tuple[Optional[CargaFilaStaging], List[CargaError]]:
    """Procesa UNA fila cruda de VENTAS. Retorna `(fila_staging, errores)`
    orquestando los tres pasos de la transformación (ver los docstrings de
    `_pasa_filtros_negocio`/`_resolver_fecha_o_error`/`_resolver_claves`)."""
    if not _pasa_filtros_negocio(fila_raw, mapa_columnas, tipos_inventario_incluidos):
        return None, []

    anio_mes, error_fecha = _resolver_fecha_o_error(fila_raw, mapa_columnas, carga_id, numero_fila)
    if anio_mes is None:
        return None, [error_fecha]
    anio, mes = anio_mes

    cantidad, error_cantidad = _resolver_cantidad_o_error(
        fila_raw, mapa_columnas, carga_id, numero_fila
    )
    if cantidad is None:
        return None, [error_cantidad]

    modulo = _texto(_extraer(fila_raw, mapa_columnas, "Módulo")) or ""

    sucursal_id, referencia_id, errores = _resolver_claves(
        fila_raw, mapa_columnas, cache, carga_id, numero_fila, proveedor_id
    )

    payload = {"anio": anio, "mes": mes, "origen": modulo.upper(), "cantidad": str(cantidad)}
    fila_staging = CargaFilaStaging(
        carga_id=carga_id,
        fila=numero_fila,
        lote=lote,
        payload=payload,
        sucursal_id=sucursal_id,
        referencia_id=referencia_id,
    )
    return fila_staging, errores


ClaveVentaMensual = Tuple[uuid.UUID, uuid.UUID, int, int, str]


def agregar_unidades(
    filas_staging: Sequence[CargaFilaStaging],
) -> Dict[ClaveVentaMensual, Decimal]:
    """Agregación NETA-firmada (ADR-4): suma `Cantidad inv.` tal cual llega
    (sin clasificación de devolución/nota de crédito) por clave
    `(sucursal_id, referencia_id, anio, mes, origen)`. Filas sin sucursal o
    sin referencia resuelta (`None`) se EXCLUYEN -- ya fueron reportadas
    como `carga_error` en `procesar_fila`; re-resolver esos `NULL` contra
    los maestros vigentes es responsabilidad del caller (Fase 9) ANTES de
    llamar a esta función.

    Pura y determinística: llamarla dos veces con el mismo input produce el
    mismo resultado (T17) -- no hay estado oculto ni acumulación contra un
    valor previamente aplicado."""
    totales: Dict[ClaveVentaMensual, Decimal] = {}
    for fila in filas_staging:
        if fila.sucursal_id is None or fila.referencia_id is None:
            continue
        payload = fila.payload
        clave: ClaveVentaMensual = (
            fila.sucursal_id,
            fila.referencia_id,
            payload["anio"],
            payload["mes"],
            payload["origen"],
        )
        cantidad = Decimal(payload["cantidad"])
        totales[clave] = totales.get(clave, Decimal("0")) + cantidad
    return totales


def construir_statement_upsert(totales: Dict[ClaveVentaMensual, Decimal], carga_id: uuid.UUID):
    """Construye el `INSERT ... ON CONFLICT DO UPDATE` de ADR-4:
    `SET unidades = EXCLUDED.unidades`, NUNCA `unidades = unidades +
    EXCLUDED.unidades`. Esta es la razón de fondo por la que T17
    (idempotencia) y "meses solapados reemplazan, no acumulan" (spec) se
    cumplen por construcción: la sentencia sólo conoce las claves presentes
    en `totales` -- nunca lee ni suma contra lo que ya existe en la tabla.
    Retorna `None` si no hay nada que aplicar (archivo sin filas
    resolubles)."""
    if not totales:
        return None

    valores = [
        {
            "id": uuid.uuid4(),
            "sucursal_id": sucursal_id,
            "referencia_id": referencia_id,
            "anio": anio,
            "mes": mes,
            "origen": origen,
            "unidades": unidades,
            "carga_id": carga_id,
        }
        for (sucursal_id, referencia_id, anio, mes, origen), unidades in totales.items()
    ]
    stmt = pg_insert(VentaMensual).values(valores)
    return stmt.on_conflict_do_update(
        index_elements=list(_CLAVE_UPSERT),
        set_={"unidades": stmt.excluded.unidades, "carga_id": stmt.excluded.carga_id},
    )


async def aplicar(session, totales: Dict[ClaveVentaMensual, Decimal], carga_id: uuid.UUID) -> None:
    """Ejecuta el upsert como UNA sola sentencia set-based (ADR-2b) -- nunca
    fila por fila. No hace `commit()`: eso es responsabilidad del caller
    (el job runner de Fase 9, que ya define su propio límite de
    transacción por lote)."""
    stmt = construir_statement_upsert(totales, carga_id)
    if stmt is not None:
        await session.execute(stmt)
