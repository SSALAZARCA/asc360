"""
Motored Pedidos F3 "Motor" (S8b-1, ADR-10) — lectura de una corrida guardada
para los informes y el nivel B: entradas de la aplicación, conjunto comparable
de líneas y libro de corrida. Con una corrida "persistida" en memoria (las
mismas funciones de escritura que el servicio); el camino contra Postgres real
está en `pg_real/test_regresion_nivel_b_pg.py`.
"""
import dataclasses
import uuid
from decimal import Decimal

import pytest

from app.motored.herramientas.regresion.corrida_db import (
    conjunto_de_corrida,
    datos_corrida,
    leer_nivel_b,
)
from app.motored.herramientas.regresion.delta import conjunto_desde_resultado
from app.motored.services.motor.motor import calcular_sucursal
from app.motored.services.motor.sustitucion import resolver_cadenas
from app.motored.services.motor.tipos import NodoMaestro, ParametrosMotor
from tests.motored.fixtures.motor.constructores import (
    atributos,
    entrada,
    fila_patron,
)
from tests.motored.fixtures.regresion.almacen import (
    CORTE,
    almacenar,
    con_sucursal_id,
)

SUC_1, SUC_2 = uuid.UUID(int=301), uuid.UUID(int=302)
ID_A, ID_B = uuid.UUID(int=31), uuid.UUID(int=32)


def _sucursales():
    primera = con_sucursal_id(
        atributos(nombre="UNO", fecha_corte=CORTE), SUC_1
    )
    segunda = con_sucursal_id(
        atributos(nombre="DOS", fecha_corte=CORTE, dias_entre_pedidos="7"),
        SUC_2,
    )
    otra = entrada(
        (9, 8, 7, 6, 5, 4), codigo="REF-X", precio="10", inventario=3
    )
    sola = entrada(
        (1, 0, 2, 0, 3, 0), codigo="REF-Y", precio="5", inventario=4
    )
    patron = dataclasses.replace(fila_patron(), ajuste=Decimal(0))
    return [(primera, [patron, otra]), (segunda, [sola])]


async def test_las_entradas_del_nivel_b_son_las_lineas_guardadas():
    almacen = almacenar(_sucursales())
    leida = await leer_nivel_b(almacen, almacen.corrida.id, SUC_1)
    codigos = sorted(e.codigo for e in leida.app.entradas)
    assert codigos == ["94109-12000S", "REF-X"]
    patron = next(
        e for e in leida.app.entradas if e.codigo == "94109-12000S"
    )
    assert patron.ventas == (102, 112, 108, 105, 74, 59)
    assert (patron.inventario, patron.transito) == (27, 70)
    assert patron.ajuste == 0


async def test_el_nivel_b_recibe_atributos_parametros_y_reproduccion():
    almacen = almacenar(_sucursales())
    leida = await leer_nivel_b(almacen, almacen.corrida.id, SUC_2)
    assert leida.app.atributos.nombre == "DOS"
    assert leida.app.atributos.fecha_corte == CORTE
    assert leida.app.atributos.dias_entre_pedidos == Decimal(7)
    primera = await leer_nivel_b(almacen, almacen.corrida.id, SUC_1)
    assert primera.app.atributos.dias_entre_pedidos == Decimal(30)
    assert leida.app.params == ParametrosMotor()
    assert leida.reproduccion_identica is True
    assert leida.codigo == "PED-2026-S39-001"
    assert leida.seleccion_datos["antiguedad"]["inventario"][
        "antiguedad_dias"] == 2


async def test_una_sucursal_que_no_esta_en_la_corrida_es_un_error():
    almacen = almacenar(_sucursales())
    with pytest.raises(LookupError):
        await leer_nivel_b(almacen, almacen.corrida.id, uuid.UUID(int=999))


async def test_el_conjunto_guardado_coincide_con_el_del_motor():
    sucursales = _sucursales()
    almacen = almacenar(sucursales)
    atributos_uno, entradas = sucursales[0]
    esperado = conjunto_desde_resultado(
        calcular_sucursal(entradas, atributos_uno, ParametrosMotor())
    )
    conjunto = await conjunto_de_corrida(almacen, almacen.corrida.id, SUC_1)
    assert conjunto == esperado
    assert conjunto.lineas["94109-12000S"].pedido == 53


async def test_las_excluidas_no_son_entradas_del_pedido_en_el_nivel_b():
    vieja = entrada((5, 0, 3, 0, 2, 4), codigo="REF-A", referencia_id=ID_A)
    nueva = entrada((1,) * 6, codigo="REF-B", referencia_id=ID_B)
    sucursal = con_sucursal_id(atributos(fecha_corte=CORTE), SUC_1)
    almacen = almacenar(
        [(sucursal, [vieja, nueva])],
        overrides={"consolidar_sustituidas": True},
        nodos=(NodoMaestro(ID_A, False, ID_B),),
    )
    assert len(almacen.lineas) == 2
    leida = await leer_nivel_b(almacen, almacen.corrida.id, SUC_1)
    assert [e.codigo for e in leida.app.entradas] == ["REF-B"]


async def test_el_conjunto_guardado_lista_las_transferidas_con_su_codigo():
    vieja = entrada((5, 0, 3, 0, 2, 4), codigo="REF-A", referencia_id=ID_A)
    nueva = entrada((1,) * 6, codigo="REF-B", referencia_id=ID_B)
    nodos = (NodoMaestro(ID_A, False, ID_B),)
    sucursal = con_sucursal_id(atributos(fecha_corte=CORTE), SUC_1)
    almacen = almacenar(
        [(sucursal, [vieja, nueva])],
        overrides={"consolidar_sustituidas": True}, nodos=nodos,
    )
    esperado = conjunto_desde_resultado(calcular_sucursal(
        [vieja, nueva], sucursal, ParametrosMotor(consolidar_sustituidas=True),
        resolver_cadenas({n.referencia_id: n for n in nodos}),
    ))
    conjunto = await conjunto_de_corrida(almacen, almacen.corrida.id, SUC_1)
    assert conjunto == esperado
    assert [(e.codigo, e.sustituta) for e in conjunto.excluidas] == [
        ("REF-A", "REF-B")
    ]


async def test_datos_corrida_recalcula_cada_sucursal_desde_lo_guardado():
    almacen = almacenar(_sucursales())
    datos = await datos_corrida(almacen, almacen.corrida.id)
    assert datos.titulo == "PED-2026-S39-001"
    assert datos.fecha_corte == CORTE
    assert [s.atributos.nombre for s in datos.sucursales] == ["UNO", "DOS"]
    primera = datos.sucursales[0].resultado
    pedidos = {linea.entrada.codigo: linea.pedido for linea in primera.lineas}
    assert pedidos["94109-12000S"] == 53
    assert set(pedidos) == {"94109-12000S", "REF-X"}
    assert datos.antiguedad[0].antiguedad_dias == 2
    assert datos.antiguedad[1].fuente == "Sin dato"
    assert [a.codigo for a in datos.advertencias] == ["A-CORRIDA-101"]


async def test_una_sucursal_fallida_entra_como_advertencia_de_la_corrida():
    almacen = almacenar(_sucursales())
    fallida = almacen.sucursales[1]
    fallida.estado, fallida.codigo = "FALLIDA", "E-CORRIDA-020"
    fallida.mensaje = "Sin días de empaque ni de tránsito"
    datos = await datos_corrida(almacen, almacen.corrida.id)
    assert [s.atributos.nombre for s in datos.sucursales] == ["UNO"]
    falla = [a for a in datos.advertencias if a.codigo == "E-CORRIDA-020"]
    assert len(falla) == 1
    assert "DOS" in falla[0].mensaje
    assert "Sin días de empaque" in falla[0].mensaje
