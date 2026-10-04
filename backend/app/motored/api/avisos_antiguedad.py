"""
Motored: `/api/motored/avisos-antiguedad`, el aviso anticipado en pantalla.

`GET /` devuelve los datos del pedido (inventario, backorder, facturas de
pedidos, ingresos de facturas) cuyo ultimo dia de vigencia es hoy o manana,
hora de Bogota. Es el banner de Pedidos; el mismo calculo alimenta el
aviso por Telegram (`services/avisos_antiguedad.py`). Solo lectura. RBAC:
ADMIN y COMPRAS, igual que `/corridas`.
"""
from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.api import corridas_comun as comun
from app.motored.deps import (
    MotoredUser,
    get_motored_db_or_503,
    require_motored_ready,
)
from app.motored.services import avisos_antiguedad
from app.motored.services.reloj import hoy_bogota

router = APIRouter(
    prefix="/avisos-antiguedad",
    tags=["motored-avisos-antiguedad"],
    dependencies=[Depends(require_motored_ready)],
)


@router.get("")
async def listar_avisos(
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(comun.require_read),
) -> Dict[str, Any]:
    """`{avisos: [{dataset, nombre, vence: hoy|manana, fecha_carga,
    fecha_vencimiento}]}`, del que vence primero al último."""
    hoy = hoy_bogota()
    vencimientos = await avisos_antiguedad.leer_vencimientos(db, hoy)
    del_dia = avisos_antiguedad.avisos_del_dia(vencimientos, hoy)
    del_dia.sort(key=lambda par: (par[0].fecha_vencimiento, par[0].tipo))
    return {"avisos": [
        {
            "dataset": venc.tipo,
            "nombre": venc.nombre,
            "vence": etiqueta,
            "fecha_carga": venc.fecha_carga.isoformat(),
            "fecha_vencimiento": venc.fecha_vencimiento.isoformat(),
        }
        for venc, etiqueta in del_dia
    ]}
