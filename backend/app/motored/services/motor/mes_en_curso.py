"""
Motored Pedidos F3 "Motor" (ADR-12, decisión #15) — mes en curso (M0) en modo
PONDERADO, detrás del switch `modo_mes_en_curso` (EXCLUIDO por defecto).

Con d = días transcurridos de M0, D = días del mes y d0 = demanda de M0 (la
venta más, con el switch de demanda perdida ON, la pérdida por su factor):

    d0_proy = d0 * D / d
    si tope > 0: d0_proy = min(d0_proy, d0 + tope * max(d1, d2, d3))
    w0 = 7 * min(1, d / D)
    N = (suma(peso_i * d_i) + d0_proy * w0) / (divisor cerrado + w0)

El divisor cerrado es el dinámico de la sucursal (§6.4.5) y `w0` se le suma.
Todo es `Fraction`: D/d, 7d/D y divisor + w0 nunca se cuantizan. Una demanda
negativa se proyecta tal cual. M0 nunca cuenta para FMS, universo ni omisión.

El motor no conoce la base de datos: `d` llega ya resuelto. Aquí vive también
`resolver_mes_en_curso`, la regla pura que decide el modo efectivo a partir de
la fecha de la última venta detectada (A-CORRIDA-105/106); el cargador de S5
sólo aporta ese dato.
"""
import calendar
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from typing import Optional, Sequence

from app.motored.services.motor.aritmetica import a_fraccion
from app.motored.services.motor.tipos import (
    COD_MES_EN_CURSO_CORTO,
    COD_MES_EN_CURSO_NO_DISPONIBLE,
    Advertencia,
    EntradaReferencia,
    MesEnCurso,
    ModoMesEnCurso,
    ParametrosMotor,
)

PESO_M0_BASE = 7
MESES_PARA_TOPE = 3


@dataclass(frozen=True)
class AporteM0:
    """Lo que M0 suma a N: demanda proyectada y su peso `w0`."""

    proyectada: Fraction
    peso: Fraction


def activo(params: ParametrosMotor) -> bool:
    """M0 participa sólo con el modo PONDERADO efectivo."""
    mes = params.mes_en_curso
    return mes is not None and mes.modo == "PONDERADO"


def validar(params: ParametrosMotor) -> None:
    """Rechaza d o D fuera de 1 <= d <= D y un tope negativo (sólo activo)."""
    if not activo(params):
        return
    mes = params.mes_en_curso
    if not 1 <= mes.dias_transcurridos <= mes.dias_del_mes:
        raise ValueError(
            f"mes en curso inválido: d={mes.dias_transcurridos}, "
            f"D={mes.dias_del_mes} (se exige 1 <= d <= D)"
        )
    if a_fraccion(mes.tope) < 0:
        raise ValueError("tope_proyeccion_mes_actual no puede ser negativo")


def peso_m0(mes: MesEnCurso) -> Fraction:
    """w0 = 7 * min(1, d / D)."""
    avance = Fraction(mes.dias_transcurridos, mes.dias_del_mes)
    return PESO_M0_BASE * min(Fraction(1), avance)


def demanda_m0(entrada: EntradaReferencia, params: ParametrosMotor
               ) -> Fraction:
    """d0 = venta de M0 (+ pérdida x factor con el switch ON)."""
    demanda = a_fraccion(entrada.venta_m0 or 0)
    if params.incluir_demanda_perdida:
        factor = a_fraccion(params.factor_demanda_perdida)
        demanda += a_fraccion(entrada.perdida_m0 or 0) * factor
    return demanda


def proyectar(d0: Fraction, serie_cerrada: Sequence[Fraction],
              mes: MesEnCurso) -> Fraction:
    """d0 * D / d, limitada por el tope si éste es mayor que cero."""
    proyectada = d0 * Fraction(mes.dias_del_mes, mes.dias_transcurridos)
    tope = a_fraccion(mes.tope)
    if tope > 0:
        recientes = serie_cerrada[-MESES_PARA_TOPE:]
        proyectada = min(proyectada, d0 + tope * max(recientes))
    return proyectada


def aporte_m0(entrada: EntradaReferencia, serie_cerrada: Sequence[Fraction],
              params: ParametrosMotor) -> Optional[AporteM0]:
    """Aporte de M0 a N, o `None` cuando M0 está excluido."""
    if not activo(params):
        return None
    mes = params.mes_en_curso
    d0 = demanda_m0(entrada, params)
    return AporteM0(proyectar(d0, serie_cerrada, mes), peso_m0(mes))


@dataclass(frozen=True)
class ResolucionMesEnCurso:
    """Modo efectivo de la corrida: `mes_en_curso` nulo significa EXCLUIDO."""

    mes_en_curso: Optional[MesEnCurso]
    advertencia: Optional[Advertencia] = None


def _excluido(codigo: str, mensaje: str) -> ResolucionMesEnCurso:
    return ResolucionMesEnCurso(None, Advertencia(codigo, mensaje))


def resolver_mes_en_curso(
    modo: ModoMesEnCurso, fecha_corte: date,
    fecha_ultima_venta: Optional[date], tope: Fraction, min_dias: int,
) -> ResolucionMesEnCurso:
    """Decide el modo efectivo; los respaldos equivalen a EXCLUIDO.

    `fecha_ultima_venta` es el máximo `fecha_max_detectada` de las cargas de
    VENTAS que cubren M0 (`None` si no hay carga o es anterior al cambio de
    ingesta). d = min(corte, última venta) - primer día de M0 + 1.
    """
    if modo != "PONDERADO":
        return ResolucionMesEnCurso(None)
    if fecha_ultima_venta is None:
        return _excluido(
            COD_MES_EN_CURSO_NO_DISPONIBLE,
            "Sin ventas del mes en curso: excluido del cálculo",
        )
    primero = fecha_corte.replace(day=1)
    dias = (min(fecha_corte, fecha_ultima_venta) - primero).days + 1
    if dias < 1:
        return _excluido(
            COD_MES_EN_CURSO_NO_DISPONIBLE,
            "Sin ventas del mes en curso: excluido del cálculo",
        )
    if dias < min_dias:
        return _excluido(
            COD_MES_EN_CURSO_CORTO,
            f"Mes en curso con solo {dias} días: excluido del cálculo",
        )
    _, dias_mes = calendar.monthrange(fecha_corte.year, fecha_corte.month)
    return ResolucionMesEnCurso(MesEnCurso("PONDERADO", dias, dias_mes, tope))
