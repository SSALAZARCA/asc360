"""
Motored Pedidos F3 "Motor" (S8b, decisión #16) — sección "Antigüedad de
datos" de los informes del dueño.

Cada corrida congela en `seleccion_datos["antiguedad"]` la carga usada de cada
tipo de insumo: fecha del snapshot, antigüedad al corte, límite aplicado y
fuente de ese límite. Los informes la muestran tal cual para que el dueño vea
qué tan viejos eran los datos. Cuando los insumos vienen de un libro de Excel
(sin cargas) la sección se conserva y explica por qué no hay fechas.
"""
from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping, Optional, Sequence

TIPOS_ANTIGUEDAD = (
    ("inventario", "Inventario"),
    ("backorder", "Backorder"),
    ("facturas", "Facturas de pedidos"),
    ("ingresos", "Ingresos de facturas"),
)
ENCABEZADO_ANTIGUEDAD = (
    "Tipo de dato",
    "Fecha de corte del snapshot usado",
    "Antigüedad (días)",
    "Límite aplicado (días)",
    "Fuente del límite",
)
SIN_DATO = "Sin dato"


@dataclass(frozen=True)
class FilaAntiguedad:
    """Antigüedad de un tipo de insumo al corte de la corrida."""

    tipo: str
    fecha_usada: Optional[date]
    antiguedad_dias: Optional[int]
    limite_dias: Optional[int]
    fuente: str


def _fila(tipo: str, entrada: Optional[Mapping[str, Any]]) -> FilaAntiguedad:
    if not entrada:
        return FilaAntiguedad(tipo, None, None, None, SIN_DATO)
    fecha = entrada.get("fecha_usada")
    return FilaAntiguedad(
        tipo=tipo,
        fecha_usada=None if not fecha else date.fromisoformat(fecha[:10]),
        antiguedad_dias=entrada.get("antiguedad_dias"),
        limite_dias=entrada.get("limite_dias"),
        fuente=str(entrada.get("fuente_limite") or SIN_DATO),
    )


def desde_seleccion(seleccion: Mapping[str, Any]
                    ) -> tuple[FilaAntiguedad, ...]:
    """Filas de los cuatro tipos desde `corrida.seleccion_datos`."""
    bloque = seleccion.get("antiguedad") or {}
    return tuple(
        _fila(nombre, bloque.get(clave)) for clave, nombre in TIPOS_ANTIGUEDAD
    )


def sin_datos(motivo: str) -> tuple[FilaAntiguedad, ...]:
    """Las cuatro filas vacías, con el `motivo` como fuente."""
    return tuple(
        FilaAntiguedad(nombre, None, None, None, motivo)
        for _, nombre in TIPOS_ANTIGUEDAD
    )


def como_filas(filas: Sequence[FilaAntiguedad]) -> list[tuple]:
    """Filas listas para la hoja, en el orden de `ENCABEZADO_ANTIGUEDAD`."""
    return [
        (f.tipo, f.fecha_usada, f.antiguedad_dias, f.limite_dias, f.fuente)
        for f in filas
    ]
