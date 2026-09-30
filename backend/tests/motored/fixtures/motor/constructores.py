"""
Motored Pedidos F3 "Motor" (sdd/motored-pedidos-motor, S1-1) — constructores
sintéticos para los tests del motor puro.

Ningún dato confidencial: sólo la fila patrón de la especificación §10.1
(referencia `94109-12000S`) y valores inventados. Los números entran como
`int`/`str`/`Decimal` y se convierten a `Decimal` aquí (nunca `float`), igual
que la frontera real del motor.
"""
from datetime import date
from decimal import Decimal
from typing import Iterable, Optional
from uuid import UUID, uuid4

from app.motored.services.motor.tipos import (
    AtributosSucursal,
    EntradaReferencia,
    ParametrosMotor,
)

CORTE_POR_DEFECTO = date(2026, 9, 29)
VENTAS_PATRON = (102, 112, 108, 105, 74, 59)


def _dec(valor) -> Decimal:
    return Decimal(str(valor))


def _tupla_dec(valores: Iterable) -> tuple:
    return tuple(_dec(v) for v in valores)


def entrada(
    ventas: Iterable = (0, 0, 0, 0, 0, 0),
    perdidas: Iterable = (0, 0, 0, 0, 0, 0),
    *,
    codigo: str = "REF-1",
    referencia_id: Optional[UUID] = None,
    precio=None,
    unidad_empaque: int = 1,
    inventario=0,
    transito=0,
    backorder=0,
    ajuste=0,
    venta_m0=None,
    perdida_m0=None,
) -> EntradaReferencia:
    return EntradaReferencia(
        referencia_id=referencia_id or uuid4(),
        codigo=codigo,
        nombre=None,
        linea_comercial=None,
        precio=None if precio is None else _dec(precio),
        unidad_empaque=unidad_empaque,
        ventas=_tupla_dec(ventas),
        perdidas=_tupla_dec(perdidas),
        venta_m0=None if venta_m0 is None else _dec(venta_m0),
        perdida_m0=None if perdida_m0 is None else _dec(perdida_m0),
        inventario=_dec(inventario),
        transito=_dec(transito),
        backorder=_dec(backorder),
        ajuste=_dec(ajuste),
    )


def atributos(
    *,
    nombre: str = "SUCURSAL DE PRUEBA",
    fecha_corte: date = CORTE_POR_DEFECTO,
    fecha_apertura: Optional[date] = None,
    dias_empaque="3",
    dias_transito="2",
    dias_seguridad="2.5",
    dias_entre_pedidos="30",
) -> AtributosSucursal:
    """Sucursal tipo Manizales: I = 3 + 2 + 2.5 = 7.5 días."""
    return AtributosSucursal(
        sucursal_id=uuid4(),
        nombre=nombre,
        fecha_corte=fecha_corte,
        fecha_apertura=fecha_apertura,
        dias_empaque=_dec(dias_empaque),
        dias_transito=_dec(dias_transito),
        dias_seguridad=_dec(dias_seguridad),
        dias_entre_pedidos=_dec(dias_entre_pedidos),
    )


def parametros_legacy(**cambios) -> ParametrosMotor:
    """Preset legacy (Excel): todos los switches en su valor por defecto."""
    return ParametrosMotor(**cambios)


def fila_patron() -> EntradaReferencia:
    """Fila patrón §10.1: V=27, W=70, X=0, Z=-3, U=1, precio 460.75."""
    return entrada(
        VENTAS_PATRON,
        codigo="94109-12000S",
        precio="460.75",
        inventario=27,
        transito=70,
        backorder=0,
        ajuste=-3,
    )
