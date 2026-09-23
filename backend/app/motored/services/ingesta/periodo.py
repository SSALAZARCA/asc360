"""
Motored Pedidos — Fase 2 "Ingesta", Phase 5 "ADR-9 Period Module" (PR5)
(sdd/motored-pedidos-ingesta, tasks 5.1/5.2; design ADR-9 "Declared period is
authoritative; file content is the cross-check, not the source").

El owner pidió este chequeo después de que el workbook legado tuviera
etiquetas de mes corridas una columna contra las fechas reales -- el sistema
debe poder DISCREPAR con el usuario, no solo confiar en su declaración
(ADR-9 rationale). El período lo declara el usuario al subir el archivo
(`carga_archivo.periodo_desde/hasta`) y es AUTORITATIVO; el histograma
`filas_por_periodo` que este módulo recibe es evidencia del archivo, nunca
reemplaza al valor declarado.

Puro, sin acceso a DB ni al archivo -- el caller (`services/ingesta/
ventas.py`, en la MISMA pasada streaming que ya arma cada `CargaFilaStaging`,
sin una segunda pasada) construye el histograma y llama a `evaluar_periodo`.

Tabla de decisión (5 filas, design ADR-9):
1. `fuera == 0`                                             -> ACEPTADO, silencioso.
2. `0 < fuera <= tolerancia` Y todo mes fuera es ADYACENTE   -> ADVERTENCIA
   (`A-CARGA-043` por fila, aplicado en otro lado; el resto del archivo aplica).
3. `fuera > tolerancia`                                      -> RECHAZO (`E-CARGA-040`).
4. CUALQUIER mes fuera NO adyacente, sin importar el conteo  -> RECHAZO (`E-CARGA-040`).
5. Un mes declarado con CERO filas                           -> ADVERTENCIA
   (`A-CARGA-044`); coexiste con cualquiera de las 4 anteriores.

La regla 4 se evalúa ANTES que la 3 (design: "adjacency clause catches what
a percentage alone would wave through") -- un mes no-adyacente rechaza el
archivo entero aunque su porcentaje esté debajo de la tolerancia (E3); un
100% adyacente (E1, el bug histórico real) igual rechaza porque excede la
tolerancia, la adyacencia por sí sola no salva un archivo con esa magnitud
de discrepancia.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Mapping, Optional, Set, Tuple

# Tabla "¿Declara?" de ADR-9: el período es parte de la clave natural de la
# tabla de movimiento para estos 4 tipos -- los otros (FACTURAS_PEDIDOS,
# INGRESOS_FACTURAS, MAESTRO_*) no declaran período (ver design, tabla
# completa). Vive acá porque es la fuente de verdad de ADR-9 y la consume
# tanto el gate de claim del supervisor como, más adelante, la capa API
# (Fase 9).
TIPOS_QUE_DECLARAN_PERIODO: frozenset = frozenset(
    {"VENTAS", "INVENTARIO", "BACKORDER", "DEMANDA_PERDIDA"}
)

# Códigos agregados por ADR-9 (design §API). E-CARGA-041/042 los consume la
# capa API de Fase 9 (ausencia de período requerido / período futuro) -- se
# centralizan acá junto al resto para que ADR-9 tenga una única fuente de
# constantes, aunque este módulo no los emita directamente.
CODIGO_PERIODO_NO_COINCIDE = "E-CARGA-040"
CODIGO_PERIODO_REQUERIDO_AUSENTE = "E-CARGA-041"
CODIGO_PERIODO_FUTURO = "E-CARGA-042"
CODIGO_FILA_FUERA_DE_PERIODO = "A-CARGA-043"
CODIGO_PERIODO_SIN_DATOS = "A-CARGA-044"

# Fase 9, task 9.6 (owner decision 2026-09-22): el chequeo "PARCIAL" de la
# tabla ¿Declara?/Cross-check para BACKORDER -- advertir (nunca rechazar)
# cuando una `Fecha Creación` es posterior al `fecha_corte` declarado (un
# backorder no puede haberse creado después del corte). Vive acá junto al
# resto de constantes de ADR-9 aunque quien la EMITE sea `backorder.py`
# (`evaluar_corte_declarado`), mismo criterio que ya documenta este módulo
# para E-CARGA-041/042.
CODIGO_BACKORDER_CORTE_POSTERIOR = "A-CARGA-045"

MesAnio = Tuple[int, int]


class TipoVeredictoPeriodo(str, Enum):
    ACEPTADO = "ACEPTADO"
    ADVERTENCIA = "ADVERTENCIA"
    RECHAZO = "RECHAZO"


@dataclass(frozen=True)
class VeredictoPeriodo:
    """Resultado puro de `evaluar_periodo`. `meses_declarados_sin_datos`
    (regla 5) puede venir poblado junto con CUALQUIER `tipo` -- no es
    mutuamente excluyente con una advertencia o un rechazo por mes fuera de
    período, son chequeos independientes sobre el mismo histograma."""

    tipo: TipoVeredictoPeriodo
    codigo_error: Optional[str] = None
    meses_fuera_adyacentes: Tuple[MesAnio, ...] = field(default_factory=tuple)
    meses_fuera_no_adyacentes: Tuple[MesAnio, ...] = field(default_factory=tuple)
    meses_declarados_sin_datos: Tuple[MesAnio, ...] = field(default_factory=tuple)
    filas_fuera_total: int = 0
    filas_totales: int = 0


def bounds_de_mes(anio: int, mes: int) -> Tuple[date, date]:
    """Primer y último día de `(anio, mes)`, usando `calendar.monthrange`
    para que los meses de 28/29/30/31 días (incluido febrero en año
    bisiesto) salgan correctos sin tabla hardcodeada."""
    ultimo_dia = calendar.monthrange(anio, mes)[1]
    return date(anio, mes, 1), date(anio, mes, ultimo_dia)


def construir_periodo_declarado(
    anio_desde: int,
    mes_desde: int,
    anio_hasta: Optional[int] = None,
    mes_hasta: Optional[int] = None,
) -> Tuple[date, date]:
    """`periodo_desde`/`periodo_hasta` (ADR-9) a partir de mes/año
    declarados por el usuario. Un solo mes es el caso donde `_hasta` no se
    pasa (colapsa a `anio_desde`/`mes_desde`); un seed multi-mes pasa ambos
    extremos explícitos (design "Multi-month seed: supported as a
    first-class case")."""
    anio_hasta = anio_hasta if anio_hasta is not None else anio_desde
    mes_hasta = mes_hasta if mes_hasta is not None else mes_desde
    desde, _ = bounds_de_mes(anio_desde, mes_desde)
    _, hasta = bounds_de_mes(anio_hasta, mes_hasta)
    return desde, hasta


def meses_en_rango(periodo_desde: date, periodo_hasta: date) -> Set[MesAnio]:
    """Conjunto `D` (design) de `(anio, mes)` cubiertos por
    `[periodo_desde, periodo_hasta]`, inclusive en ambos extremos. Un solo
    mes es el caso de un elemento; un seed de 6 meses expande a 6
    elementos, cruzando fin de año sin caso especial."""
    meses: Set[MesAnio] = set()
    anio, mes = periodo_desde.year, periodo_desde.month
    limite = (periodo_hasta.year, periodo_hasta.month)
    while (anio, mes) <= limite:
        meses.add((anio, mes))
        anio, mes = _mes_siguiente(anio, mes)
    return meses


def _mes_anterior(anio: int, mes: int) -> MesAnio:
    return (anio - 1, 12) if mes == 1 else (anio, mes - 1)


def _mes_siguiente(anio: int, mes: int) -> MesAnio:
    return (anio + 1, 1) if mes == 12 else (anio, mes + 1)


def _es_adyacente(mes_anio: MesAnio, meses_declarados: Set[MesAnio]) -> bool:
    """Adyacente = inmediatamente antes del mes MÁS TEMPRANO declarado, o
    inmediatamente después del MÁS TARDÍO -- nunca "dentro" de un hueco de
    un seed multi-mes (esos huecos ya están cubiertos por regla 5, no son
    'fuera de período')."""
    minimo = min(meses_declarados)
    maximo = max(meses_declarados)
    return mes_anio == _mes_anterior(*minimo) or mes_anio == _mes_siguiente(*maximo)


def evaluar_periodo(
    filas_por_periodo: Mapping[MesAnio, int],
    meses_declarados: Set[MesAnio],
    tolerancia_pct: float,
) -> VeredictoPeriodo:
    """Aplica la tabla de decisión de ADR-9 (ver docstring del módulo) sobre
    un histograma YA construido por el caller. Nunca lanza por división por
    cero: un histograma vacío (E6, todas las fechas del archivo eran
    implausibles) no tiene evidencia que contradiga el período declarado, y
    se resuelve ACEPTADO sin evaluar ningún porcentaje."""
    if not meses_declarados:
        raise ValueError("meses_declarados no puede estar vacío -- error de programador.")

    filas_totales = sum(filas_por_periodo.values())
    meses_sin_datos = tuple(
        mes for mes in sorted(meses_declarados) if filas_por_periodo.get(mes, 0) == 0
    )

    fuera = {
        mes: cantidad for mes, cantidad in filas_por_periodo.items() if mes not in meses_declarados
    }
    filas_fuera_total = sum(fuera.values())

    if filas_fuera_total == 0:
        return VeredictoPeriodo(
            tipo=TipoVeredictoPeriodo.ACEPTADO,
            meses_declarados_sin_datos=meses_sin_datos,
            filas_fuera_total=0,
            filas_totales=filas_totales,
        )

    no_adyacentes = tuple(
        sorted(mes for mes in fuera if not _es_adyacente(mes, meses_declarados))
    )
    if no_adyacentes:
        return VeredictoPeriodo(
            tipo=TipoVeredictoPeriodo.RECHAZO,
            codigo_error=CODIGO_PERIODO_NO_COINCIDE,
            meses_fuera_no_adyacentes=no_adyacentes,
            meses_declarados_sin_datos=meses_sin_datos,
            filas_fuera_total=filas_fuera_total,
            filas_totales=filas_totales,
        )

    porcentaje_fuera = (filas_fuera_total / filas_totales) * 100
    if porcentaje_fuera > tolerancia_pct:
        return VeredictoPeriodo(
            tipo=TipoVeredictoPeriodo.RECHAZO,
            codigo_error=CODIGO_PERIODO_NO_COINCIDE,
            meses_declarados_sin_datos=meses_sin_datos,
            filas_fuera_total=filas_fuera_total,
            filas_totales=filas_totales,
        )

    meses_adyacentes = tuple(sorted(fuera.keys()))
    return VeredictoPeriodo(
        tipo=TipoVeredictoPeriodo.ADVERTENCIA,
        meses_fuera_adyacentes=meses_adyacentes,
        meses_declarados_sin_datos=meses_sin_datos,
        filas_fuera_total=filas_fuera_total,
        filas_totales=filas_totales,
    )
