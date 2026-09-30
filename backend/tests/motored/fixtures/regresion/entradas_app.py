"""
Motored Pedidos F3 "Motor" (S8b) — entradas de la aplicación sintéticas para
el nivel B: las del libro con Z = 0 (la base no guarda Z en F3) y los cambios
que cada test quiera introducir. Sólo datos inventados.
"""
from dataclasses import replace
from decimal import Decimal
from typing import Mapping, Optional

from app.motored.herramientas.regresion.comparador import (
    atributos_de,
    entradas_de,
)
from app.motored.herramientas.regresion.nivel_b import EntradasApp
from app.motored.services.motor.tipos import ParametrosMotor


def entradas_app(lectura, *, cambios: Optional[Mapping] = None, quitar=(),
                 agregar=(), params: Optional[ParametrosMotor] = None
                 ) -> EntradasApp:
    """Entradas de la aplicación: las del libro, Z = 0 y `cambios`."""
    cambios = cambios or {}
    entradas = [
        replace(e, ajuste=Decimal(0), **cambios.get(e.codigo, {}))
        for e in entradas_de(lectura) if e.codigo not in quitar
    ]
    return EntradasApp(
        entradas=tuple(entradas) + tuple(agregar),
        atributos=atributos_de(lectura),
        params=params or ParametrosMotor(),
    )
