"""
Motored Pedidos F3 "Motor" (S8b, ADR-10, decisión #11) — libro de corrida
simple para el dueño.

Hasta que exista la pantalla de F4 el dueño recibe las corridas como Excel.
El libro no compara contra nada: muestra lo que el motor calculó para una
o varias sucursales.

- `Resumen clases`: por sucursal las diez clases (unidades, referencias con
  pedido, valor y peso) y su total; con más de una sucursal, también la red.
- `Antigüedad de datos`: por tipo de insumo, fecha del snapshot usado,
  antigüedad al corte, límite aplicado y fuente (decisión #16).
- Una hoja por sucursal con las columnas A..AD de la hoja `Pedido`.
- `Excluidas`: referencias que salieron del pedido (consolidación).
- `Advertencias`: avisos de la corrida y de cada sucursal.

No es el formato de exportación de HMCL. Se escribe en modo `write_only` por
`LibroSalida`, siempre fuera del repositorio.
"""
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from pathlib import Path
from typing import Iterator, Sequence

from app.motored.herramientas.regresion.antiguedad import (
    ENCABEZADO_ANTIGUEDAD,
    FilaAntiguedad,
    como_filas,
)
from app.motored.herramientas.regresion.libro_excel import LibroSalida
from app.motored.services.motor.motor import ResultadoSucursal
from app.motored.services.motor.resumen import CLASE_TOTAL, FilaResumen
from app.motored.services.motor.tipos import (
    MOTIVO_SUSTITUIDA,
    Advertencia,
    AtributosSucursal,
    LineaExcluida,
    LineaPedido,
)

HOJA_RESUMEN = "Resumen clases"
HOJA_ANTIGUEDAD = "Antigüedad de datos"
HOJA_EXCLUIDAS = "Excluidas"
HOJA_ADVERTENCIAS = "Advertencias"
TODA_LA_CORRIDA = "TODA LA CORRIDA"
TODA_LA_RED = "TODA LA RED"

ENCABEZADO_RESUMEN = (
    "Sucursal", "Clase", "Unidades pedido", "Referencias con pedido",
    "Valor pedido", "% Peso",
)
ENCABEZADO_EXCLUIDAS = (
    "Sucursal", "Referencia", "Motivo", "Sustituta final", "Descripción",
    "Inventario", "Tránsito", "Backorder",
)
ENCABEZADO_ADVERTENCIAS = ("Sucursal", "Código", "Mensaje")
# Columnas A..AD de la hoja `Pedido` de la plantilla, en el mismo orden.
ENCABEZADO_PEDIDO = (
    "Referencia", "Nombre Parte", "Última fecha de entrada",
    "Línea Comercial",
    "Venta mes 6", "Venta mes 5", "Venta mes 4", "Venta mes 3",
    "Venta mes 2", "Venta mes 1",
    "Dem. perdida (K)", "Dem. último mes (L)", "Prom. demanda (M)",
    "Prom. Dem. Pond. (N)", "% Peso", "% Acum",
    "Clasif. Dem. (Unidades)", "Clas. FMS", "Clase",
    "PVD N", "Unidad de empaque", "Inv. fecha corte",
    "Tránsitos / fact. no ingresada", "Backorder", "Inv. Final", "Ajuste",
    "SS", "PEDIDO unds", "Valor pedido", "Cobertura Final",
)


@dataclass(frozen=True)
class SucursalCorrida:
    """Una sucursal de la corrida con su resultado del motor."""

    atributos: AtributosSucursal
    resultado: ResultadoSucursal


@dataclass(frozen=True)
class DatosCorrida:
    """Todo lo que lleva el libro de una corrida.

    `titulo` es el código de la corrida (o la descripción de la fuente) y
    `advertencias` los avisos que no son de una sucursal en particular.
    """

    titulo: str
    fecha_corte: date
    sucursales: tuple[SucursalCorrida, ...]
    antiguedad: tuple[FilaAntiguedad, ...]
    advertencias: tuple[Advertencia, ...] = ()


def _fila_pedido(linea: LineaPedido) -> list:
    entrada = linea.entrada
    return [
        entrada.codigo, entrada.nombre, None, entrada.linea_comercial,
        *entrada.ventas,
        linea.k_perdida, linea.l_ultimo_mes, linea.m_promedio, linea.n,
        linea.peso, linea.acumulado,
        linea.clase_abc, linea.clase_fms, linea.clase,
        entrada.precio, entrada.unidad_empaque, entrada.inventario,
        entrada.transito, entrada.backorder, linea.inventario_efectivo,
        entrada.ajuste, linea.stock_objetivo, linea.pedido,
        linea.valor_pedido, linea.cobertura_final,
    ]


def _fila_resumen(nombre: str, fila: FilaResumen) -> tuple:
    return (
        nombre, fila.clase, fila.unidades, fila.referencias, fila.valor,
        fila.porcentaje_peso,
    )


def _filas_resumen_sucursal(sucursal: SucursalCorrida) -> Iterator[tuple]:
    nombre = sucursal.atributos.nombre
    resumen = sucursal.resultado.resumen
    for fila in (*resumen.filas, resumen.total):
        yield _fila_resumen(nombre, fila)


def _red(sucursales: Sequence[SucursalCorrida]) -> list[FilaResumen]:
    """Suma de todas las sucursales por clase, con el total al final."""
    sumas: dict[str, list] = {}
    for sucursal in sucursales:
        resumen = sucursal.resultado.resumen
        for fila in (*resumen.filas, resumen.total):
            acumulado = sumas.setdefault(
                fila.clase, [Fraction(0), 0, Fraction(0)]
            )
            acumulado[0] += fila.unidades
            acumulado[1] += fila.referencias
            acumulado[2] += fila.valor
    total = sumas.get(CLASE_TOTAL, [Fraction(0), 0, Fraction(0)])
    return [
        FilaResumen(
            clase, unidades, referencias, valor,
            unidades / total[0] if total[0] else Fraction(0),
        )
        for clase, (unidades, referencias, valor) in sumas.items()
    ]


def _filas_resumen(sucursales: Sequence[SucursalCorrida]) -> Iterator[tuple]:
    for sucursal in sucursales:
        yield from _filas_resumen_sucursal(sucursal)
    if len(sucursales) > 1:
        for fila in _red(sucursales):
            yield _fila_resumen(TODA_LA_RED, fila)


def _descripcion(excluida: LineaExcluida) -> str:
    if excluida.motivo == MOTIVO_SUSTITUIDA:
        return f"Demanda transferida a {excluida.sustituta_final_codigo}"
    return "Inactiva sin reemplazo, revisar"


def _filas_excluidas(sucursales: Sequence[SucursalCorrida]
                     ) -> Iterator[tuple]:
    for sucursal in sucursales:
        for excluida in sucursal.resultado.excluidas:
            entrada = excluida.entrada
            yield (
                sucursal.atributos.nombre, entrada.codigo, excluida.motivo,
                excluida.sustituta_final_codigo, _descripcion(excluida),
                entrada.inventario, entrada.transito, entrada.backorder,
            )


def _filas_advertencias(datos: DatosCorrida) -> Iterator[tuple]:
    for aviso in datos.advertencias:
        yield (TODA_LA_CORRIDA, aviso.codigo, aviso.mensaje)
    for sucursal in datos.sucursales:
        for aviso in sucursal.resultado.advertencias:
            yield (sucursal.atributos.nombre, aviso.codigo, aviso.mensaje)


def hoja_antiguedad(libro: LibroSalida, titulo: str, fecha_corte: date,
                    antiguedad: Sequence[FilaAntiguedad]) -> None:
    """Sección "Antigüedad de datos" (decisión #16), común a los informes."""
    libro.hoja(
        HOJA_ANTIGUEDAD, ENCABEZADO_ANTIGUEDAD, como_filas(antiguedad),
        previas=[
            ("Corrida", titulo), ("Fecha de corte", fecha_corte), (),
        ],
    )


def escribir_libro_corrida(datos: DatosCorrida, destino) -> Path:
    """Escribe el libro de la corrida en `destino` (fuera del repositorio)."""
    libro = LibroSalida(destino)
    libro.hoja(
        HOJA_RESUMEN, ENCABEZADO_RESUMEN, _filas_resumen(datos.sucursales)
    )
    hoja_antiguedad(libro, datos.titulo, datos.fecha_corte, datos.antiguedad)
    for sucursal in datos.sucursales:
        libro.hoja(
            sucursal.atributos.nombre, ENCABEZADO_PEDIDO,
            (_fila_pedido(linea) for linea in sucursal.resultado.lineas),
        )
    libro.hoja(
        HOJA_EXCLUIDAS, ENCABEZADO_EXCLUIDAS,
        _filas_excluidas(datos.sucursales),
    )
    libro.hoja(
        HOJA_ADVERTENCIAS, ENCABEZADO_ADVERTENCIAS,
        _filas_advertencias(datos),
    )
    return libro.guardar()
