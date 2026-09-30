"""
Motored Pedidos F3 "Motor" (S8b, ADR-10, spec Domain 4 nivel B) — pipeline.

El nivel B pasa los archivos revisados por la ingesta real de F2 a una base de
pruebas, corre una corrida con todos los switches apagados y compara:

1. primero las ENTRADAS de cada referencia (E:J ventas, T precio, U unidad,
   V inventario, W tránsito, X backorder) contra el Excel revisado: una
   divergencia de entradas se reporta antes que cualquier salida;
2. después las SALIDAS, que son el motor sobre las entradas de la aplicación
   comparado con el Excel con las reglas del A2 (divisor 21, orden propio).

La Z sale del Excel (sólo el arnés: en F3 la base guarda Z = 0). Toda
diferencia lleva una categoría de la taxonomía; las de entradas (T6, T7, T8)
sólo entran por el archivo de aceptaciones `{código: categoría}` y, si hay
entradas distintas, el movimiento de las demás filas es cascada (T2).

Este módulo es puro: recibe las entradas ya leídas (`EntradasApp`). La lectura
de la corrida en la base está en `nivel_b_db`.
"""
from dataclasses import dataclass, replace
from typing import Mapping, Optional, Sequence

from app.motored.herramientas.regresion.comparador import (
    AUSENTE,
    PRESENTE,
    Diferencia,
    InsumosNivel,
    ResultadoNivel,
    ejecutar_salidas_nivel_b,
    nueva_diferencia,
    verificar_precondiciones,
)
from app.motored.herramientas.regresion.extractor_excel import (
    FilaExcel,
    LecturaExcel,
)
from app.motored.herramientas.regresion.taxonomia import (
    SIN_CATEGORIA,
    aplicar_aceptacion,
)
from app.motored.services.motor.tipos import (
    AtributosSucursal,
    EntradaReferencia,
    ParametrosMotor,
)

COLUMNA_FILA = "FILA"
COLUMNAS_VENTAS = ("E", "F", "G", "H", "I", "J")
MUESTRA_DIFERENCIAS = 5


@dataclass(frozen=True)
class EntradasApp:
    """Lo que la aplicación cargó y usó para UNA sucursal de la corrida."""

    entradas: tuple[EntradaReferencia, ...]
    atributos: AtributosSucursal
    params: ParametrosMotor


@dataclass(frozen=True)
class ResultadoNivelB:
    """Entradas primero, salidas después; `paso` exige las dos sin
    diferencias sin categoría."""

    sucursal: str
    filas_excel: int
    filas_app: int
    entradas: tuple[Diferencia, ...]
    salidas: ResultadoNivel
    reproduccion_identica: Optional[bool] = None

    @property
    def entradas_pasan(self) -> bool:
        return all(d.categoria != SIN_CATEGORIA for d in self.entradas)

    @property
    def paso(self) -> bool:
        return self.entradas_pasan and self.salidas.paso


def _pares_entrada(fila: FilaExcel, entrada: EntradaReferencia) -> list:
    """`(columna, valor Excel, valor de la aplicación)` de los insumos."""
    return [
        *zip(COLUMNAS_VENTAS, fila.ventas, entrada.ventas),
        ("T", fila.precio, entrada.precio),
        ("U", fila.unidad_empaque, entrada.unidad_empaque),
        ("V", fila.inventario, entrada.inventario),
        ("W", fila.transito, entrada.transito),
        ("X", fila.backorder, entrada.backorder),
    ]


def _diferencias_fila(fila: FilaExcel, entrada: EntradaReferencia,
                      aceptaciones: Mapping[str, str]) -> list[Diferencia]:
    categoria = aplicar_aceptacion(SIN_CATEGORIA, fila.codigo, aceptaciones)
    return [
        nueva_diferencia(
            fila.codigo, fila.fila, columna, excel, app, categoria
        )
        for columna, excel, app in _pares_entrada(fila, entrada)
        if excel != app
    ]


def comparar_entradas(lectura: LecturaExcel,
                      entradas: Sequence[EntradaReferencia],
                      aceptaciones: Optional[Mapping[str, str]] = None
                      ) -> tuple[Diferencia, ...]:
    """Diferencias de entradas por fila y de presencia (columna `FILA`)."""
    aceptaciones = aceptaciones or {}
    app = {entrada.codigo: entrada for entrada in entradas}
    diferencias: list[Diferencia] = []
    for fila in lectura.filas:
        entrada = app.pop(fila.codigo, None)
        if entrada is None:
            categoria = aplicar_aceptacion(
                SIN_CATEGORIA, fila.codigo, aceptaciones
            )
            diferencias.append(nueva_diferencia(
                fila.codigo, fila.fila, COLUMNA_FILA, PRESENTE, AUSENTE,
                categoria,
            ))
            continue
        diferencias += _diferencias_fila(fila, entrada, aceptaciones)
    for codigo in app:
        categoria = aplicar_aceptacion(SIN_CATEGORIA, codigo, aceptaciones)
        diferencias.append(nueva_diferencia(
            codigo, None, COLUMNA_FILA, AUSENTE, PRESENTE, categoria
        ))
    return tuple(diferencias)


def _con_z_del_excel(lectura: LecturaExcel,
                     entradas: Sequence[EntradaReferencia]
                     ) -> list[EntradaReferencia]:
    """Inyecta la Z del Excel (sólo arnés: la base guarda Z = 0)."""
    z = {fila.codigo: fila.ajuste for fila in lectura.filas}
    return [replace(e, ajuste=z.get(e.codigo, e.ajuste)) for e in entradas]


def ejecutar_nivel_b(lectura: LecturaExcel, app: EntradasApp,
                     aceptaciones: Optional[Mapping[str, str]] = None,
                     reproduccion_identica: Optional[bool] = None
                     ) -> ResultadoNivelB:
    """Compara entradas y luego salidas del pipeline contra el Excel."""
    verificar_precondiciones(app.params, app.atributos)
    entradas = comparar_entradas(lectura, app.entradas, aceptaciones)
    insumos = InsumosNivel(
        entradas=_con_z_del_excel(lectura, app.entradas),
        atributos=app.atributos,
        params=app.params,
        cascada_externa=bool(entradas),
    )
    salidas = ejecutar_salidas_nivel_b(lectura, insumos, aceptaciones)
    return ResultadoNivelB(
        sucursal=lectura.sucursal.nombre,
        filas_excel=len(lectura.filas),
        filas_app=len(app.entradas),
        entradas=entradas,
        salidas=salidas,
        reproduccion_identica=reproduccion_identica,
    )


def _lineas_diferencias(titulo: str, diferencias: Sequence[Diferencia],
                        paso: bool, muestra: int) -> list[str]:
    lineas = [
        f"{titulo}: {len(diferencias)} diferencias; "
        f"{'PASA' if paso else 'FALLA'}"
    ]
    por_categoria: dict[str, int] = {}
    for d in diferencias:
        por_categoria[d.categoria] = por_categoria.get(d.categoria, 0) + 1
    lineas += [
        f"  {categoria}: {total} diferencias"
        for categoria, total in sorted(por_categoria.items())
    ]
    primero_lo_inexplicado = sorted(
        diferencias, key=lambda d: d.categoria != SIN_CATEGORIA
    )
    lineas += [
        f"    {d.codigo} {d.columna}: Excel {d.valor_excel} aplicación "
        f"{d.valor_motor} [{d.categoria}]"
        for d in primero_lo_inexplicado[:muestra]
    ]
    return lineas


def resumen_texto_b(resultado: ResultadoNivelB,
                    muestra: int = MUESTRA_DIFERENCIAS) -> list[str]:
    """Consola: primero las entradas, después las salidas."""
    lineas = [
        f"Sucursal: {resultado.sucursal} ({resultado.filas_excel} filas en "
        f"el Excel, {resultado.filas_app} en la aplicación)",
        *_lineas_diferencias(
            "B-entradas", resultado.entradas, resultado.entradas_pasan,
            muestra,
        ),
        *_lineas_diferencias(
            "B-salidas", resultado.salidas.diferencias,
            resultado.salidas.paso, muestra,
        ),
    ]
    if resultado.reproduccion_identica is not None:
        estado = "idéntica" if resultado.reproduccion_identica else (
            "CON DIFERENCIAS"
        )
        lineas.append(
            f"Reproducción de la corrida desde su snapshot: {estado}"
        )
    return lineas
