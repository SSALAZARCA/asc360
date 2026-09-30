"""
Motored Pedidos F3 "Motor" (ADR-8, decisiones #10, #12 y #13) — consolidación
de referencias sustituidas, detrás de `consolidar_sustituidas`.

La demanda pertenece a la necesidad, no al número de parte. Con el switch ON
cada referencia inactiva o sustituida se resuelve, siguiendo `sustituida_por`
de forma transitiva y a prueba de ciclos, hasta la sustituta ACTIVA final:

- Sus ventas y su demanda perdida (también las del mes en curso) pasan mes a
  mes a la sustituta; el factor de pérdida se aplica una sola vez, después,
  sobre lo consolidado. La Z manual NO se transfiere.
- Su inventario, tránsito y backorder (V, W, X) se suman a la sustituta, de
  modo que se restan de su pedido, una sola vez.
- La vieja sale del pedido y se lista como `SUSTITUIDA` ("demanda transferida
  a X"). Las que no tienen reemplazo (inactiva sin sustituta, cadena que
  termina en inactiva, ciclo o cadena de más de 50 nodos) se listan como
  `INACTIVA_SIN_REEMPLAZO` ("revisar") y NO influyen en ningún pedido.

Ambos listados se limitan a las referencias con venta en la ventana operada
o con V+W+X > 0 en la sucursal. Nunca se borra nada. Con el switch OFF (o sin
resoluciones) la salida es idéntica a la de un motor sin esta función.

Contrato con el cargador: la sustituta final debe venir en las entradas de la
sucursal aunque no tenga ventas ni stock (con ceros); si falta, la vieja se
trata como sin reemplazo. Las resoluciones salen de `resolver_cadenas`.
"""
from collections import defaultdict
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Iterable, Mapping, Optional, Sequence
from uuid import UUID

from app.motored.services.motor.clasificacion import ventas_efectivas
from app.motored.services.motor.tipos import (
    COD_CADENA_CICLICA,
    MOTIVO_SIN_REEMPLAZO,
    MOTIVO_SUSTITUIDA,
    Advertencia,
    EntradaReferencia,
    LineaExcluida,
    NodoMaestro,
    ParametrosMotor,
    Resolucion,
)
from app.motored.services.motor.ventana import MESES_VENTANA, Ventana

MAX_CADENA = 50
_PROPIA = "PROPIA"


@dataclass(frozen=True)
class Consolidacion:
    """Entradas ya consolidadas más lo que salió del pedido."""

    entradas: tuple[EntradaReferencia, ...]
    excluidas: tuple[LineaExcluida, ...] = ()
    advertencias: tuple[Advertencia, ...] = ()


@dataclass(frozen=True)
class _Destino:
    tipo: str
    final: Optional[EntradaReferencia] = None
    ciclo: bool = False


# --- resolución de cadenas ---------------------------------------------------


def _final(inicio: UUID, final: UUID, cadena: Sequence[UUID]) -> Resolucion:
    motivo = None if final == inicio else MOTIVO_SUSTITUIDA
    return Resolucion(inicio, final, motivo, tuple(cadena))


def _sin_reemplazo(inicio: UUID, cadena: Sequence[UUID],
                   ciclo: bool) -> Resolucion:
    return Resolucion(
        inicio, None, MOTIVO_SIN_REEMPLAZO, tuple(cadena), ciclo
    )


def _resolver(inicio: UUID, maestro: Mapping[UUID, NodoMaestro]
              ) -> Resolucion:
    """Sigue `sustituida_por` desde `inicio` con conjunto de visitados."""
    cadena = [inicio]
    vistos = {inicio}
    nodo = maestro[inicio]
    while nodo.sustituida_por is not None:
        siguiente = nodo.sustituida_por
        if siguiente in vistos or len(cadena) >= MAX_CADENA:
            return _sin_reemplazo(inicio, cadena, ciclo=True)
        cadena.append(siguiente)
        vistos.add(siguiente)
        nodo = maestro.get(siguiente)
        if nodo is None:
            return _final(inicio, siguiente, cadena)
    if not nodo.activa:
        return _sin_reemplazo(inicio, cadena, ciclo=False)
    return _final(inicio, cadena[-1], cadena)


def resolver_cadenas(maestro: Mapping[UUID, NodoMaestro]
                     ) -> dict[UUID, Resolucion]:
    """Resolución de cada referencia del maestro; iterativa y finita."""
    return {ref: _resolver(ref, maestro) for ref in maestro}


# --- fusión de entradas ------------------------------------------------------


def _validar_meses(entrada: EntradaReferencia) -> None:
    if (
        len(entrada.ventas) != MESES_VENTANA
        or len(entrada.perdidas) != MESES_VENTANA
    ):
        raise ValueError(
            f"{entrada.codigo}: se esperan {MESES_VENTANA} meses de ventas "
            f"y de demanda perdida"
        )


def _sumar_meses(series: Iterable[Sequence[Decimal]]
                 ) -> tuple[Decimal, ...]:
    return tuple(sum(mes, Decimal(0)) for mes in zip(*series))


def _sumar_opcional(valores: Iterable[Optional[Decimal]]
                    ) -> Optional[Decimal]:
    presentes = [v for v in valores if v is not None]
    return sum(presentes, Decimal(0)) if presentes else None


def _fusionar(final: EntradaReferencia,
              origenes: Sequence[EntradaReferencia]) -> EntradaReferencia:
    """La sustituta con la demanda y el stock de sus viejas; Z no se suma."""
    if not origenes:
        return final
    todas = (final, *origenes)
    for entrada in todas:
        _validar_meses(entrada)
    return replace(
        final,
        ventas=_sumar_meses(e.ventas for e in todas),
        perdidas=_sumar_meses(e.perdidas for e in todas),
        venta_m0=_sumar_opcional(e.venta_m0 for e in todas),
        perdida_m0=_sumar_opcional(e.perdida_m0 for e in todas),
        inventario=sum((e.inventario for e in todas), Decimal(0)),
        transito=sum((e.transito for e in todas), Decimal(0)),
        backorder=sum((e.backorder for e in todas), Decimal(0)),
    )


# --- clasificación y listado -------------------------------------------------


def _indexar(entradas: Sequence[EntradaReferencia]
             ) -> dict[UUID, EntradaReferencia]:
    por_id: dict[UUID, EntradaReferencia] = {}
    for entrada in entradas:
        if entrada.referencia_id in por_id:
            raise ValueError(f"referencia repetida: {entrada.codigo}")
        por_id[entrada.referencia_id] = entrada
    return por_id


def _destino(entrada: EntradaReferencia,
             resoluciones: Mapping[UUID, Resolucion],
             por_id: Mapping[UUID, EntradaReferencia]) -> _Destino:
    resolucion = resoluciones.get(entrada.referencia_id)
    if resolucion is None or resolucion.motivo is None:
        return _Destino(_PROPIA)
    final = por_id.get(resolucion.final_id) if resolucion.final_id else None
    if final is None:
        return _Destino(MOTIVO_SIN_REEMPLAZO, None, resolucion.ciclo)
    return _Destino(MOTIVO_SUSTITUIDA, final)


def _amerita_listado(entrada: EntradaReferencia, ventana: Ventana) -> bool:
    con_venta = any(v > 0 for v in ventas_efectivas(entrada, ventana))
    stock = entrada.inventario + entrada.transito + entrada.backorder
    return con_venta or stock > 0


def _excluida(entrada: EntradaReferencia, destino: _Destino
              ) -> LineaExcluida:
    final = destino.final
    return LineaExcluida(
        entrada=entrada,
        motivo=destino.tipo,
        sustituta_final_id=None if final is None else final.referencia_id,
        sustituta_final_codigo=None if final is None else final.codigo,
    )


def _aviso_ciclo(entrada: EntradaReferencia) -> Advertencia:
    return Advertencia(
        COD_CADENA_CICLICA,
        f"Referencia {entrada.codigo}: cadena de sustitución cíclica o "
        f"demasiado larga; queda inactiva sin reemplazo, revisar",
    )


def _listar(salientes: Sequence[tuple[EntradaReferencia, _Destino]],
            ventana: Ventana
            ) -> tuple[tuple[LineaExcluida, ...], tuple[Advertencia, ...]]:
    """Listado ordenado por código y avisos de ciclo de las listadas."""
    listadas = sorted(
        (par for par in salientes if _amerita_listado(par[0], ventana)),
        key=lambda par: par[0].codigo,
    )
    excluidas = tuple(_excluida(e, d) for e, d in listadas)
    avisos = tuple(_aviso_ciclo(e) for e, d in listadas if d.ciclo)
    return excluidas, avisos


def consolidar(entradas: Sequence[EntradaReferencia],
               resoluciones: Optional[Mapping[UUID, Resolucion]],
               ventana: Ventana, params: ParametrosMotor) -> Consolidacion:
    """Pre-paso de `calcular_sucursal`; identidad con el switch OFF."""
    if not params.consolidar_sustituidas or not resoluciones:
        return Consolidacion(tuple(entradas))
    por_id = _indexar(entradas)
    propias = []
    salientes = []
    recibidas = defaultdict(list)
    for entrada in entradas:
        destino = _destino(entrada, resoluciones, por_id)
        if destino.tipo == _PROPIA:
            propias.append(entrada)
            continue
        salientes.append((entrada, destino))
        if destino.final is not None:
            recibidas[destino.final.referencia_id].append(entrada)
    fusionadas = tuple(
        _fusionar(e, recibidas.get(e.referencia_id, ())) for e in propias
    )
    excluidas, avisos = _listar(salientes, ventana)
    return Consolidacion(fusionadas, excluidas, avisos)
