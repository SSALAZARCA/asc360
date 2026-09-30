"""
Motored Pedidos F3 "Motor" (ADR-2) — serie de demanda mensual, demanda
ponderada N e indicadores informativos K/L/M.

La demanda mensual es la venta más, con el switch ON, la demanda perdida por
`factor_demanda_perdida` (por mes de ocurrencia). Con el switch OFF la
pérdida no influye en NADA, ni siquiera en K. Los meses no operados por la
sucursal (divisor dinámico) valen 0. El mes en curso (M0) sólo entra a N
con el modo PONDERADO (`mes_en_curso.py`); con EXCLUIDO no influye.
"""
from dataclasses import dataclass
from fractions import Fraction
from typing import Optional

from app.motored.services.motor.aritmetica import a_fraccion
from app.motored.services.motor.mes_en_curso import AporteM0, aporte_m0
from app.motored.services.motor.tipos import EntradaReferencia, ParametrosMotor
from app.motored.services.motor.ventana import MESES_VENTANA, Ventana


@dataclass(frozen=True)
class Indicadores:
    """Columnas informativas: no influyen en N, clase, cobertura ni pedido."""

    k_perdida: Fraction
    l_ultimo_mes: Fraction
    m_promedio: Fraction


def _validar_seis_meses(entrada: EntradaReferencia) -> None:
    if (
        len(entrada.ventas) != MESES_VENTANA
        or len(entrada.perdidas) != MESES_VENTANA
    ):
        raise ValueError(
            f"{entrada.codigo}: se esperan {MESES_VENTANA} meses de ventas "
            f"y de demanda perdida"
        )


def _perdida_usada(entrada: EntradaReferencia, ventana: Ventana,
                   params: ParametrosMotor) -> tuple[Fraction, ...]:
    if not params.incluir_demanda_perdida:
        return (Fraction(0),) * MESES_VENTANA
    factor = a_fraccion(params.factor_demanda_perdida)
    return tuple(
        a_fraccion(p) * factor if peso else Fraction(0)
        for p, peso in zip(entrada.perdidas, ventana.pesos)
    )


def serie_demanda(entrada: EntradaReferencia, ventana: Ventana,
                  params: ParametrosMotor) -> tuple[Fraction, ...]:
    """Demanda mensual d_i (M6..M1) tal como la usa el motor."""
    _validar_seis_meses(entrada)
    perdida = _perdida_usada(entrada, ventana, params)
    return tuple(
        (a_fraccion(v) if peso else Fraction(0)) + p
        for v, p, peso in zip(entrada.ventas, perdida, ventana.pesos)
    )


def demanda_ponderada(serie: tuple[Fraction, ...], ventana: Ventana,
                      m0: Optional[AporteM0] = None) -> Fraction:
    """N = (sum(peso_i * d_i) [+ d0_proy * w0]) / (divisor [+ w0]), exacto.

    Sin `m0` es el N de meses cerrados. Divisor 0 no tiene N.
    """
    if ventana.sin_historia:
        raise ValueError("divisor 0: la sucursal debe omitirse (OMITIDA)")
    numerador = sum(p * d for p, d in zip(ventana.pesos, serie))
    divisor = Fraction(ventana.divisor)
    if m0 is not None:
        numerador += m0.proyectada * m0.peso
        divisor += m0.peso
    return numerador / divisor


def demanda_con_m0(entrada: EntradaReferencia, ventana: Ventana,
                   params: ParametrosMotor
                   ) -> tuple[Fraction, Optional[Fraction]]:
    """(N, venta de M0 proyectada); la proyección es `None` sin M0."""
    serie = serie_demanda(entrada, ventana, params)
    m0 = aporte_m0(entrada, serie, params)
    proyectada = None if m0 is None else m0.proyectada
    return demanda_ponderada(serie, ventana, m0), proyectada


def indicadores_informativos(entrada: EntradaReferencia, ventana: Ventana,
                             params: ParametrosMotor) -> Indicadores:
    """K = pérdida usada en la ventana; L = demanda de M1; M = media de 6."""
    serie = serie_demanda(entrada, ventana, params)
    k = sum(_perdida_usada(entrada, ventana, params), Fraction(0))
    return Indicadores(
        k_perdida=k,
        l_ultimo_mes=serie[-1],
        m_promedio=sum(serie, Fraction(0)) / MESES_VENTANA,
    )
