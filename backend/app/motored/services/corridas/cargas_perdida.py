"""
Motored Pedidos F3 "Motor" (sdd/motored-pedidos-motor, S7, ADR-11): cargas
EXCEL de DEMANDA_PERDIDA que el cargador lee.

El preflight vincula a la corrida las cinco cargas que congela (VENTAS,
INVENTARIO, BACKORDER, FACTURAS_PEDIDOS, INGRESOS_FACTURAS). La demanda
perdida no tiene un corte congelado: el cargador suma todas las filas cuya
`fecha` cae en la ventana. Para que una corrida CERRADA bloquee la anulación
de esas cargas, `crear_corrida` vincula las cargas EXCEL no anuladas que
tienen al menos una fila dentro de la MISMA ventana que lee el cargador
(seis meses cerrados y, si el mes en curso es efectivo, hasta el corte).

Las filas BOT quedan fuera a propósito: son cientos de miles de cabeceras al
año y su anulación ya revierte la cantidad en sitio (ver `cargador`).
"""
from datetime import date
from typing import Tuple
from uuid import UUID

from sqlalchemy import select

from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.demanda_perdida import DemandaPerdida
from app.motored.services.corridas.vigencia import meses_cerrados

ORIGEN_EXCEL = "EXCEL"
ESTADO_ANULADO = "ANULADO"


def consulta_cargas_perdida(fecha_corte: date, con_m0: bool):
    """Ids de las cargas EXCEL vivas con filas en la ventana del cargador."""
    primero_m0 = fecha_corte.replace(day=1)
    desde = meses_cerrados(fecha_corte)[0]
    hasta = (
        DemandaPerdida.fecha <= fecha_corte if con_m0
        else DemandaPerdida.fecha < primero_m0)
    return (
        select(DemandaPerdida.carga_id)
        .join(CargaArchivo, CargaArchivo.id == DemandaPerdida.carga_id)
        .where(
            DemandaPerdida.origen == ORIGEN_EXCEL,
            CargaArchivo.origen == ORIGEN_EXCEL,
            CargaArchivo.estado != ESTADO_ANULADO,
            DemandaPerdida.fecha >= desde,
            hasta,
        )
        .distinct()
    )


async def cargas_demanda_perdida_excel(
    db, fecha_corte: date, con_m0: bool,
) -> Tuple[UUID, ...]:
    """Ids ordenados de las cargas EXCEL de demanda perdida que se leen."""
    resultado = await db.execute(consulta_cargas_perdida(fecha_corte, con_m0))
    return tuple(sorted(resultado.scalars().all()))
