"""
Motored Pedidos — Fase 2 "Ingesta", Phase 8 "FACTURAS/INGRESOS + Tránsito"
(PR8) (sdd/motored-pedidos-ingesta, task 8.1; design ADR-8/ADR-9, spec
"FACTURAS_PEDIDOS Parte column and NC subtraction").

Compone `lector` + `columnas` + `resolucion` + `errores` (Phase 3) +
`transito.extraer_prefijo_numero_rh` (Phase 8, H3) en el transform de
FACTURAS_PEDIDOS: resuelve sucursal por `SIIC` (con `Sucursal` como
respaldo -- mismo patrón primario+respaldo que `backorder.py` usa para
`SIC`/`Sucursal`, spec §5.4 "Sucursal | verificación") y referencia contra
el cache de ADR-8, arma la fila de `carga_fila_staging` (ADR-2) y, en
`Aplicar`, agrega en memoria y hace el upsert REPLACE-not-sum de ADR-4
keyed a `(sucursal_id, referencia_id, prefijo_rh, numero_rh)`.

Columnas confirmadas contra el workbook real de producción (`PLANTILLA
PEDIDO SEPTIEMBRE.xlsx`, hoja "facturas pedidos", encabezado en la fila 6):
`SIIC`, `Sucursal`, `Nota crédito`, `Factura`, `Fecha`, `Parte`,
`Cantidad`, `Vlr. Total Neto` (22 434 filas; 10 054 usables, 12 380 filas
de relleno en blanco al final -- mismo patrón de remanente de fórmulas de
Excel que Phase 6/7 ya encontraron en INVENTARIO/BACKORDER). `Parte` y
`Parte Pedida` difieren en 153 de las 10 054 filas usables -- confirma que
la regla "usar `Parte`, nunca `Parte Pedida`" (spec) no es un caso
hipotético acá; por eso `Parte Pedida` NI SIQUIERA está en `COLUMNAS_
ESPERADAS`.

`Tipo documento` vale `'RH'` en TODAS las filas usables de este ciclo --
nunca literalmente `'NC'` como el spec original sugiere en su glosario de
`tipo_documento`. La señal real de nota de crédito es la columna separada
`Nota crédito` teniendo un valor (spec §5.4, cita literal del documento
fuente: "Las notas crédito (`Nota crédito` con valor) restan cantidad") --
por eso `_es_nota_credito` mira esa columna, no `Tipo documento` (que este
módulo ni siquiera necesita leer). Cero filas de este ciclo tienen `Nota
crédito` poblada, así que la resta de NC no se pudo verificar end-to-end
contra datos reales -- misma limitación que Phase 7 encontró para la
columna `sucursal` de DEMANDA_PERDIDA, reportado para re-chequeo cuando el
owner tenga una nota de crédito real cargada.

H3 (`transito.extraer_prefijo_numero_rh`): el `Factura` (`RH194067`) se
descompone vía regex, nunca por ancho fijo -- ver docstring de
`transito.py`. `factura_proveedor_linea.cantidad` (unidades) y `.valor_
total` (`Vlr. Total Neto`, agregado en Phase 8 vía migración
`3956c0ebd69c` -- el cruce de tránsito necesita un valor monetario
comparable, `cantidad` sola no lo es) se agregan juntos, con el MISMO
signo por fila (positivo para una factura normal, negativo cuando `Nota
crédito` tiene valor) -- ver docstring del módulo sobre esa limitación de
verificación.

Deliberadamente FUERA de alcance de esta fase (ver tasks.md Fase 9):
- Wiring a `JobRunner`/supervisor y a la API — Fase 9.
- El cruce de tránsito en sí (`ingresada`/`transito_vencido`/`ingreso_
  parcial_sospechoso`) — eso es `transito.py`, que opera sobre agregados
  YA persistidos de esta tabla más `ingreso_factura`, no sobre este
  archivo directamente.
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
from app.motored.models.factura_proveedor_linea import FacturaProveedorLinea
from app.motored.services.ingesta import columnas as columnas_mod
from app.motored.services.ingesta import errores as errores_mod
from app.motored.services.ingesta import transito as transito_mod
from app.motored.services.ingesta.resolucion import (
    CacheResolucion,
    resolver_referencia,
    resolver_sucursal,
    resolver_sucursal_por_sic,
)

# Nombres CANÓNICOS (no normalizados) tal como los espera `columnas.
# construir_mapa_columnas` -- verificados contra el workbook real de
# producción, hoja "facturas pedidos" (ver docstring del módulo).
# `Parte Pedida` deliberadamente AUSENTE (spec: usar `Parte`, nunca ésa).
COLUMNAS_ESPERADAS: Tuple[str, ...] = (
    "SIIC", "Sucursal", "Nota crédito", "Factura", "Fecha", "Parte", "Cantidad", "Vlr. Total Neto",
)

CODIGO_FECHA_INVALIDA = "FECHA_INVALIDA"
CODIGO_CANTIDAD_INVALIDA = "CANTIDAD_INVALIDA"
CODIGO_VALOR_TOTAL_INVALIDO = "VALOR_TOTAL_INVALIDO"
CODIGO_DOCUMENTO_RH_INVALIDO = "DOCUMENTO_RH_INVALIDO"

_CLAVE_UPSERT = ("sucursal_id", "referencia_id", "prefijo_rh", "numero_rh")


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


def _resolver_fecha_o_error(
    fila_raw: Sequence[Any], mapa_columnas: Dict[str, int], carga_id: uuid.UUID, numero_fila: int
) -> Tuple[Optional[date], Optional[CargaError]]:
    """`Fecha` no interpretable como fecha -- mismo contrato de tolerancia
    por-fila que `ventas._resolver_fecha_o_error`. A diferencia de VENTAS,
    acá solo hace falta la fecha en sí (`fecha_factura`), nunca año/mes
    separados -- FACTURAS_PEDIDOS no declara período por ADR-9."""
    valor_fecha = _extraer(fila_raw, mapa_columnas, "Fecha")
    if isinstance(valor_fecha, date):
        return valor_fecha, None
    if hasattr(valor_fecha, "date"):
        return valor_fecha.date(), None
    error = errores_mod.construir_error(
        carga_id, numero_fila, "Fecha", _texto(valor_fecha), CODIGO_FECHA_INVALIDA,
        "La fecha de la fila no se pudo interpretar.",
    )
    return None, error


def _resolver_decimal_o_error(
    fila_raw: Sequence[Any], mapa_columnas: Dict[str, int], nombre_columna: str,
    carga_id: uuid.UUID, numero_fila: int, codigo_error: str, mensaje: str,
) -> Tuple[Optional[Decimal], Optional[CargaError]]:
    """Ausente -> cero; no numérico -> `carga_error` tipado, nunca un
    `decimal.InvalidOperation` crudo -- mismo contrato que `ventas.
    _resolver_cantidad_o_error`/`inventario._resolver_existencia_o_error`.
    Compartida entre `Cantidad` y `Vlr. Total Neto`: ambas siguen
    exactamente la misma regla de tolerancia."""
    valor_raw = _extraer(fila_raw, mapa_columnas, nombre_columna)
    if valor_raw is None:
        return Decimal("0"), None
    try:
        return Decimal(str(valor_raw)), None
    except InvalidOperation:
        error = errores_mod.construir_error(
            carga_id, numero_fila, nombre_columna, _texto(valor_raw), codigo_error, mensaje,
        )
        return None, error


def _es_nota_credito(fila_raw: Sequence[Any], mapa_columnas: Dict[str, int]) -> bool:
    """`Nota crédito` CON VALOR (cualquier valor, no un patrón específico)
    -- spec §5.4, cita literal del documento fuente: "Nota crédito con
    valor". NO mira `Tipo documento` (siempre `'RH'` en el archivo real,
    ver docstring del módulo)."""
    return _texto(_extraer(fila_raw, mapa_columnas, "Nota crédito")) is not None


def _resolver_claves(
    fila_raw: Sequence[Any],
    mapa_columnas: Dict[str, int],
    cache: CacheResolucion,
    carga_id: uuid.UUID,
    numero_fila: int,
    proveedor_id: uuid.UUID,
) -> Tuple[Optional[uuid.UUID], Optional[uuid.UUID], List[CargaError]]:
    """Resuelve sucursal (SIIC/SIC primero, `Sucursal` como respaldo --
    mismo patrón que `backorder._resolver_claves`) y referencia contra el
    cache de ADR-8. Sucursal y/o referencia sin resolver NO abortan la
    fila."""
    siic = _texto(_extraer(fila_raw, mapa_columnas, "SIIC"))
    texto_sucursal = _texto(_extraer(fila_raw, mapa_columnas, "Sucursal"))
    sucursal_id = resolver_sucursal_por_sic(cache, siic)
    if sucursal_id is None:
        sucursal_id = resolver_sucursal(cache, texto_sucursal)

    codigo_referencia = _texto(_extraer(fila_raw, mapa_columnas, "Parte"))
    referencia_id = resolver_referencia(cache, codigo_referencia, proveedor_id)

    errores: List[CargaError] = []
    if sucursal_id is None:
        errores.append(
            errores_mod.error_sucursal_no_encontrada(carga_id, numero_fila, "SIIC", siic)
        )
    if referencia_id is None:
        errores.append(
            errores_mod.error_referencia_no_encontrada(
                carga_id, numero_fila, "Parte", codigo_referencia
            )
        )
    return sucursal_id, referencia_id, errores


def _resolver_montos_o_error(
    fila_raw: Sequence[Any], mapa_columnas: Dict[str, int], carga_id: uuid.UUID, numero_fila: int
) -> Tuple[Optional[Decimal], Optional[Decimal], Optional[CargaError]]:
    """Resuelve `Cantidad`/`Vlr. Total Neto` y aplica el signo de nota de
    crédito (spec §5.4: "Nota crédito con valor" resta cantidad Y valor,
    mismo signo en ambas -- ver docstring del módulo). Retorna `(cantidad,
    valor_total, error)`; cualquier campo inválido corta acá con el error
    tipado correspondiente, nunca ambos a la vez."""
    cantidad, error_cantidad = _resolver_decimal_o_error(
        fila_raw, mapa_columnas, "Cantidad", carga_id, numero_fila,
        CODIGO_CANTIDAD_INVALIDA, "La cantidad de la fila no se pudo interpretar como un número.",
    )
    if cantidad is None:
        return None, None, error_cantidad

    valor_total, error_valor = _resolver_decimal_o_error(
        fila_raw, mapa_columnas, "Vlr. Total Neto", carga_id, numero_fila,
        CODIGO_VALOR_TOTAL_INVALIDO,
        "El valor total neto de la fila no se pudo interpretar como un número.",
    )
    if valor_total is None:
        return None, None, error_valor

    if _es_nota_credito(fila_raw, mapa_columnas):
        cantidad = -cantidad
        valor_total = -valor_total
    return cantidad, valor_total, None


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
    """Procesa UNA fila cruda de FACTURAS_PEDIDOS. Retorna `(fila_staging,
    errores)` orquestando: fila de relleno (`Factura` ausente) -> parseo
    del documento RH (H3) -> fecha -> cantidad/valor_total (con signo de NC)
    -> resolución de claves."""
    factura_raw = _texto(_extraer(fila_raw, mapa_columnas, "Factura"))
    if factura_raw is None:
        # Fila de relleno (cola del archivo real, ver docstring del módulo)
        # -- mismo contrato de descarte silencioso que INVENTARIO usa para
        # una `Referencia` ausente.
        return None, []

    documento = transito_mod.extraer_prefijo_numero_rh(factura_raw)
    if documento is None:
        error = errores_mod.construir_error(
            carga_id, numero_fila, "Factura", factura_raw, CODIGO_DOCUMENTO_RH_INVALIDO,
            "El número de documento no tiene el formato esperado (dos letras + dígitos).",
        )
        return None, [error]
    prefijo_rh, numero_rh = documento

    fecha_factura, error_fecha = _resolver_fecha_o_error(
        fila_raw, mapa_columnas, carga_id, numero_fila
    )
    if fecha_factura is None:
        return None, [error_fecha]

    cantidad, valor_total, error_monto = _resolver_montos_o_error(
        fila_raw, mapa_columnas, carga_id, numero_fila
    )
    if cantidad is None:
        return None, [error_monto]

    sucursal_id, referencia_id, errores = _resolver_claves(
        fila_raw, mapa_columnas, cache, carga_id, numero_fila, proveedor_id
    )

    payload = {
        "prefijo_rh": prefijo_rh,
        "numero_rh": numero_rh,
        "fecha_factura": fecha_factura.isoformat(),
        "cantidad": str(cantidad),
        "valor_total": str(valor_total),
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


ClaveFacturaLinea = Tuple[uuid.UUID, uuid.UUID, str, int]


def agregar_lineas(filas_staging: Sequence[CargaFilaStaging]) -> Dict[ClaveFacturaLinea, dict]:
    """Agrega `cantidad`/`valor_total` (ADITIVO -- una NC y su factura
    original, cuando comparten la MISMA clave, se netean por construcción,
    mismo criterio que `ventas.agregar_unidades`) por
    `(sucursal_id, referencia_id, prefijo_rh, numero_rh)`. `fecha_factura`
    se conserva de la ÚLTIMA fila procesada para esa clave (todas las
    líneas de un mismo documento comparten la misma fecha en los datos
    reales verificados). Filas sin sucursal o sin referencia resuelta
    (`None`) se EXCLUYEN, ya reportadas como `carga_error` en
    `procesar_fila`."""
    totales: Dict[ClaveFacturaLinea, dict] = {}
    for fila in filas_staging:
        if fila.sucursal_id is None or fila.referencia_id is None:
            continue
        payload = fila.payload
        clave: ClaveFacturaLinea = (
            fila.sucursal_id, fila.referencia_id, payload["prefijo_rh"], payload["numero_rh"],
        )
        acumulado = totales.setdefault(
            clave, {"cantidad": Decimal("0"), "valor_total": Decimal("0"), "fecha_factura": None}
        )
        acumulado["cantidad"] += Decimal(payload["cantidad"])
        acumulado["valor_total"] += Decimal(payload["valor_total"])
        acumulado["fecha_factura"] = date.fromisoformat(payload["fecha_factura"])
    return totales


def construir_statement_upsert(consolidado: Dict[ClaveFacturaLinea, dict], carga_id: uuid.UUID):
    """`INSERT ... ON CONFLICT DO UPDATE SET cantidad = EXCLUDED.cantidad,
    valor_total = EXCLUDED.valor_total` -- NUNCA sumando contra lo ya
    persistido (mismo patrón REPLACE-not-sum que el resto de Fase 2). Los
    tres booleanos de tránsito quedan en su `default=False` -- los
    completa `transito.py` en un paso posterior, nunca este módulo.
    Retorna `None` si no hay nada que aplicar."""
    if not consolidado:
        return None

    valores = [
        {
            "id": uuid.uuid4(),
            "sucursal_id": sucursal_id,
            "referencia_id": referencia_id,
            "prefijo_rh": prefijo_rh,
            "numero_rh": numero_rh,
            "fecha_factura": datos["fecha_factura"],
            "cantidad": datos["cantidad"],
            "valor_total": datos["valor_total"],
            "carga_id": carga_id,
        }
        for (sucursal_id, referencia_id, prefijo_rh, numero_rh), datos in consolidado.items()
    ]
    stmt = pg_insert(FacturaProveedorLinea).values(valores)
    return stmt.on_conflict_do_update(
        index_elements=list(_CLAVE_UPSERT),
        set_={
            "fecha_factura": stmt.excluded.fecha_factura,
            "cantidad": stmt.excluded.cantidad,
            "valor_total": stmt.excluded.valor_total,
            "carga_id": stmt.excluded.carga_id,
        },
    )


async def aplicar(
    session, consolidado: Dict[ClaveFacturaLinea, dict], carga_id: uuid.UUID
) -> None:
    """Ejecuta el upsert como UNA sola sentencia set-based (ADR-2b) -- nunca
    fila por fila. No hace `commit()`: responsabilidad del caller (Fase 9)."""
    stmt = construir_statement_upsert(consolidado, carga_id)
    if stmt is not None:
        await session.execute(stmt)
