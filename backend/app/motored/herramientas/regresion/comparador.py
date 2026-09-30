"""
Motored Pedidos F3 "Motor" (S8a, ADR-10, spec Domain 4) — niveles A1 y A2.

Los insumos cacheados del Excel (E:J, T, U, V, W, X, Z y la sucursal de
`Meses de cobertura`) pasan por el motor puro con todos los switches en su
valor legacy y la fecha de apertura de la sucursal nula (se verifica). La Z
del motor es la Z del Excel: sólo aquí, nunca en producción.

- **A1 (fidelidad de fórmulas)**: `AjustesPrueba` reproduce el divisor /18 de
  las filas marcadas y el orden físico del Excel como desempate del ABC. Se
  espera coincidencia exacta en N..AD (|Δ| <= 5e-7 en decimales, 0 en el
  pedido); lo que no coincide lleva categoría o es `SIN_CATEGORIA`.
- **A2 (comportamiento del producto)**: divisor 21 y el orden del motor
  (N descendente, código ascendente). Toda diferencia se clasifica con la
  taxonomía y lo inexplicado hace fallar el nivel.

Columnas comparadas por fila: N, O, P, Q, R, S, Y, AA, AB, AC, AD. Además
los factores de cobertura E3:N3 y el bloque de resumen AA1:AE11. K, L y M
quedan fuera a propósito: el motor las expone como informativas y no
replican el `L = J + K x 10` del Excel.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction
from typing import Mapping, Optional, Sequence
from uuid import NAMESPACE_OID, uuid5

from app.motored.herramientas.regresion.extractor_excel import (
    FilaExcel,
    FilaResumenExcel,
    LecturaExcel,
)
from app.motored.herramientas.regresion.taxonomia import (
    SIN_CATEGORIA,
    ContextoFila,
    aplicar_aceptacion,
    clasificar,
)
from app.motored.services.motor.aritmetica import a_fraccion, cuantizar
from app.motored.services.motor.cobertura import cobertura_clase
from app.motored.services.motor.motor import (
    ResultadoSucursal,
    calcular_sucursal,
)
from app.motored.services.motor.resumen import CLASE_TOTAL, FilaResumen
from app.motored.services.motor.tipos import (
    AjustesPrueba,
    AtributosSucursal,
    EntradaReferencia,
    LineaPedido,
    ParametrosMotor,
)
from app.motored.services.motor.ventana import (
    DIVISOR_BASE,
    MESES_VENTANA,
    construir_ventana,
)

# Mes siguiente a la última columna E:J del Excel (feb..jul -> corte en ago).
FECHA_CORTE_ARNES = date(2026, 8, 15)
DIAS_ENTRE_PEDIDOS_LEGACY = Decimal(30)
DIVISOR_EXCEL_HABITUAL = 21
TOLERANCIA = Fraction(5, 10 ** 7)
SIN_TOLERANCIA = Fraction(0)
ESCALA_INFORME = 10
AUSENTE = "ausente"
PRESENTE = "presente"
COLUMNA_FILA = "FILA"
COLUMNA_COBERTURA = "E3:N3"
ETIQUETA_TOTAL_EXCEL = "Total general"
COLUMNAS_DERIVADAS = frozenset({"S", "AB", "AC", COLUMNA_FILA})
ETIQUETAS_T10 = frozenset({"CF", "CM", CLASE_TOTAL})


class PrecondicionIncumplida(ValueError):
    """El arnés no está en el preset legacy que exige el nivel A."""


@dataclass(frozen=True)
class Diferencia:
    """Un valor del Excel que el motor no reproduce, con su categoría.

    `fila` es la fila del Excel (`None` en cobertura y resumen); `codigo` es
    la referencia, o la clase en cobertura y resumen. Los valores van como
    texto para el informe y `delta` = motor - Excel cuando ambos son números.
    """

    codigo: str
    fila: Optional[int]
    columna: str
    valor_excel: str
    valor_motor: str
    delta: Optional[Decimal]
    categoria: str


@dataclass(frozen=True)
class ResultadoNivel:
    """Resultado de un nivel: conteos y diferencias clasificadas."""

    nivel: str
    filas_excel: int
    filas_exactas: int
    filas_con_diferencias: int
    diferencias: tuple[Diferencia, ...]
    por_categoria: Mapping[str, int]
    filas_por_categoria: Mapping[str, int]
    exacto: bool
    paso: bool


@dataclass(frozen=True)
class _Globales:
    """Hechos de toda la hoja que alimentan el contexto de cada fila."""

    nivel: str
    hay_divisor_distinto: bool
    por_empate: Mapping[str, frozenset[str]]
    cortes_abc: tuple[Fraction, Fraction]


def verificar_precondiciones(params: ParametrosMotor,
                             atributos: AtributosSucursal) -> None:
    """Exige preset legacy, revisión de 30 días y sucursal sin apertura."""
    if params != ParametrosMotor():
        raise PrecondicionIncumplida(
            "Los parámetros no son el preset legacy: el nivel A exige todos "
            "los switches de desviación apagados y el mes en curso EXCLUIDO"
        )
    if atributos.dias_entre_pedidos != DIAS_ENTRE_PEDIDOS_LEGACY:
        raise PrecondicionIncumplida(
            "dias_entre_pedidos debe ser 30 (el Excel usa 1 + I x k / 30)"
        )
    ventana = construir_ventana(
        atributos.fecha_corte, atributos.fecha_apertura
    )
    if ventana.divisor != DIVISOR_BASE:
        raise PrecondicionIncumplida(
            "La fecha de apertura de la sucursal cae dentro de la ventana: "
            "el divisor dinámico cambiaría N respecto del Excel"
        )


def atributos_de(lectura: LecturaExcel,
                 fecha_corte: date = FECHA_CORTE_ARNES) -> AtributosSucursal:
    """Atributos de la sucursal; `fecha_apertura` nula (Manizales)."""
    sucursal = lectura.sucursal
    return AtributosSucursal(
        sucursal_id=uuid5(NAMESPACE_OID, sucursal.nombre),
        nombre=sucursal.nombre,
        fecha_corte=fecha_corte,
        fecha_apertura=None,
        dias_empaque=sucursal.dias_empaque,
        dias_transito=sucursal.dias_transito,
        dias_seguridad=sucursal.dias_seguridad,
        dias_entre_pedidos=DIAS_ENTRE_PEDIDOS_LEGACY,
    )


def entradas_de(lectura: LecturaExcel) -> list[EntradaReferencia]:
    """Una entrada por fila del Excel, con la Z del Excel (sólo arnés).

    La demanda perdida va en cero: con el switch apagado no influye y la K
    del Excel (un total) no se puede repartir por mes.
    """
    sin_perdidas = (Decimal(0),) * MESES_VENTANA
    return [
        EntradaReferencia(
            referencia_id=uuid5(NAMESPACE_OID, fila.codigo),
            codigo=fila.codigo,
            nombre=None,
            linea_comercial=None,
            precio=fila.precio,
            unidad_empaque=fila.unidad_empaque,
            ventas=fila.ventas,
            perdidas=sin_perdidas,
            inventario=fila.inventario,
            transito=fila.transito,
            backorder=fila.backorder,
            ajuste=fila.ajuste,
        )
        for fila in lectura.filas
    ]


def ajustes_orden_fisico(lectura: LecturaExcel) -> AjustesPrueba:
    """Sólo el orden físico del Excel como desempate (sin el /18)."""
    return AjustesPrueba(
        orden_explicito=[fila.codigo for fila in lectura.filas]
    )


def ajustes_a1(lectura: LecturaExcel) -> AjustesPrueba:
    """Divisor por referencia (el /18) y orden físico del Excel."""
    divisores = {
        fila.codigo: fila.divisor
        for fila in lectura.filas
        if fila.divisor not in (None, DIVISOR_EXCEL_HABITUAL)
    }
    return AjustesPrueba(
        divisor_por_referencia=divisores,
        orden_explicito=[fila.codigo for fila in lectura.filas],
    )


def _formato(valor) -> str:
    if valor is None:
        return "nulo"
    if isinstance(valor, str):
        return valor
    return format(cuantizar(Fraction(valor), ESCALA_INFORME), "f")


def _difiere(excel, motor, tolerancia: Optional[Fraction]) -> bool:
    if tolerancia is None or excel is None or motor is None:
        return excel != motor
    return abs(Fraction(motor) - Fraction(excel)) > tolerancia


def _delta(excel, motor) -> Optional[Decimal]:
    if any(v is None or isinstance(v, str) for v in (excel, motor)):
        return None
    return cuantizar(Fraction(motor) - Fraction(excel), ESCALA_INFORME)


def _diferencia(codigo: str, fila: Optional[int], columna: str,
                excel, motor, categoria: str) -> Diferencia:
    return Diferencia(
        codigo=codigo, fila=fila, columna=columna,
        valor_excel=_formato(excel), valor_motor=_formato(motor),
        delta=_delta(excel, motor), categoria=categoria,
    )


def _pares(fila: FilaExcel, linea: LineaPedido) -> list[tuple]:
    """(columna, valor Excel, valor motor, tolerancia) de una fila."""
    return [
        ("N", fila.n, linea.n, TOLERANCIA),
        ("O", fila.peso, linea.peso, TOLERANCIA),
        ("P", fila.acumulado, linea.acumulado, TOLERANCIA),
        ("Q", fila.clase_abc, linea.clase_abc, None),
        ("R", fila.clase_fms, linea.clase_fms, None),
        ("S", fila.clase_estatica, linea.clase, None),
        ("Y", fila.inventario_final, linea.inventario_efectivo, TOLERANCIA),
        ("AA", fila.stock_objetivo, linea.stock_objetivo, TOLERANCIA),
        ("AB", fila.pedido, linea.pedido, SIN_TOLERANCIA),
        ("AC", fila.valor_pedido, linea.valor_pedido, TOLERANCIA),
        ("AD", fila.cobertura_final, linea.cobertura_final, TOLERANCIA),
    ]


def _frontera_medio(linea: LineaPedido) -> bool:
    """El cociente (SS - Y + Z) / U cae exactamente en un .5."""
    unidad = linea.entrada.unidad_empaque
    if unidad <= 0:
        return False
    neto = (
        linea.stock_objetivo - linea.inventario_efectivo
        + a_fraccion(linea.entrada.ajuste)
    )
    return (neto / unidad).denominator == 2


def _otro_lado(fila: FilaExcel, linea: LineaPedido) -> bool:
    """El Excel pidió exactamente una unidad de empaque más o menos."""
    return abs(Fraction(fila.pedido) - linea.pedido) == (
        linea.entrada.unidad_empaque
    )


def _contexto(fila: FilaExcel, linea: LineaPedido,
              globales: _Globales) -> ContextoFila:
    return ContextoFila(
        nivel=globales.nivel,
        divisor_distinto=fila.divisor not in (None, DIVISOR_EXCEL_HABITUAL),
        hay_divisor_distinto=globales.hay_divisor_distinto,
        estatica_inconsistente=(
            fila.clase_estatica != fila.clase_abc + fila.clase_fms
        ),
        u_cero=fila.unidad_empaque <= 0,
        columnas_empate=globales.por_empate.get(fila.codigo, frozenset()),
        frontera_medio=_frontera_medio(linea) and _otro_lado(fila, linea),
        frontera_abc=linea.acumulado in globales.cortes_abc,
    )


def _comparar_fila(fila: FilaExcel, linea: Optional[LineaPedido],
                   globales: _Globales) -> list[Diferencia]:
    if linea is None:
        return [_diferencia(
            fila.codigo, fila.fila, COLUMNA_FILA, PRESENTE, AUSENTE,
            SIN_CATEGORIA,
        )]
    contexto = _contexto(fila, linea, globales)
    return [
        _diferencia(
            fila.codigo, fila.fila, columna, excel, motor,
            clasificar(columna, contexto),
        )
        for columna, excel, motor, tolerancia in _pares(fila, linea)
        if _difiere(excel, motor, tolerancia)
    ]


def _valores_motor(fila: FilaExcel, linea: LineaPedido) -> dict:
    return {columna: motor for columna, _, motor, _ in _pares(fila, linea)}


def _cambios_por_empate(lectura: LecturaExcel, resultado: ResultadoSucursal,
                        referencia: Optional[ResultadoSucursal]
                        ) -> dict[str, frozenset[str]]:
    """Columnas de cada fila que cambian sólo por el desempate del ABC.

    Se compara el motor con su orden (código ascendente) contra el mismo
    motor con el orden físico del Excel: lo que difiere entre ambos lo causa
    únicamente el desempate, y no el divisor.
    """
    if referencia is None:
        return {}
    filas = {fila.codigo: fila for fila in lectura.filas}
    base = {linea.entrada.codigo: linea for linea in referencia.lineas}
    cambios = {}
    for linea in resultado.lineas:
        codigo = linea.entrada.codigo
        propios = _valores_motor(filas[codigo], linea)
        previos = _valores_motor(filas[codigo], base[codigo])
        columnas = frozenset(c for c, v in propios.items() if previos[c] != v)
        if columnas:
            cambios[codigo] = columnas
    return cambios


def _globales(lectura: LecturaExcel, params: ParametrosMotor, nivel: str,
              por_empate: Mapping[str, frozenset[str]]) -> _Globales:
    return _Globales(
        nivel=nivel,
        hay_divisor_distinto=any(
            fila.divisor not in (None, DIVISOR_EXCEL_HABITUAL)
            for fila in lectura.filas
        ),
        por_empate=por_empate,
        cortes_abc=(
            a_fraccion(params.corte_abc_a), a_fraccion(params.corte_abc_b)
        ),
    )


def _comparar_filas(lectura: LecturaExcel, resultado: ResultadoSucursal,
                    globales: _Globales) -> list[Diferencia]:
    lineas = {linea.entrada.codigo: linea for linea in resultado.lineas}
    diferencias = []
    for fila in lectura.filas:
        diferencias += _comparar_fila(fila, lineas.get(fila.codigo), globales)
    return diferencias


def _comparar_coberturas(lectura: LecturaExcel, atributos: AtributosSucursal,
                         params: ParametrosMotor) -> list[Diferencia]:
    diferencias = []
    for clase, excel in lectura.coberturas.items():
        motor = cobertura_clase(clase, atributos, params)
        if _difiere(excel, motor, TOLERANCIA):
            diferencias.append(_diferencia(
                clase, None, COLUMNA_COBERTURA, excel, motor, SIN_CATEGORIA,
            ))
    return diferencias


def _categoria_derivada(filas: Sequence[Diferencia]) -> str:
    """Categoría de los totales: la de las filas que los cambiaron."""
    categorias = {
        d.categoria for d in filas if d.columna in COLUMNAS_DERIVADAS
    }
    if not categorias:
        return SIN_CATEGORIA
    return categorias.pop() if len(categorias) == 1 else "T2"


def _valores_resumen(excel: Optional[FilaResumenExcel],
                     motor: Optional[FilaResumen]) -> list[tuple]:
    """(columna, Excel, motor, tolerancia); `ausente` si falta la fila."""
    def tomar(objeto, campo):
        return AUSENTE if objeto is None else getattr(objeto, campo)

    return [
        ("RES_unidades", tomar(excel, "unidades"),
         tomar(motor, "unidades"), SIN_TOLERANCIA),
        ("RES_referencias", tomar(excel, "referencias"),
         tomar(motor, "referencias"), SIN_TOLERANCIA),
        ("RES_valor", tomar(excel, "valor"),
         tomar(motor, "valor"), TOLERANCIA),
        ("RES_peso", tomar(excel, "peso"),
         tomar(motor, "porcentaje_peso"), TOLERANCIA),
    ]


def _distintos(excel, motor, tolerancia) -> bool:
    if AUSENTE in (excel, motor):
        otro = motor if excel == AUSENTE else excel
        return otro not in (AUSENTE, 0) and otro is not None
    return _difiere(excel, motor, tolerancia)


def _etiquetas_resumen(lectura: LecturaExcel, resultado: ResultadoSucursal
                       ) -> list[str]:
    etiquetas = [r.etiqueta for r in lectura.resumen] + [CLASE_TOTAL]
    etiquetas += [
        f.clase for f in resultado.resumen.filas if f.clase not in etiquetas
    ]
    return etiquetas


def _comparar_resumen(lectura: LecturaExcel, resultado: ResultadoSucursal,
                      derivada: str) -> list[Diferencia]:
    excel = {r.etiqueta: r for r in lectura.resumen}
    if lectura.total is not None:
        excel[CLASE_TOTAL] = lectura.total
    motor = {f.clase: f for f in resultado.resumen.filas}
    motor[CLASE_TOTAL] = resultado.resumen.total
    cf = motor.get("CF")
    sin_cf = "CF" not in excel and cf is not None and (
        cf.unidades != 0 or cf.referencias != 0 or cf.valor != 0
    )
    diferencias = []
    for etiqueta in _etiquetas_resumen(lectura, resultado):
        valores = _valores_resumen(excel.get(etiqueta), motor.get(etiqueta))
        for columna, valor_excel, valor_motor, tolerancia in valores:
            if not _distintos(valor_excel, valor_motor, tolerancia):
                continue
            t10 = sin_cf and (
                columna == "RES_peso" or etiqueta in ETIQUETAS_T10
            )
            diferencias.append(_diferencia(
                etiqueta, None, columna, valor_excel, valor_motor,
                "T10" if t10 else derivada,
            ))
    return diferencias


def _resultado(nivel: str, lectura: LecturaExcel,
               diferencias: Sequence[Diferencia]) -> ResultadoNivel:
    por_fila = [d for d in diferencias if d.fila is not None]
    filas_con = {d.codigo for d in por_fila}
    filas_categoria: dict[str, set[str]] = defaultdict(set)
    for d in por_fila:
        filas_categoria[d.categoria].add(d.codigo)
    por_categoria = Counter(d.categoria for d in diferencias)
    return ResultadoNivel(
        nivel=nivel,
        filas_excel=len(lectura.filas),
        filas_exactas=len(lectura.filas) - len(filas_con),
        filas_con_diferencias=len(filas_con),
        diferencias=tuple(diferencias),
        por_categoria=dict(por_categoria),
        filas_por_categoria={c: len(v) for c, v in filas_categoria.items()},
        exacto=not diferencias,
        paso=SIN_CATEGORIA not in por_categoria,
    )


def _aceptadas(diferencias: Sequence[Diferencia],
               aceptaciones: Mapping[str, str]) -> list[Diferencia]:
    return [
        Diferencia(
            d.codigo, d.fila, d.columna, d.valor_excel, d.valor_motor,
            d.delta, aplicar_aceptacion(d.categoria, d.codigo, aceptaciones),
        )
        for d in diferencias
    ]


def _ejecutar_nivel(lectura: LecturaExcel, nivel: str,
                    aceptaciones: Optional[Mapping[str, str]],
                    ajustes: Optional[AjustesPrueba],
                    referencia: Optional[AjustesPrueba] = None
                    ) -> ResultadoNivel:
    params = ParametrosMotor()
    atributos = atributos_de(lectura)
    verificar_precondiciones(params, atributos)
    entradas = entradas_de(lectura)
    resultado = calcular_sucursal(
        entradas, atributos, params, ajustes_prueba=ajustes
    )
    base = None if referencia is None else calcular_sucursal(
        entradas, atributos, params, ajustes_prueba=referencia
    )
    globales = _globales(
        lectura, params, nivel, _cambios_por_empate(lectura, resultado, base)
    )
    filas = _aceptadas(
        _comparar_filas(lectura, resultado, globales), aceptaciones or {}
    )
    derivada = _categoria_derivada(filas)
    diferencias = (
        filas + _comparar_coberturas(lectura, atributos, params)
        + _comparar_resumen(lectura, resultado, derivada)
    )
    return _resultado(nivel, lectura, diferencias)


def ejecutar_nivel_a1(lectura: LecturaExcel,
                      aceptaciones: Optional[Mapping[str, str]] = None
                      ) -> ResultadoNivel:
    """Nivel A1: divisor por referencia y orden físico del Excel."""
    return _ejecutar_nivel(lectura, "A1", aceptaciones, ajustes_a1(lectura))


def ejecutar_nivel_a2(lectura: LecturaExcel,
                      aceptaciones: Optional[Mapping[str, str]] = None
                      ) -> ResultadoNivel:
    """Nivel A2: divisor 21 siempre y el orden propio del motor."""
    return _ejecutar_nivel(
        lectura, "A2", aceptaciones, None, ajustes_orden_fisico(lectura)
    )
