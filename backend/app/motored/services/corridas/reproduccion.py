"""
Motored Pedidos F3 "Motor" (sdd/motored-pedidos-motor, S6a, ADR-4, T17/T18):
reproducción pura de una corrida desde lo que quedó guardado.

`reproducir` reconstruye las entradas del motor SOLO con `corrida` (parámetros
y maestro congelados, mes en curso efectivo), `corrida_sucursal` (apertura,
días y nombre) y `corrida_linea` (entradas crudas propias, incluidas las
líneas excluidas y las entradas auxiliares de la consolidación), vuelve a
calcular con el motor puro y compara cada columna de salida con lo guardado.
Nunca lee ventas, inventario, backorder, referencias, sucursales ni
parámetros vivos: por eso un cambio de maestro, la purga del inventario o una
versión nueva de parámetros no alteran el resultado (T18).

Sólo se reproducen las sucursales OK y OMITIDA; las FALLIDA o PENDIENTES no
tienen resultado que comparar. Las filas guardadas SON las entradas, así que
una línea de más o de menos se detecta por el conteo de la sucursal y por el
efecto que tiene en el ABC de las demás.
"""
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Tuple
from uuid import UUID

from sqlalchemy import select

from app.motored.models.corrida import Corrida
from app.motored.models.corrida_linea import CorridaLinea
from app.motored.models.corrida_resumen import CorridaResumen
from app.motored.models.corrida_sucursal import CorridaSucursal
from app.motored.services.corridas import estados
from app.motored.services.corridas import parametros_corrida as pcorr
from app.motored.services.corridas import persistencia as pe
from app.motored.services.motor.motor import calcular_sucursal
from app.motored.services.motor.sustitucion import resolver_cadenas
from app.motored.services.motor.tipos import (
    AtributosSucursal,
    EntradaReferencia,
    ParametrosMotor,
    Resolucion,
)

_CORRIDA = Corrida.__table__
_SUCURSAL = CorridaSucursal.__table__
_LINEA = CorridaLinea.__table__
_RESUMEN = CorridaResumen.__table__
_COLUMNAS_LINEA = [c.key for c in _LINEA.columns if c.key != "id"]
_COLUMNAS_RESUMEN = ("unidades", "referencias", "valor", "porcentaje_peso")
_ESTADOS_REPRODUCIBLES = (estados.SUC_OK, estados.SUC_OMITIDA)
_AUSENTE = "ausente"
_PRESENTE = "presente"


@dataclass(frozen=True)
class Diferencia:
    """Una columna que no coincide. `clave` es el código de la referencia,
    `resumen:<clase>` o `sucursal`."""

    sucursal_id: UUID
    clave: str
    columna: str
    esperado: Any
    almacenado: Any


@dataclass(frozen=True)
class ReporteReproduccion:
    identico: bool
    diferencias: Tuple[Diferencia, ...]


def _como_dict(fila: Any, columnas: Iterable[str]) -> Dict[str, Any]:
    return {columna: getattr(fila, columna) for columna in columnas}


def _diferencias(
    sucursal_id: UUID, clave: str, esperado: Mapping[str, Any],
    almacenado: Mapping[str, Any],
) -> List[Diferencia]:
    return [
        Diferencia(sucursal_id, clave, columna, valor, almacenado[columna])
        for columna, valor in esperado.items()
        if valor != almacenado[columna]
    ]


def _atributos(corrida: Any, fila: Any) -> AtributosSucursal:
    return AtributosSucursal(
        sucursal_id=fila.sucursal_id,
        nombre=fila.parametros["nombre"],
        fecha_corte=corrida.fecha_corte,
        fecha_apertura=fila.fecha_apertura,
        dias_empaque=fila.dias_empaque,
        dias_transito=fila.dias_transito,
        dias_seguridad=fila.dias_seguridad,
        dias_entre_pedidos=fila.dias_entre_pedidos,
    )


def _entradas(lineas: Iterable[Any], fila: Any) -> List[EntradaReferencia]:
    """Las entradas del motor: una por fila guardada más las auxiliares."""
    entradas = [pe.entrada_desde_fila(linea) for linea in lineas]
    entradas += [
        pe.deserializar_entrada(datos)
        for datos in fila.parametros["entradas_auxiliares"]
    ]
    return entradas


def _comparar_lineas(
    sucursal_id: UUID, esperadas: List[Dict[str, Any]], lineas: List[Any],
) -> List[Diferencia]:
    guardadas = {linea.referencia_id: linea for linea in lineas}
    diferencias: List[Diferencia] = []
    for esperada in esperadas:
        clave = esperada["codigo_referencia"]
        guardada = guardadas.get(esperada["referencia_id"])
        if guardada is None:
            diferencias.append(Diferencia(
                sucursal_id, clave, "*", _PRESENTE, _AUSENTE))
            continue
        diferencias += _diferencias(
            sucursal_id, clave, esperada,
            _como_dict(guardada, _COLUMNAS_LINEA))
    return diferencias


def _comparar_resumen(
    sucursal_id: UUID, esperadas: List[Dict[str, Any]], guardadas: List[Any],
) -> List[Diferencia]:
    por_clase = {fila.clase: fila for fila in guardadas}
    diferencias: List[Diferencia] = []
    for esperada in esperadas:
        clave = f"resumen:{esperada['clase']}"
        guardada = por_clase.pop(esperada["clase"], None)
        if guardada is None:
            diferencias.append(Diferencia(
                sucursal_id, clave, "*", _PRESENTE, _AUSENTE))
            continue
        diferencias += _diferencias(
            sucursal_id, clave,
            {c: esperada[c] for c in _COLUMNAS_RESUMEN},
            _como_dict(guardada, _COLUMNAS_RESUMEN))
    diferencias += [
        Diferencia(sucursal_id, f"resumen:{clase}", "*", _AUSENTE, _PRESENTE)
        for clase in por_clase
    ]
    return diferencias


def _reproducir_sucursal(
    corrida: Any, fila: Any, lineas: List[Any], resumen: List[Any],
    motor: ParametrosMotor, resoluciones: Mapping[UUID, Resolucion],
) -> List[Diferencia]:
    atributos = _atributos(corrida, fila)
    entradas = _entradas(lineas, fila)
    resultado = calcular_sucursal(entradas, atributos, motor, resoluciones)
    esperado = pe.armar_filas(
        corrida.id, atributos, entradas, resultado,
        consolidar=motor.consolidar_sustituidas)
    columnas = esperado.sucursal.keys()
    return (
        _diferencias(
            fila.sucursal_id, "sucursal", esperado.sucursal,
            _como_dict(fila, columnas))
        + _comparar_lineas(fila.sucursal_id, esperado.lineas, lineas)
        + _comparar_resumen(fila.sucursal_id, esperado.resumen, resumen)
    )


def _agrupar(filas: Iterable[Any]) -> Dict[UUID, List[Any]]:
    grupos: Dict[UUID, List[Any]] = defaultdict(list)
    for fila in filas:
        grupos[fila.sucursal_id].append(fila)
    return grupos


async def reproducir(db, corrida_id: UUID) -> ReporteReproduccion:
    """Reproduce la corrida desde lo guardado y reporta toda diferencia."""
    corrida = (await db.execute(
        select(_CORRIDA).where(_CORRIDA.c.id == corrida_id))).first()
    if corrida is None:
        raise LookupError(f"la corrida {corrida_id} no existe")
    sucursales = (await db.execute(
        select(_SUCURSAL).where(_SUCURSAL.c.corrida_id == corrida_id)
        .order_by(_SUCURSAL.c.orden))).all()
    lineas = _agrupar((await db.execute(
        select(_LINEA).where(_LINEA.c.corrida_id == corrida_id))).all())
    resumen = _agrupar((await db.execute(
        select(_RESUMEN).where(_RESUMEN.c.corrida_id == corrida_id))).all())
    motor = pcorr.parametros_motor_desde_snapshot(
        corrida.parametros_snapshot, corrida.seleccion_datos)
    resoluciones = (
        resolver_cadenas(pe.maestro_desde_json(corrida.maestro_sustitucion))
        if motor.consolidar_sustituidas else {})
    diferencias: List[Diferencia] = []
    for fila in sucursales:
        if fila.estado not in _ESTADOS_REPRODUCIBLES:
            continue
        diferencias += _reproducir_sucursal(
            corrida, fila, lineas[fila.sucursal_id],
            resumen[fila.sucursal_id], motor, resoluciones)
    return ReporteReproduccion(not diferencias, tuple(diferencias))
