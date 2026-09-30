"""
Motored Pedidos F3 "Motor" (ADR-2) — `calcular_sucursal`: de las entradas de
UNA sucursal a líneas de pedido, resumen por clase y advertencias.

Orden de las etapas:

1. Ventana y divisor. Divisor 0 (sucursal sin ningún mes completo operado)
   -> `OMITIDA` con A-CORRIDA-102 (decisión #14).
2. Consolidación de sustituidas (S3), sólo con `consolidar_sustituidas`
   ON; con el switch OFF es identidad.
3. Universo: referencias con venta neta > 0 en algún mes cerrado operado.
   Nunca entran por stock, tránsito, backorder, demanda perdida ni mes en
   curso.
4. Serie de demanda y N (divisor cerrado, decisión #5 y §6.4.5).
5. ABC (sobre todo el universo), FMS y clase.
6. Cobertura, stock objetivo, pedido y valores derivados.
7. Puntos y estado de quiebre.
8. Resumen por clase.

El mes en curso (M0) sólo entra a N con `modo_mes_en_curso` PONDERADO (etapa
4); no cuenta para el universo, FMS ni la omisión. Todo es aritmética exacta
y determinista: el resultado no depende del orden de las entradas.
"""
from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Mapping, Optional, Sequence
from uuid import UUID

from app.motored.services.motor.aritmetica import a_fraccion
from app.motored.services.motor.clasificacion import (
    ItemAbc,
    clase_fms,
    clasificar_abc,
    meses_con_venta,
    ventas_efectivas,
)
from app.motored.services.motor.cobertura import (
    cobertura_actual,
    cobertura_clase,
    punto_maximo,
    punto_minimo,
    stock_objetivo,
)
from app.motored.services.motor.demanda import (
    demanda_con_m0,
    indicadores_informativos,
)
from app.motored.services.motor.mes_en_curso import validar as validar_m0
from app.motored.services.motor.pedido import (
    calcular_pedido,
    cobertura_final,
    inventario_efectivo,
    valor_pedido,
)
from app.motored.services.motor.puntos import estado_quiebre
from app.motored.services.motor.resumen import ResumenSucursal, resumir
from app.motored.services.motor.sustitucion import consolidar
from app.motored.services.motor.tipos import (
    COD_SUCURSAL_OMITIDA,
    COD_SUMA_NO_POSITIVA,
    ESTADO_OK,
    ESTADO_OMITIDA,
    Advertencia,
    AjustesPrueba,
    AtributosSucursal,
    EntradaReferencia,
    LineaExcluida,
    LineaPedido,
    ParametrosMotor,
    Resolucion,
)
from app.motored.services.motor.ventana import Ventana, construir_ventana

Universo = Mapping[
    str, tuple[EntradaReferencia, tuple[Fraction, ...]]
]

MENSAJE_SUMA_NO_POSITIVA = (
    "La suma de la demanda ponderada no es positiva: "
    "no se puede clasificar ABC"
)


@dataclass(frozen=True)
class ResultadoSucursal:
    """Resultado de una sucursal; `lineas` sale en orden ABC.

    `excluidas` son las referencias que salieron del pedido por la
    consolidación de sustituidas (vacío con el switch OFF).
    """

    estado: str
    lineas: tuple[LineaPedido, ...]
    resumen: ResumenSucursal
    advertencias: tuple[Advertencia, ...]
    divisor: int
    excluidas: tuple[LineaExcluida, ...] = ()


def _omitida(sucursal: AtributosSucursal, ventana: Ventana
             ) -> ResultadoSucursal:
    mensaje = (
        f"Sucursal {sucursal.nombre} abrió hace menos de un mes: "
        f"sin historia para calcular el pedido"
    )
    return ResultadoSucursal(
        estado=ESTADO_OMITIDA,
        lineas=(),
        resumen=resumir([]),
        advertencias=(Advertencia(COD_SUCURSAL_OMITIDA, mensaje),),
        divisor=ventana.divisor,
    )


def _universo(entradas: Sequence[EntradaReferencia], ventana: Ventana
              ) -> Universo:
    """`{código: (entrada, ventas efectivas)}` de las que tienen venta > 0."""
    universo = {}
    for entrada in entradas:
        if entrada.codigo in universo:
            raise ValueError(f"referencia repetida: {entrada.codigo}")
        ventas = ventas_efectivas(entrada, ventana)
        if any(v > 0 for v in ventas):
            universo[entrada.codigo] = (entrada, ventas)
    return universo


def _ventana_de(ventana: Ventana, codigo: str,
                ajustes: Optional[AjustesPrueba]) -> Ventana:
    """Ventana con el divisor de prueba de la referencia, si lo hay."""
    if ajustes is None or not ajustes.divisor_por_referencia:
        return ventana
    divisor = ajustes.divisor_por_referencia.get(codigo)
    return ventana if divisor is None else replace(ventana, divisor=divisor)


def _rangos_fisicos(ajustes: Optional[AjustesPrueba]
                    ) -> Optional[Mapping[str, int]]:
    if ajustes is None or ajustes.orden_explicito is None:
        return None
    return {codigo: i for i, codigo in enumerate(ajustes.orden_explicito)}


def _empates_como_excel(ajustes: Optional[AjustesPrueba]) -> bool:
    return ajustes is not None and ajustes.empates_como_excel


@dataclass(frozen=True)
class _Contexto:
    """Lo que comparten todas las líneas de una misma sucursal."""

    ventana: Ventana
    sucursal: AtributosSucursal
    params: ParametrosMotor


def _quiebre(entrada: EntradaReferencia, n: Fraction,
             ventas: Sequence[Fraction], minimo: Fraction, maximo: Fraction,
             params: ParametrosMotor) -> str:
    return estado_quiebre(
        n=n,
        inventario=a_fraccion(entrada.inventario),
        transito=a_fraccion(entrada.transito),
        backorder=a_fraccion(entrada.backorder),
        punto_minimo=minimo,
        punto_maximo=maximo,
        ventas=ventas,
        params=params,
    )


def _linea(ctx: _Contexto, entrada: EntradaReferencia,
           ventas: Sequence[Fraction], n: Fraction, item: ItemAbc,
           fms: str, cobertura: Fraction,
           m0_proyectada: Optional[Fraction]) -> LineaPedido:
    params = ctx.params
    indicadores = indicadores_informativos(entrada, ctx.ventana, params)
    clase = item.clase + fms
    ss = stock_objetivo(n, cobertura)
    y = inventario_efectivo(entrada)
    calculo = calcular_pedido(
        ss, y, a_fraccion(entrada.ajuste), entrada.unidad_empaque,
        params.modo_redondeo,
    )
    precio = None if entrada.precio is None else a_fraccion(entrada.precio)
    minimo = punto_minimo(n, clase, ctx.sucursal, params)
    maximo = punto_maximo(ss)
    return LineaPedido(
        entrada=entrada,
        n=n,
        k_perdida=indicadores.k_perdida,
        l_ultimo_mes=indicadores.l_ultimo_mes,
        m_promedio=indicadores.m_promedio,
        peso=item.peso,
        acumulado=item.acumulado,
        orden_abc=item.orden,
        clase_abc=item.clase,
        clase_fms=fms,
        clase=clase,
        meses_con_venta=meses_con_venta(ventas),
        cobertura=cobertura,
        inventario_efectivo=y,
        stock_objetivo=ss,
        pedido=calculo.pedido,
        valor_pedido=valor_pedido(calculo.pedido, precio),
        cobertura_final=cobertura_final(y, calculo.pedido, n),
        cobertura_actual=cobertura_actual(y, n),
        punto_minimo=minimo,
        punto_maximo=maximo,
        estado_quiebre=_quiebre(entrada, n, ventas, minimo, maximo, params),
        advertencias=calculo.advertencias,
        venta_m0_proyectada=m0_proyectada,
    )


def _demandas(universo: Universo, ctx: _Contexto,
              ajustes: Optional[AjustesPrueba]
              ) -> tuple[dict[str, Fraction], dict[str, Optional[Fraction]]]:
    """N exacta de cada referencia y su venta de M0 proyectada (o `None`)."""
    demandas, proyectadas = {}, {}
    for codigo, (entrada, _) in universo.items():
        propia = _ventana_de(ctx.ventana, codigo, ajustes)
        demandas[codigo], proyectadas[codigo] = demanda_con_m0(
            entrada, propia, ctx.params
        )
    return demandas, proyectadas


def _lineas(universo: Universo, demandas: Mapping[str, Fraction],
            proyectadas: Mapping[str, Optional[Fraction]],
            abc: Mapping[str, ItemAbc], ctx: _Contexto
            ) -> tuple[LineaPedido, ...]:
    coberturas: dict[str, Fraction] = {}
    lineas = []
    for codigo, (entrada, ventas) in universo.items():
        item = abc[codigo]
        fms = clase_fms(meses_con_venta(ventas), ctx.params)
        clase = item.clase + fms
        if clase not in coberturas:
            coberturas[clase] = cobertura_clase(
                clase, ctx.sucursal, ctx.params
            )
        lineas.append(_linea(
            ctx, entrada, ventas, demandas[codigo], item, fms,
            coberturas[clase], proyectadas[codigo],
        ))
    return tuple(sorted(lineas, key=lambda linea: linea.orden_abc))


def calcular_sucursal(entradas: Sequence[EntradaReferencia],
                      sucursal: AtributosSucursal, params: ParametrosMotor,
                      resoluciones: Optional[Mapping[UUID, Resolucion]] = None,
                      *, ajustes_prueba: Optional[AjustesPrueba] = None
                      ) -> ResultadoSucursal:
    """Calcula el pedido de una sucursal; ver el docstring del módulo.

    `resoluciones` (de `resolver_cadenas`) sólo se usa con
    `consolidar_sustituidas` ON.
    """
    validar_m0(params)
    ventana = construir_ventana(sucursal.fecha_corte, sucursal.fecha_apertura)
    if ventana.sin_historia:
        return _omitida(sucursal, ventana)
    ctx = _Contexto(ventana, sucursal, params)
    consolidacion = consolidar(entradas, resoluciones, ventana, params)
    universo = _universo(consolidacion.entradas, ventana)
    demandas, proyectadas = _demandas(universo, ctx, ajustes_prueba)
    abc = clasificar_abc(
        demandas, params, desempate=_rangos_fisicos(ajustes_prueba),
        empates_como_excel=_empates_como_excel(ajustes_prueba),
    )
    lineas = _lineas(universo, demandas, proyectadas, abc.items, ctx)
    advertencias = consolidacion.advertencias + (
        (Advertencia(COD_SUMA_NO_POSITIVA, MENSAJE_SUMA_NO_POSITIVA),)
        if abc.suma_no_positiva else ()
    )
    return ResultadoSucursal(
        estado=ESTADO_OK,
        lineas=lineas,
        resumen=resumir(
            (linea.clase, linea.pedido, linea.valor_pedido)
            for linea in lineas
        ),
        advertencias=advertencias,
        divisor=ventana.divisor,
        excluidas=consolidacion.excluidas,
    )
