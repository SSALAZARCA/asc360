"""
Motored Pedidos F3 "Motor" (S8b, ADR-10, spec Domain 4 nivel C) — medición
con base de datos: una corrida escenario REAL por switch.

Sobre una base de pruebas ya cargada con los archivos revisados (por la
ingesta real de F2), corre la corrida base (todo apagado) y, por cada
escenario, una corrida con ESOS overrides (`POST /corridas` los acepta tal
cual) para UNA sucursal. Cada una recorre el pipeline completo (preflight,
cargador, motor, persistencia), así que también miden los switches que actúan
en el cargador (tránsito vencido) o dependen de las cargas (mes en curso).

El preset de producción nunca se escribe: los overrides viven en la corrida
(`es_escenario`) y en su snapshot. Las corridas quedan en la base de pruebas.
"""
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date
from typing import Any, AsyncIterator, Iterable, Mapping, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.motored.herramientas.regresion.corrida_db import (
    CorridaLeida,
    conjunto_de_filas,
    leer_corrida,
)
from app.motored.herramientas.regresion.delta import (
    NOMBRE_BASE,
    ConjuntoLineas,
    Escenario,
    ResultadoEscenario,
    calcular_delta,
)
from app.motored.services.corridas import estados
from app.motored.services.corridas import servicio
from app.motored.services.corridas.codigos import ErrorCorrida

CLAVE_MES = "modo_mes_en_curso"
MODO_PONDERADO = "PONDERADO"


@dataclass(frozen=True)
class MedicionBase:
    """Escenarios medidos y lo que identifica la corrida base."""

    resultados: tuple[ResultadoEscenario, ...]
    codigo_base: str
    sucursal: str
    seleccion_datos: Mapping[str, Any]


@asynccontextmanager
async def sesion_desde_url(url: str) -> AsyncIterator[AsyncSession]:
    """Sesión sobre la base de pruebas indicada (se libera al salir)."""
    motor = create_async_engine(url)
    try:
        async with AsyncSession(motor, expire_on_commit=False) as db:
            yield db
    finally:
        await motor.dispose()


def _verificar_sucursal(leida: CorridaLeida, sucursal_id: UUID) -> None:
    fila = next(f for f in leida.sucursales if f.sucursal_id == sucursal_id)
    if fila.estado != estados.SUC_OK:
        detalle = f": {fila.mensaje}" if fila.mensaje else ""
        raise ValueError(
            f"La sucursal quedó {fila.estado} en la corrida "
            f"{leida.corrida.codigo}{detalle}"
        )


async def _correr(db, fecha_corte: date, sucursal_id: UUID,
                  overrides: Optional[Mapping[str, Any]],
                  confirmar: bool) -> CorridaLeida:
    corrida = await servicio.crear_corrida(
        db, fecha_corte=fecha_corte, sucursal_ids=[sucursal_id],
        overrides=overrides, hoy=fecha_corte,
    )
    await servicio.calcular_corrida(db, corrida.id)
    if confirmar:
        await db.commit()
    leida = await leer_corrida(db, corrida.id)
    _verificar_sucursal(leida, sucursal_id)
    return leida


async def crear_y_calcular(db, fecha_corte: date, sucursal_id: UUID, *,
                           overrides: Optional[Mapping[str, Any]] = None,
                           confirmar: bool = True) -> UUID:
    """Crea y calcula una corrida de UNA sucursal; devuelve su id.

    `confirmar` hace commit (la base de pruebas conserva la corrida). Levanta
    `ValueError` si la sucursal no quedó OK y `ErrorCorrida` si el preflight
    rechaza la corrida.
    """
    leida = await _correr(db, fecha_corte, sucursal_id, overrides, confirmar)
    return leida.corrida.id


def _nota_mes_en_curso(escenario: Escenario, leida: CorridaLeida
                       ) -> Optional[str]:
    if escenario.overrides.get(CLAVE_MES) != MODO_PONDERADO:
        return None
    bloque = leida.corrida.seleccion_datos.get("mes_en_curso") or {}
    if bloque.get("modo_efectivo") == MODO_PONDERADO:
        return f"Mes en curso PONDERADO con d={bloque['d']}, D={bloque['D']}."
    return (
        f"El mes en curso quedó EXCLUIDO ({bloque.get('motivo')}): el "
        f"escenario equivale a la base en ese switch."
    )


async def _medir(db, fecha_corte: date, sucursal_id: UUID,
                 base: ConjuntoLineas, escenario: Escenario,
                 confirmar: bool) -> ResultadoEscenario:
    try:
        leida = await _correr(
            db, fecha_corte, sucursal_id, escenario.overrides, confirmar
        )
    except ErrorCorrida as error:
        return ResultadoEscenario(
            escenario, None, None, f"{error.codigo}: {error.mensaje}"
        )
    conjunto = conjunto_de_filas(leida.lineas.get(sucursal_id, []))
    return ResultadoEscenario(
        escenario, conjunto, calcular_delta(base, conjunto), None,
        _nota_mes_en_curso(escenario, leida),
    )


async def medir_con_base(db, fecha_corte: date, sucursal_id: UUID,
                         escenarios: Iterable[Escenario], *,
                         confirmar: bool = True) -> MedicionBase:
    """Base y una corrida escenario por `Escenario`; la base va primero."""
    leida = await _correr(db, fecha_corte, sucursal_id, None, confirmar)
    base = conjunto_de_filas(leida.lineas.get(sucursal_id, []))
    linea_base = Escenario(
        NOMBRE_BASE, "Todos los switches en su valor legacy", {}
    )
    resultados = [ResultadoEscenario(linea_base, base, None)]
    for escenario in escenarios:
        resultados.append(await _medir(
            db, fecha_corte, sucursal_id, base, escenario, confirmar
        ))
    fila = next(f for f in leida.sucursales if f.sucursal_id == sucursal_id)
    return MedicionBase(
        resultados=tuple(resultados),
        codigo_base=leida.corrida.codigo,
        sucursal=fila.parametros["nombre"],
        seleccion_datos=leida.corrida.seleccion_datos,
    )
