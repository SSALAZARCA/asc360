"""
Motored Pedidos F3 "Motor" (S8b, ADR-10) — lectura de corridas guardadas para
los informes del dueño y el nivel B.

Lo único que este módulo lee es lo que la corrida dejó persistido
(`corrida`, `corrida_sucursal`, `corrida_linea`): las filas guardadas SON las
entradas del motor (ADR-4), así que recalcular desde ellas reproduce la
corrida sin tocar ventas, inventario, referencias ni parámetros vivos.

- `leer_nivel_b`: entradas, atributos y parámetros que la aplicación usó en UNA
  sucursal (lo que compara el nivel B contra el Excel) y si la corrida se
  reproduce idéntica;
- `conjunto_de_corrida`: las líneas guardadas de una sucursal como conjunto
  comparable (nivel C con base de datos);
- `datos_corrida`: todas las sucursales recalculadas desde lo guardado, listas
  para el libro de corrida simple.

Las conversiones de filas son funciones puras (aceptan cualquier objeto con
los atributos de la fila); la lectura de la base es una capa delgada.
"""
from dataclasses import dataclass
from typing import Any, Mapping, Sequence
from uuid import UUID

from sqlalchemy import select

from app.motored.herramientas.regresion.antiguedad import desde_seleccion
from app.motored.herramientas.regresion.delta import (
    ConjuntoLineas,
    Excluida,
    LineaComparable,
)
from app.motored.herramientas.regresion.informe_excel import (
    DatosCorrida,
    SucursalCorrida,
)
from app.motored.herramientas.regresion.nivel_b import EntradasApp
from app.motored.models.corrida import Corrida
from app.motored.models.corrida_linea import CorridaLinea
from app.motored.models.corrida_sucursal import CorridaSucursal
from app.motored.services.corridas import estados
from app.motored.services.corridas import parametros_corrida as pcorr
from app.motored.services.corridas import persistencia as pe
from app.motored.services.corridas import reproduccion as rp
from app.motored.services.corridas import valores
from app.motored.services.motor.motor import calcular_sucursal
from app.motored.services.motor.sustitucion import resolver_cadenas
from app.motored.services.motor.tipos import (
    Advertencia,
    AtributosSucursal,
    EntradaReferencia,
    ParametrosMotor,
    Resolucion,
)

_CORRIDA = Corrida.__table__
_SUCURSAL = CorridaSucursal.__table__
_LINEA = CorridaLinea.__table__
_REPRODUCIBLES = (estados.SUC_OK, estados.SUC_OMITIDA)


@dataclass(frozen=True)
class CorridaLeida:
    """Filas guardadas de una corrida: cabecera, sucursales y sus líneas."""

    corrida: Any
    sucursales: tuple
    lineas: Mapping[UUID, list]


@dataclass(frozen=True)
class CorridaNivelB:
    """Lo que el nivel B necesita de una corrida para UNA sucursal."""

    app: EntradasApp
    codigo: str
    seleccion_datos: Mapping[str, Any]
    reproduccion_identica: bool


# --- Conversión de filas (pura) ---------------------------------------------


def atributos_de_fila(corrida: Any, fila: Any) -> AtributosSucursal:
    """Atributos de la sucursal tal como la corrida los congeló."""
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


def entradas_del_pedido(lineas: Sequence[Any]
                        ) -> tuple[EntradaReferencia, ...]:
    """Entradas de las líneas del pedido (las excluidas no entran)."""
    return tuple(
        pe.entrada_desde_fila(linea) for linea in lineas
        if linea.motivo_exclusion is None
    )


def _todas_las_entradas(lineas: Sequence[Any], fila: Any
                        ) -> list[EntradaReferencia]:
    """Todas las entradas del motor: líneas más auxiliares (consolidación)."""
    entradas = [pe.entrada_desde_fila(linea) for linea in lineas]
    entradas += [
        pe.deserializar_entrada(datos)
        for datos in fila.parametros["entradas_auxiliares"]
    ]
    return entradas


def conjunto_de_filas(lineas: Sequence[Any]) -> ConjuntoLineas:
    """Líneas guardadas como conjunto comparable (mismo formato del motor)."""
    codigos = {
        linea.referencia_id: linea.codigo_referencia for linea in lineas
    }
    pedido, excluidas = {}, []
    for linea in lineas:
        if linea.motivo_exclusion is None:
            pedido[linea.codigo_referencia] = LineaComparable(
                linea.codigo_referencia, linea.clase,
                linea.demanda_ponderada, linea.pedido_sugerido,
                valores.valor_sugerido(linea),
            )
            continue
        destino = linea.sustituta_final_id
        excluidas.append(Excluida(
            linea.codigo_referencia, linea.motivo_exclusion,
            None if destino is None else codigos.get(destino, str(destino)),
        ))
    return ConjuntoLineas(pedido, tuple(excluidas))


# --- Lectura de la base -----------------------------------------------------


async def leer_corrida(db, corrida_id: UUID) -> CorridaLeida:
    """Lee cabecera, sucursales (por orden) y líneas de la corrida."""
    corrida = (await db.execute(
        select(_CORRIDA).where(_CORRIDA.c.id == corrida_id))).first()
    if corrida is None:
        raise LookupError(f"la corrida {corrida_id} no existe")
    sucursales = (await db.execute(
        select(_SUCURSAL).where(_SUCURSAL.c.corrida_id == corrida_id)
        .order_by(_SUCURSAL.c.orden))).all()
    lineas: dict[UUID, list] = {}
    for fila in (await db.execute(
            select(_LINEA).where(_LINEA.c.corrida_id == corrida_id))).all():
        lineas.setdefault(fila.sucursal_id, []).append(fila)
    return CorridaLeida(corrida, tuple(sucursales), lineas)


def _fila_de_sucursal(leida: CorridaLeida, sucursal_id: UUID) -> Any:
    for fila in leida.sucursales:
        if fila.sucursal_id == sucursal_id:
            return fila
    raise LookupError(
        f"la sucursal {sucursal_id} no está en la corrida "
        f"{leida.corrida.codigo}"
    )


def _motor(corrida: Any) -> ParametrosMotor:
    return pcorr.parametros_motor_desde_snapshot(
        corrida.parametros_snapshot, corrida.seleccion_datos
    )


async def leer_nivel_b(db, corrida_id: UUID, sucursal_id: UUID
                       ) -> CorridaNivelB:
    """Entradas, atributos y parámetros de UNA sucursal para el nivel B."""
    leida = await leer_corrida(db, corrida_id)
    fila = _fila_de_sucursal(leida, sucursal_id)
    corrida = leida.corrida
    reporte = await rp.reproducir(db, corrida_id)
    return CorridaNivelB(
        app=EntradasApp(
            entradas=entradas_del_pedido(leida.lineas.get(sucursal_id, [])),
            atributos=atributos_de_fila(corrida, fila),
            params=_motor(corrida),
        ),
        codigo=corrida.codigo,
        seleccion_datos=corrida.seleccion_datos,
        reproduccion_identica=reporte.identico,
    )


async def conjunto_de_corrida(db, corrida_id: UUID, sucursal_id: UUID
                              ) -> ConjuntoLineas:
    """Líneas guardadas de una sucursal como conjunto comparable."""
    leida = await leer_corrida(db, corrida_id)
    _fila_de_sucursal(leida, sucursal_id)
    return conjunto_de_filas(leida.lineas.get(sucursal_id, []))


# --- Libro de corrida -------------------------------------------------------


def _resoluciones(corrida: Any, motor: ParametrosMotor
                  ) -> Mapping[UUID, Resolucion]:
    if not motor.consolidar_sustituidas:
        return {}
    return resolver_cadenas(pe.maestro_desde_json(corrida.maestro_sustitucion))


def _aviso_fallida(nombre: str, fila: Any) -> Advertencia:
    return Advertencia(
        fila.codigo or "SUCURSAL-FALLIDA",
        f"Sucursal {nombre} FALLIDA: {fila.mensaje}",
    )


def _avisos_de_corrida(corrida: Any) -> list[Advertencia]:
    return [
        Advertencia(aviso["codigo"], aviso["mensaje"])
        for aviso in corrida.seleccion_datos.get("advertencias", [])
    ]


async def datos_corrida(db, corrida_id: UUID) -> DatosCorrida:
    """Todas las sucursales de la corrida, recalculadas desde lo guardado."""
    leida = await leer_corrida(db, corrida_id)
    corrida = leida.corrida
    motor = _motor(corrida)
    resoluciones = _resoluciones(corrida, motor)
    avisos = _avisos_de_corrida(corrida)
    sucursales = []
    for fila in leida.sucursales:
        if fila.estado not in _REPRODUCIBLES:
            datos = fila.parametros or {}
            nombre = datos.get("nombre", str(fila.sucursal_id))
            avisos.append(_aviso_fallida(nombre, fila))
            continue
        atributos = atributos_de_fila(corrida, fila)
        entradas = _todas_las_entradas(
            leida.lineas.get(fila.sucursal_id, []), fila
        )
        resultado = calcular_sucursal(
            entradas, atributos, motor, resoluciones
        )
        sucursales.append(SucursalCorrida(atributos, resultado))
    return DatosCorrida(
        titulo=corrida.codigo,
        fecha_corte=corrida.fecha_corte,
        sucursales=tuple(sucursales),
        antiguedad=desde_seleccion(corrida.seleccion_datos),
        advertencias=tuple(avisos),
    )
