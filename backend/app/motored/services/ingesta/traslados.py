"""
TRASLADOS load (odd/tasks/motored-traslados-pendientes.md, T1): the ERP file
of transfers between stores that are still alive in the ERP, one row per
transfer line (sample `Traslados_09.xlsx`).

Required columns: `Nro documento`, `Fecha`, `Bod. salida`, `Bod. entrada`,
`Referencia`, `Cant. Saldo`. Optional: `Desc. bod. salida`, `Desc. bod.
entrada`, `Desc. item`, `Item resumen`, `U.M.`. Every text cell is trimmed
(the ERP pads them with spaces).

Row rules:
- A row without `Nro documento` is filler and is skipped silently.
- An empty origin bodega, an invalid date or a quantity that is not a number
  greater than zero is a row error.
- The DESTINATION bodega must resolve to a store (by bodega code, then by its
  description, through the same cache as INVENTARIO); an unknown one is a
  `SUCURSAL_NO_ENCONTRADA` row error, because the receiving store is who
  certifies the reception. An unknown ORIGIN is kept without a store.
- A reference that is not in the catalog is kept with its code and
  description (`referencia_id` NULL), never an error.

Snapshot semantics: every applied load is a FULL snapshot of the transfers
alive in the ERP. `aplicar` only inserts this load's lines; the current
snapshot is the latest non-ANULADO APLICADO TRASLADOS carga (see
`services/traslados_pendientes.py`), so a transfer missing from a newer load
has been received in the ERP, and annulling the newest load restores the
previous snapshot.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import insert

from app.motored.models.carga_error import CargaError
from app.motored.models.carga_fila_staging import CargaFilaStaging
from app.motored.models.traslado import TrasladoLinea
from app.motored.services.ingesta import columnas as columnas_mod
from app.motored.services.ingesta import errores as errores_mod
from app.motored.services.ingesta import numeros as numeros_mod
from app.motored.services.ingesta.lotes import partir
from app.motored.services.ingesta.resolucion import (
    CacheResolucion, resolver_referencia,
    resolver_sucursal_por_codigo_o_nombre,
)

COLUMNAS_ESPERADAS: Tuple[str, ...] = (
    "Nro documento", "Fecha", "Bod. salida", "Bod. entrada", "Referencia",
    "Cant. Saldo",
)
COLUMNAS_OPCIONALES: Tuple[str, ...] = (
    "Desc. bod. salida", "Desc. bod. entrada", "Desc. item", "Item resumen",
    "U.M.",
)

CODIGO_FECHA_INVALIDA = "FECHA_INVALIDA"
CODIGO_CANTIDAD_INVALIDA = "CANTIDAD_INVALIDA"
CODIGO_BODEGA_SALIDA_VACIA = "BODEGA_SALIDA_VACIA"

# Stored lengths of `traslado_linea`.
_LARGOS = {
    "nro_documento": 40, "bodega": 20, "descripcion_bodega": 120,
    "referencia": 60, "descripcion": 200, "unidad": 20,
}

ResultadoFila = Tuple[Optional[CargaFilaStaging], List[CargaError]]


def _texto(fila_raw: Sequence[Any], mapa: Dict[str, int], nombre: str,
           largo: int) -> Optional[str]:
    """Trimmed cell text cut to the stored length; None when empty/absent."""
    idx = mapa.get(nombre)
    if idx is None or idx >= len(fila_raw) or fila_raw[idx] is None:
        return None
    texto = str(fila_raw[idx]).strip()
    return texto[:largo] or None


def _crudo(fila_raw: Sequence[Any], mapa: Dict[str, int], nombre: str) -> Any:
    idx = mapa.get(nombre)
    return fila_raw[idx] if idx is not None and idx < len(fila_raw) else None


def _error(carga_id, numero_fila, columna, valor, codigo, mensaje):
    return [errores_mod.construir_error(
        carga_id, numero_fila, columna, valor, codigo, mensaje)]


def _destino(fila_raw, mapa, cache, carga_id, numero_fila):
    """`(sucursal_id, errores)` of the receiving bodega."""
    codigo = _texto(fila_raw, mapa, "Bod. entrada", _LARGOS["bodega"])
    nombre = _texto(fila_raw, mapa, "Desc. bod. entrada",
                    _LARGOS["descripcion_bodega"])
    sucursal_id = resolver_sucursal_por_codigo_o_nombre(cache, codigo, nombre)
    if sucursal_id is not None:
        return sucursal_id, []
    return None, [errores_mod.error_sucursal_no_encontrada(
        carga_id, numero_fila, "Desc. bod. entrada", nombre or codigo,
        codigo_bodega=codigo)]


def procesar_fila(
    fila_raw: Sequence[Any], *, numero_fila: int, lote: int,
    mapa_columnas: Dict[str, int], cache: CacheResolucion,
    carga_id: uuid.UUID, proveedor_id: Optional[uuid.UUID] = None,
) -> ResultadoFila:
    """One raw row -> `(staging row, errors)`. The staging row carries the
    receiving store (`sucursal_id`) and the resolved reference."""
    documento = _texto(fila_raw, mapa_columnas, "Nro documento",
                       _LARGOS["nro_documento"])
    if documento is None:
        return None, []
    bodega_salida = _texto(fila_raw, mapa_columnas, "Bod. salida",
                           _LARGOS["bodega"])
    if bodega_salida is None:
        return None, _error(
            carga_id, numero_fila, "Bod. salida", None,
            CODIGO_BODEGA_SALIDA_VACIA, "La bodega de salida está vacía.")
    fecha = columnas_mod.a_fecha(_crudo(fila_raw, mapa_columnas, "Fecha"))
    if fecha is None:
        return None, _error(
            carga_id, numero_fila, "Fecha", None, CODIGO_FECHA_INVALIDA,
            "La fecha de la fila no se pudo interpretar.")
    cantidad, error = numeros_mod.resolver_decimal_o_error(
        _crudo(fila_raw, mapa_columnas, "Cant. Saldo"), "Cant. Saldo",
        carga_id, numero_fila, CODIGO_CANTIDAD_INVALIDA,
        "La cantidad de la fila no se pudo interpretar como un número.")
    if cantidad is None:
        return None, [error]
    if cantidad <= 0:
        return None, _error(
            carga_id, numero_fila, "Cant. Saldo", str(cantidad),
            CODIGO_CANTIDAD_INVALIDA,
            "La cantidad de un traslado debe ser mayor que cero.")
    sucursal_id, errores = _destino(
        fila_raw, mapa_columnas, cache, carga_id, numero_fila)
    if sucursal_id is None:
        return None, errores
    return _staging(
        fila_raw, mapa_columnas, cache, carga_id, numero_fila, lote,
        documento, bodega_salida, fecha, cantidad, sucursal_id), []


def _staging(fila_raw, mapa, cache, carga_id, numero_fila, lote, documento,
             bodega_salida, fecha: date, cantidad: Decimal,
             sucursal_id) -> CargaFilaStaging:
    descripcion_salida = _texto(fila_raw, mapa, "Desc. bod. salida",
                                _LARGOS["descripcion_bodega"])
    origen = resolver_sucursal_por_codigo_o_nombre(
        cache, bodega_salida, descripcion_salida)
    codigo_ref = _texto(fila_raw, mapa, "Referencia", _LARGOS["referencia"])
    referencia_id = resolver_referencia(cache, codigo_ref)
    payload = {
        "nro_documento": documento,
        "fecha": fecha.isoformat(),
        "bodega_salida": bodega_salida,
        "descripcion_bodega_salida": descripcion_salida,
        "sucursal_salida_id": str(origen) if origen else None,
        "bodega_entrada": _texto(
            fila_raw, mapa, "Bod. entrada", _LARGOS["bodega"]) or "",
        "referencia_codigo": codigo_ref or "",
        "descripcion": _texto(
            fila_raw, mapa, "Desc. item", _LARGOS["descripcion"]),
        "unidad": _texto(fila_raw, mapa, "U.M.", _LARGOS["unidad"]),
        "cantidad": str(cantidad),
    }
    return CargaFilaStaging(
        carga_id=carga_id, fila=numero_fila, lote=lote, payload=payload,
        sucursal_id=sucursal_id, referencia_id=referencia_id)


def construir_lineas(
    filas_staging: Sequence[CargaFilaStaging], carga_id: uuid.UUID,
) -> Dict[uuid.UUID, dict]:
    """The `traslado_linea` rows of the staged lines (keyed by their id, so
    `lotes.partir` can split the insert)."""
    lineas: Dict[uuid.UUID, dict] = {}
    for fila in filas_staging:
        p = fila.payload
        salida = p.get("sucursal_salida_id")
        lineas[uuid.uuid4()] = {
            "carga_id": carga_id,
            "nro_documento": p["nro_documento"],
            "fecha": date.fromisoformat(p["fecha"]),
            "bodega_salida": p["bodega_salida"],
            "descripcion_bodega_salida": p.get("descripcion_bodega_salida"),
            "sucursal_salida_id": uuid.UUID(salida) if salida else None,
            "bodega_entrada": p["bodega_entrada"],
            "sucursal_entrada_id": fila.sucursal_id,
            "referencia_codigo": p["referencia_codigo"],
            "referencia_id": fila.referencia_id,
            "descripcion": p.get("descripcion"),
            "unidad": p.get("unidad"),
            "cantidad": Decimal(p["cantidad"]),
        }
    return lineas


async def aplicar(session, lineas: Dict[uuid.UUID, dict]) -> None:
    """Inserts the load's lines in batches. No commit (the caller's)."""
    for lote in partir(lineas, 1000):
        await session.execute(insert(TrasladoLinea).values([
            {"id": linea_id, **datos} for linea_id, datos in lote.items()]))
