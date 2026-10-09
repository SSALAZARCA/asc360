"""
Motored Pedidos — Fase 2 "Ingesta", Phase 8 "FACTURAS/INGRESOS + Tránsito"
(PR8) (sdd/motored-pedidos-ingesta, task 8.1; design ADR-9, spec
"Tránsito cruce by RH document identity").

Filtro `Estado != 'Anulado'` (decisión del owner, 2026-09-22): el archivo
real trae 4 valores (`Facturado`, `Contabilizado`, `Anulado`, `En
elaboración`, verificado con openpyxl -- 58 de 1 395 filas no-blanco son
`Anulado`). Un `ingreso_factura` anulado NUNCA debe contar como "recibido"
en el cruce de tránsito (`transito.py`): si contara, una factura genuinamente
pendiente aparecería como `ingresada = true` sólo porque un ingreso que
después se anuló coincidió por `(prefijo_rh, numero_rh)` -- exactamente el
"ingreso fantasma" que el cruce existe para prevenir. Filtro de negocio, no
un error de fila: se descarta en silencio, mismo contrato que
`ventas._pasa_filtros_negocio`/`backorder._pasa_filtro_estado`.

Compone `lector` + `columnas` + `errores` (Phase 3) +
`transito.extraer_prefijo_numero_rh` (Phase 8, H3) en el transform de
INGRESOS_FACTURAS. A diferencia de TODOS los demás tipos de Fase 2, este
módulo NO usa `resolucion.py` en absoluto -- ver la nota "sin sucursal ni
referencia" abajo.

Columnas confirmadas contra el workbook real de producción (`PLANTILLA
PEDIDO SEPTIEMBRE.xlsx`, hoja "ingreso facturas ultimo 45 dias", encabezado
en la fila 1, sin filas de título previas): `Nrodocumento`, `Fecha`,
`Estado`, `Dct.referencia`, `Valornetolocal` -- coincide literalmente con
spec §5.5.

**Sin sucursal ni referencia -- hallazgo real contra el archivo, corregido
en la migración `3956c0ebd69c` (ver su docstring para el detalle
completo).** Este archivo es a nivel de DOCUMENTO (una fila por
`Nrodocumento`) y no trae ninguna columna de sucursal ni de parte, a
diferencia de "facturas pedidos". Por eso `sucursal_id`/`referencia_id` se
dejan SIEMPRE en `None` acá -- no es una resolución fallida (no hay
`SUCURSAL_NO_ENCONTRADA`/`REFERENCIA_NO_ENCONTRADA` posibles para este
tipo, porque no hay ninguna columna de la que partir), es la ausencia
estructural de esa dimensión en el archivo. El cruce (§5.6, `transito.py`)
nunca las necesitó de todos modos: matchea únicamente por `(prefijo_rh,
numero_rh)`.

`valor_neto` (`Valornetolocal`) es el campo monetario que `transito.py`
usa para `ingreso_parcial_sospechoso` -- el modelo lo tiene con ese nombre
(no `cantidad`) desde la misma migración, porque este archivo no trae
ninguna columna de cantidad de unidades en absoluto.

Referencias que no son facturas de repuestos (decisión del owner,
2026-10-08, reemplaza la de error de fila): el export real del ERP trae en
`Dct.referencia` (encabezado "Docto. referencia", aceptado como alias en
`columnas.ALIAS_COLUMNAS`) compras de motos (`CH-74745`) y otros documentos
(`OH 1234`, `NRH1234`, `FCI12345`) junto a las facturas HMCL de repuestos
(`RH123456`). Una referencia que, tras `strip()` + `upper()`, no matchea
`^[A-Z]{2}\\d+$` se descarta EN SILENCIO -- sin `carga_error`, igual que una
fila `Anulado` -- y `procesar_fila` devuelve `MarcaIngreso.NO_ES_REPUESTO`
para que el orquestador la cuente en `carga.log["filas_no_repuestos"]`.
Antes era un error de fila `DOCUMENTO_RH_INVALIDO`, que llenaba el informe
con cientos de errores de filas que nunca debían cargarse. Un documento
con prefijo distinto de `RH` pero de formato válido (`FE15892`) SÍ se
stagea igual -- es `transito.py`, no este módulo, quien nunca lo cruza
contra una factura (una clave `('FE', N)` jamás colisiona con `('RH', N)`).

`Estado` se compara sin distinguir mayúsculas ni espacios (`ANULADO`,
` anulado `).

Optional "C.O." column (owner decision 2026-10-08): when the file brings
it, the row's C.O. is matched against `sucursal.codigo_co` (normalized,
case-insensitive, same aliases as VENTAS) and fills `sucursal_id`. An
unknown or empty C.O. leaves it NULL with NO row error, and a file
without the column loads exactly as before. The cruce still matches only
by `(prefijo_rh, numero_rh)`.

Deliberadamente FUERA de alcance de esta fase (ver tasks.md Fase 9):
- Wiring a `JobRunner`/supervisor y a la API — Fase 9.
- El cruce de tránsito en sí — eso es `transito.py`.
"""
from __future__ import annotations

import enum
import uuid
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.motored.models.carga_error import CargaError
from app.motored.models.carga_fila_staging import CargaFilaStaging
from app.motored.models.ingreso_factura import IngresoFactura
from app.motored.services.ingesta import columnas as columnas_mod
from app.motored.services.ingesta import errores as errores_mod
from app.motored.services.ingesta import numeros as numeros_mod
from app.motored.services.ingesta import transito as transito_mod
from app.motored.services.ingesta.lotes import partir
from app.motored.services.ingesta.resolucion import normalizar_codigo_co
from app.motored.services.ingesta.ventas import ALIAS_COLUMNA_CO

# Nombres CANÓNICOS (no normalizados) tal como los espera `columnas.
# construir_mapa_columnas` -- verificados contra el workbook real de
# producción, hoja "ingreso facturas ultimo 45 dias" (ver docstring).
COLUMNAS_ESPERADAS: Tuple[str, ...] = (
    "Nrodocumento", "Fecha", "Estado", "Dct.referencia", "Valornetolocal",
)

CODIGO_FECHA_INVALIDA = "FECHA_INVALIDA"
CODIGO_VALOR_NETO_INVALIDO = "VALOR_NETO_INVALIDO"
# No longer emitted (owner decision 2026-10-08): kept so historical
# `carga_error` rows keep a known code.
CODIGO_DOCUMENTO_RH_INVALIDO = "DOCUMENTO_RH_INVALIDO"

ESTADO_ANULADO = "Anulado"

# Payload key of the resolved store (only when its C.O. matched).
CLAVE_SUCURSAL = "sucursal_id"


class MarcaIngreso(enum.Enum):
    """A row skipped silently that the orchestrator counts."""

    NO_ES_REPUESTO = "no_es_repuesto"


_CLAVE_UPSERT = ("prefijo_rh", "numero_rh")

ResultadoFila = Tuple[Optional[CargaFilaStaging], List[CargaError]]


def _extraer(
    fila_raw: Sequence[Any], mapa: Dict[str, int], nombre: str
) -> Any:
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
    fila_raw: Sequence[Any],
    mapa_columnas: Dict[str, int],
    carga_id: uuid.UUID,
    numero_fila: int,
) -> Tuple[Optional[date], Optional[CargaError]]:
    """`Fecha` no interpretable -- mismo contrato que `facturas.
    _resolver_fecha_o_error`."""
    valor_fecha = _extraer(fila_raw, mapa_columnas, "Fecha")
    fecha = columnas_mod.a_fecha(valor_fecha)
    if fecha is not None:
        return fecha, None
    error = errores_mod.construir_error(
        carga_id, numero_fila, "Fecha", _texto(valor_fecha),
        CODIGO_FECHA_INVALIDA,
        "La fecha de la fila no se pudo interpretar.",
    )
    return None, error


def _resolver_valor_neto_o_error(
    fila_raw: Sequence[Any],
    mapa_columnas: Dict[str, int],
    carga_id: uuid.UUID,
    numero_fila: int,
) -> Tuple[Optional[Decimal], Optional[CargaError]]:
    """`Valornetolocal` vacío, con error de Excel o no numérico -- mismo
    contrato que `facturas._resolver_decimal_o_error`: `carga_error`, nunca
    un cero silencioso (decisión del owner, 2026-09-29)."""
    return numeros_mod.resolver_decimal_o_error(
        _extraer(fila_raw, mapa_columnas, "Valornetolocal"),
        "Valornetolocal", carga_id,
        numero_fila, CODIGO_VALOR_NETO_INVALIDO,
        "El valor neto de la fila no se pudo interpretar como un número.",
    )


def _pasa_filtro_estado(
    fila_raw: Sequence[Any], mapa_columnas: Dict[str, int]
) -> bool:
    """`Estado == 'Anulado'` (sin distinguir mayúsculas, 2026-10-08) se
    descarta -- decisión del owner (2026-09-22): un ingreso anulado NUNCA
    cuenta como "recibido" en el cruce de tránsito (ver docstring del
    módulo). Filtro de negocio, no una fila inválida: nunca genera
    `carga_error` (mismo contrato que `ventas._pasa_filtros_negocio`/
    `backorder._pasa_filtro_estado`)."""
    estado = _texto(_extraer(fila_raw, mapa_columnas, "Estado"))
    return (estado or "").casefold() != ESTADO_ANULADO.casefold()


def tiene_columna_co(mapa_columnas: Dict[str, int]) -> bool:
    """True when the header brings the C.O. column (any alias)."""
    return any(alias in mapa_columnas for alias in ALIAS_COLUMNA_CO)


def _resolver_sucursal_co(
    fila_raw: Sequence[Any],
    mapa_columnas: Dict[str, int],
    sucursal_por_co: Optional[Dict[str, uuid.UUID]],
) -> Optional[uuid.UUID]:
    """Store of the row's C.O.; `None` without the column, with an empty
    cell or with an unknown code (never a row error)."""
    if not sucursal_por_co:
        return None
    for alias in ALIAS_COLUMNA_CO:
        if alias in mapa_columnas:
            codigo = normalizar_codigo_co(
                _extraer(fila_raw, mapa_columnas, alias))
            return sucursal_por_co.get(codigo) if codigo else None
    return None


def _fila_staging(
    carga_id: uuid.UUID, numero_fila: int, lote: int, payload: dict,
    sucursal_id: Optional[uuid.UUID] = None,
) -> CargaFilaStaging:
    """Staging row with no referencia (see module docstring); the store
    only when the C.O. column resolved one."""
    return CargaFilaStaging(
        carga_id=carga_id,
        fila=numero_fila,
        lote=lote,
        payload=payload,
        sucursal_id=sucursal_id,
        referencia_id=None,
    )


def procesar_fila(
    fila_raw: Sequence[Any],
    *,
    numero_fila: int,
    lote: int,
    mapa_columnas: Dict[str, int],
    carga_id: uuid.UUID,
    sucursal_por_co: Optional[Dict[str, uuid.UUID]] = None,
) -> Union[ResultadoFila, MarcaIngreso]:
    """Procesa UNA fila cruda de INGRESOS_FACTURAS: `(fila_staging,
    errores)`, o `MarcaIngreso.NO_ES_REPUESTO` (ver docstring del módulo).
    La sucursal sale solo del C.O. opcional (`sucursal_por_co`)."""
    if not _pasa_filtro_estado(fila_raw, mapa_columnas):
        return None, []

    documento_raw = _texto(_extraer(fila_raw, mapa_columnas, "Dct.referencia"))
    if documento_raw is None:
        # Fila de relleno -- mismo contrato de descarte silencioso que
        # `facturas.procesar_fila` usa para `Factura` ausente.
        return None, []

    documento = transito_mod.extraer_prefijo_numero_rh(documento_raw)
    if documento is None:
        return MarcaIngreso.NO_ES_REPUESTO
    prefijo_rh, numero_rh = documento

    fecha_ingreso, error_fecha = _resolver_fecha_o_error(
        fila_raw, mapa_columnas, carga_id, numero_fila
    )
    if fecha_ingreso is None:
        return None, [error_fecha]

    valor_neto, error_valor = _resolver_valor_neto_o_error(
        fila_raw, mapa_columnas, carga_id, numero_fila
    )
    if valor_neto is None:
        return None, [error_valor]

    payload = {
        "prefijo_rh": prefijo_rh,
        "numero_rh": numero_rh,
        "fecha_ingreso": fecha_ingreso.isoformat(),
        "valor_neto": str(valor_neto),
    }
    sucursal_id = _resolver_sucursal_co(
        fila_raw, mapa_columnas, sucursal_por_co)
    if sucursal_id is not None:
        payload[CLAVE_SUCURSAL] = str(sucursal_id)
    fila = _fila_staging(carga_id, numero_fila, lote, payload, sucursal_id)
    return fila, []


ClaveIngresoDocumento = Tuple[str, int]


def agregar_documentos(
    filas_staging: Sequence[CargaFilaStaging],
) -> Dict[ClaveIngresoDocumento, dict]:
    """Agrega `valor_neto` (ADITIVO, mismo criterio que `ventas.
    agregar_unidades`) por `(prefijo_rh, numero_rh)` -- no observado más de
    una fila por documento en el archivo real, pero la robustez de sumar
    en vez de pisar es gratis y consistente con el resto de Fase 2.
    `fecha_ingreso` se conserva de la última fila procesada para esa
    clave; `sucursal_id`, de la última fila que resolvió una."""
    totales: Dict[ClaveIngresoDocumento, dict] = {}
    for fila in filas_staging:
        payload = fila.payload
        clave: ClaveIngresoDocumento = (
            payload["prefijo_rh"], payload["numero_rh"]
        )
        acumulado = totales.setdefault(
            clave,
            {"valor_neto": Decimal("0"), "fecha_ingreso": None,
             "sucursal_id": None},
        )
        acumulado["valor_neto"] += Decimal(payload["valor_neto"])
        acumulado["fecha_ingreso"] = date.fromisoformat(
            payload["fecha_ingreso"]
        )
        if payload.get(CLAVE_SUCURSAL):
            acumulado["sucursal_id"] = uuid.UUID(payload[CLAVE_SUCURSAL])
    return totales


def construir_statement_upsert(
    consolidado: Dict[ClaveIngresoDocumento, dict], carga_id: uuid.UUID
):
    """`INSERT ... ON CONFLICT DO UPDATE SET valor_neto = EXCLUDED.
    valor_neto` -- NUNCA sumando contra lo ya persistido (REPLACE-not-sum,
    mismo patrón que el resto de Fase 2). `referencia_id` siempre `NULL`;
    `sucursal_id` es la del C.O. (o `NULL`) y también se reemplaza en el
    conflicto. Retorna `None` si no hay nada que aplicar."""
    if not consolidado:
        return None

    valores = [
        {
            "id": uuid.uuid4(),
            "prefijo_rh": prefijo_rh,
            "numero_rh": numero_rh,
            "fecha_ingreso": datos["fecha_ingreso"],
            "sucursal_id": datos.get("sucursal_id"),
            "referencia_id": None,
            "valor_neto": datos["valor_neto"],
            "carga_id": carga_id,
        }
        for (prefijo_rh, numero_rh), datos in consolidado.items()
    ]
    stmt = pg_insert(IngresoFactura).values(valores)
    return stmt.on_conflict_do_update(
        index_elements=list(_CLAVE_UPSERT),
        set_={
            "fecha_ingreso": stmt.excluded.fecha_ingreso,
            "valor_neto": stmt.excluded.valor_neto,
            "sucursal_id": stmt.excluded.sucursal_id,
            "carga_id": stmt.excluded.carga_id,
        },
    )


async def aplicar(
    session,
    consolidado: Dict[ClaveIngresoDocumento, dict],
    carga_id: uuid.UUID,
) -> None:
    """Ejecuta el upsert como sentencias set-based por lotes (ADR-2b; limite de
    parametros de PostgreSQL) -- nunca fila por fila. No hace `commit()`:
    responsabilidad del caller (Fase 9)."""
    for lote in partir(consolidado):
        stmt = construir_statement_upsert(lote, carga_id)
        if stmt is not None:
            await session.execute(stmt)
