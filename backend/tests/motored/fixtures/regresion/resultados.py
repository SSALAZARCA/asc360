"""
Motored Pedidos F3 "Motor" (S8b) — resultados del motor sintéticos para los
tests de los informes de Excel. Sólo datos inventados y la fila patrón §10.1.
"""
from datetime import date
from uuid import UUID

from app.motored.services.motor.motor import calcular_sucursal
from app.motored.services.motor.sustitucion import resolver_cadenas
from app.motored.services.motor.tipos import NodoMaestro
from tests.motored.fixtures.motor.constructores import (
    atributos,
    entrada,
    fila_patron,
    parametros_legacy,
)

CORTE = date(2026, 9, 21)
ID_VIEJA = UUID(int=1)
ID_NUEVA = UUID(int=2)


def resultado_patron(nombre: str = "MANIZALES AV SANTANDER"):
    """Sucursal con la fila patrón: pedido 50, valor 23 037.50, clase CF."""
    sucursal = atributos(nombre=nombre, fecha_corte=CORTE)
    resultado = calcular_sucursal(
        [fila_patron()], sucursal, parametros_legacy()
    )
    return sucursal, resultado


def resultado_omitida(nombre: str = "SUCURSAL NUEVA"):
    """Sucursal abierta en el mes en curso: OMITIDA con A-CORRIDA-102."""
    sucursal = atributos(
        nombre=nombre, fecha_corte=CORTE, fecha_apertura=date(2026, 9, 5)
    )
    resultado = calcular_sucursal(
        [fila_patron()], sucursal, parametros_legacy()
    )
    return sucursal, resultado


def resultado_con_sustitucion():
    """REF-A (vieja) cede su demanda a REF-B: A sale como SUSTITUIDA."""
    vieja = entrada(
        (5, 0, 3, 0, 2, 4), codigo="REF-A", referencia_id=ID_VIEJA,
        inventario=2,
    )
    nueva = entrada(
        (1, 1, 1, 1, 1, 1), codigo="REF-B", referencia_id=ID_NUEVA,
        precio="10.50",
    )
    maestro = {ID_VIEJA: NodoMaestro(ID_VIEJA, False, ID_NUEVA)}
    sucursal = atributos(nombre="SUCURSAL CONSOLIDADA", fecha_corte=CORTE)
    resultado = calcular_sucursal(
        [vieja, nueva], sucursal,
        parametros_legacy(consolidar_sustituidas=True),
        resolver_cadenas(maestro),
    )
    return sucursal, resultado
