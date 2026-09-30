"""
Motored Pedidos F3 "Motor" (S8b, ADR-10) — lo que los subcomandos hacen contra
una base de pruebas.

Este módulo arrastra `app.config` (la configuración de la aplicación exige
variables de entorno de producción), así que `comandos` lo importa SOLO cuando
un subcomando usa una base. Los modos con libro de Excel no lo cargan.
"""
from datetime import date
from typing import Callable, Optional
from uuid import UUID

from app.motored.herramientas.regresion.corrida_db import (
    CorridaNivelB,
    datos_corrida,
    leer_nivel_b,
)
from app.motored.herramientas.regresion.delta import Escenario
from app.motored.herramientas.regresion.delta_db import (
    MedicionBase,
    crear_y_calcular,
    medir_con_base,
    sesion_desde_url,
)
from app.motored.herramientas.regresion.informe_excel import DatosCorrida


def fabrica_de_sesiones(abrir_sesion: Optional[Callable]) -> Callable:
    """La fábrica indicada o la que abre una sesión desde una URL."""
    return abrir_sesion or sesion_desde_url


async def leer_para_nivel_b(abrir_sesion: Callable, url: str,
                            sucursal_id: UUID, corrida_id: Optional[UUID],
                            fecha_corte: Optional[date], confirmar: bool
                            ) -> CorridaNivelB:
    """Entradas de la aplicación; crea la corrida base si no se da una."""
    async with abrir_sesion(url) as db:
        if corrida_id is None:
            corrida_id = await crear_y_calcular(
                db, fecha_corte, sucursal_id, confirmar=confirmar
            )
        return await leer_nivel_b(db, corrida_id, sucursal_id)


async def medir(abrir_sesion: Callable, url: str, sucursal_id: UUID,
                fecha_corte: date, escenarios: tuple[Escenario, ...],
                confirmar: bool) -> MedicionBase:
    """Base y una corrida escenario por switch (nivel C con base)."""
    async with abrir_sesion(url) as db:
        return await medir_con_base(
            db, fecha_corte, sucursal_id, escenarios, confirmar=confirmar
        )


async def leer_datos_corrida(abrir_sesion: Callable, url: str,
                             corrida_id: UUID) -> DatosCorrida:
    """Todas las sucursales de una corrida guardada, para el libro."""
    async with abrir_sesion(url) as db:
        return await datos_corrida(db, corrida_id)
