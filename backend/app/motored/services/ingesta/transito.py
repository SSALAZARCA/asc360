"""
Motored Pedidos — Fase 2 "Ingesta", Phase 8 "FACTURAS/INGRESOS + Tránsito"
(PR8) (sdd/motored-pedidos-ingesta, task 8.2; design ADR-2b/ADR-9, spec
"Tránsito cruce by RH document identity").

Cruce §5.6 entre `factura_proveedor_linea` (`facturas.py`, §5.4) e
`ingreso_factura` (`ingresos.py`, §5.5), a nivel de DOCUMENTO
`(prefijo_rh, numero_rh)` -- NUNCA a nivel de línea (spec: "si un RH
ingresó parcialmente, todas sus líneas quedan ingresadas"). Este módulo es
DISTINTO en forma al resto de `services/ingesta/*`: los otros componen
`lector + columnas + resolucion + errores` sobre UN archivo propio; este
recibe agregados YA calculados por el caller (Fase 9, vía `GROUP BY` sobre
`factura_proveedor_linea`/`ingreso_factura`, el mismo criterio "el caller
hace la agregación SQL" que `ventas.aplicar`/`inventario.aplicar` ya usan)
porque cruza DOS tablas que pueden haberse cargado en momentos distintos --
no hay "un archivo" del que este módulo pueda leer directamente.

H3 (`extraer_prefijo_numero_rh`): el regex `^([A-Z]{2})(\\d+)$` sobre el
documento COMPLETO, comparado como (prefijo, entero) -- NUNCA una
extracción de ancho fijo. Es la corrección explícita del spec sobre la
inconsistencia real del Excel (`MID(...;3;8)` en facturas vs
`MID(...;3;6)` en ingresos, spec §5.5 "Inconsistencia del Excel que hay
que corregir"): con documentos de 6 dígitos ambos anchos fijos coinciden,
pero un consecutivo más largo rompería el cruce en silencio. Verificado
contra el workbook real: TODOS los 10 054 documentos de "facturas pedidos"
son de 6 dígitos hoy, así que el caso de más de 6 dígitos no se pudo
confirmar end-to-end contra datos reales este ciclo -- cubierto solo por
el test unitario (H3 explícitamente lo exige incluso sin evidencia real
todavía). Confirmado además contra "ingreso facturas ultimo 45 dias" que
el regex es indispensable: ese archivo trae formatos que NO matchean en
absoluto (`CH-70752`, 474 de 1 395 filas no-blanco) y prefijos distintos de
`RH` (`FE15892`) -- el cruce nunca los toca porque una clave `(prefijo,
numero)` de una factura `RH` jamás colisiona con una de otro prefijo, sin
necesitar un filtro explícito por `prefijo_rh == 'RH'`.

H4 (`calcular_veredicto`): `transito_vencido` cuando `fecha_factura <
fecha_corte - dias_ventana_ingresos` (default 45) Y sigue sin ingreso --
mejora obligatoria sobre el Excel (spec: el archivo de ingresos solo cubre
45 días, así que sin esta regla una factura vieja aparecería "en tránsito"
para siempre). `ingreso_parcial_sospechoso` solo se evalúa cuando SÍ hay
ingreso matcheado (spec: "cuando el valor neto del ingreso difiere del
valor de la factura en más del parámetro tolerancia_ingreso_pct") -- una
factura NUNCA ingresada no es "sospechosa de parcial", es simplemente
tránsito (o vencida). `documento.valor_total == 0` es una guarda explícita
contra división por cero -- nunca debería pasar en datos reales (una
factura de $0 no es un caso de negocio esperado) pero un módulo de
cálculo puro nunca debe poder crashear por eso.

`dias_ventana_ingresos`/`tolerancia_ingreso_pct` son parámetros explícitos
del caller (Fase 9, `parametro_metodologia`), mismo criterio que
`tipos_inventario_incluidos`/`estados_backorder_vigentes` en
`ventas.py`/`backorder.py` -- nunca se leen acá.

`construir_statements_actualizacion`/`aplicar` son deliberadamente UN
`UPDATE` POR DOCUMENTO, no un único statement set-based como el resto de
Fase 2 (ADR-2b): esta operación es un `UPDATE` cruzado sobre filas YA
existentes de `factura_proveedor_linea` (no un `INSERT ... ON CONFLICT`
sobre un `dict` de claves nuevas), y su granularidad natural es el
DOCUMENTO (miles, no cientos de miles) -- sigue siendo órdenes de magnitud
menor que iterar fila por fila. Deliberadamente FUERA de alcance de esta
fase (ver tasks.md Fase 9): la agregación SQL real que produce
`facturas_por_documento`/`ingresos_por_documento`, el wiring a
`JobRunner`/API, y la resolución de `dias_ventana_ingresos`/
`tolerancia_ingreso_pct` desde `parametro_metodologia`.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, NamedTuple, Optional, Tuple

from sqlalchemy import update

from app.motored.models.factura_proveedor_linea import FacturaProveedorLinea

_RH_RE = re.compile(r"^([A-Z]{2})(\d+)$")

ClaveDocumento = Tuple[str, int]


def extraer_prefijo_numero_rh(documento: Optional[str]) -> Optional[ClaveDocumento]:
    """H3: `^([A-Z]{2})(\\d+)$` sobre el documento completo, comparado como
    (prefijo, entero) -- NUNCA `substring`/`MID` de ancho fijo (ver
    docstring del módulo). `None`/vacío/formato inesperado (p.ej. `CH-
    70752`, visto en datos reales) retorna `None`, nunca lanza -- el
    caller (`facturas.py`/`ingresos.py`) lo traduce a `carga_error`, mismo
    contrato de tolerancia por-fila que el resto de Fase 2. Tolerante a
    minúsculas/espacios (`trim()` + `upper()`) -- los documentos reales
    siempre vienen en mayúsculas, pero un transform no debe fallar por una
    variante de casing."""
    if not documento:
        return None
    texto = documento.strip().upper()
    coincidencia = _RH_RE.match(texto)
    if coincidencia is None:
        return None
    return coincidencia.group(1), int(coincidencia.group(2))


class DocumentoFactura(NamedTuple):
    """Agregado de UN documento del lado factura -- ya sumado por el
    caller (`SUM(valor_total)` sobre todas las líneas de
    `factura_proveedor_linea` que comparten `(prefijo_rh, numero_rh)`,
    `MIN(fecha_factura)` como fecha del documento)."""

    valor_total: Decimal
    fecha_factura: date


class VeredictoTransito(NamedTuple):
    ingresada: bool
    transito_vencido: bool
    ingreso_parcial_sospechoso: bool


def calcular_veredicto(
    documento: DocumentoFactura,
    valor_ingreso_neto: Optional[Decimal],
    fecha_corte: date,
    dias_ventana_ingresos: int,
    tolerancia_ingreso_pct: float,
) -> VeredictoTransito:
    """Evalúa UN documento (ver docstring del módulo, H4). `valor_ingreso_
    neto=None` significa que no existe ningún `ingreso_factura` con esa
    misma clave `(prefijo_rh, numero_rh)` -- spec: `ingresada = EXISTE
    ingreso_factura DONDE ...`."""
    ingresada = valor_ingreso_neto is not None

    transito_vencido = False
    if not ingresada:
        limite = fecha_corte - timedelta(days=dias_ventana_ingresos)
        transito_vencido = documento.fecha_factura < limite

    ingreso_parcial_sospechoso = False
    if ingresada and documento.valor_total != 0:
        diferencia_pct = (
            abs(valor_ingreso_neto - documento.valor_total) / abs(documento.valor_total) * 100
        )
        ingreso_parcial_sospechoso = diferencia_pct > Decimal(str(tolerancia_ingreso_pct))

    return VeredictoTransito(
        ingresada=ingresada,
        transito_vencido=transito_vencido,
        ingreso_parcial_sospechoso=ingreso_parcial_sospechoso,
    )


def calcular_veredictos(
    facturas_por_documento: Dict[ClaveDocumento, DocumentoFactura],
    ingresos_por_documento: Dict[ClaveDocumento, Decimal],
    fecha_corte: date,
    dias_ventana_ingresos: int,
    tolerancia_ingreso_pct: float,
) -> Dict[ClaveDocumento, VeredictoTransito]:
    """Aplica `calcular_veredicto` a cada documento de facturas. Una clave
    de `ingresos_por_documento` con un prefijo distinto (`FE`/`CH`/etc.)
    nunca colisiona con una clave `RH` de facturas -- no hace falta filtrar
    por `prefijo_rh == 'RH'` explícitamente, el propio `dict.get` ya lo
    garantiza (ver docstring del módulo)."""
    return {
        clave: calcular_veredicto(
            documento, ingresos_por_documento.get(clave), fecha_corte,
            dias_ventana_ingresos, tolerancia_ingreso_pct,
        )
        for clave, documento in facturas_por_documento.items()
    }


def construir_statements_actualizacion(
    veredictos: Dict[ClaveDocumento, VeredictoTransito],
) -> List[object]:
    """Un `UPDATE` por documento (ver docstring del módulo, nota ADR-2b) --
    cada uno afecta TODAS las líneas de `factura_proveedor_linea` que
    comparten esa clave `(prefijo_rh, numero_rh)` en una sola sentencia."""
    statements = []
    for (prefijo_rh, numero_rh), veredicto in veredictos.items():
        stmt = (
            update(FacturaProveedorLinea)
            .where(FacturaProveedorLinea.prefijo_rh == prefijo_rh)
            .where(FacturaProveedorLinea.numero_rh == numero_rh)
            .values(
                ingresada=veredicto.ingresada,
                transito_vencido=veredicto.transito_vencido,
                ingreso_parcial_sospechoso=veredicto.ingreso_parcial_sospechoso,
            )
        )
        statements.append(stmt)
    return statements


async def aplicar(session, veredictos: Dict[ClaveDocumento, VeredictoTransito]) -> None:
    """Ejecuta un `UPDATE` por documento (ver `construir_statements_
    actualizacion`). No hace `commit()`: responsabilidad del caller
    (Fase 9)."""
    for stmt in construir_statements_actualizacion(veredictos):
        await session.execute(stmt)
