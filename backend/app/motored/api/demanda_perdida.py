"""
Motored Pedidos — indicador de cobertura del bot Lore (sdd/motored-ventas-
perdidas-bot, Phase 6 "Demanda perdida — bot write path", design D1).

`GET /api/motored/demanda-perdida/cobertura-bot`: la fecha `ACTIVA` más
reciente del ledger `demanda_perdida_bot_linea` por sucursal -- el
indicador "última carga por bot" que Fase 7 (frontend) consumirá. Design
D1 es explícito: esto es SOLO advisory -- una subida Excel que se superpone
con fechas ya cubiertas por el bot NUNCA debe bloquearse por esto (ese
guard, si existiera, viviría en la ingesta EXCEL, nunca acá; este endpoint
es de solo lectura).

Auth/scoping: el MISMO criterio fail-closed que `api/cargas.py::
_filtrar_errores_por_sucursal`/`_filtrar_staging_por_sucursal` -- un
usuario `SUCURSAL` solo ve sus propias sucursales; los otros 3 roles ven
todas. `ASESOR_MOSTRADOR` nunca llega acá (no tiene acceso a ningún
endpoint web pre-existente, spec "RBAC role enforcement" delta) -- este
router usa `get_current_motored_user`/JWT, no el secreto del bot.
"""
from __future__ import annotations

import uuid
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.deps import (
    MotoredUser,
    get_current_motored_user,
    get_motored_db_or_503,
    require_motored_ready,
)
from app.motored.models.demanda_perdida_bot_linea import DemandaPerdidaBotLinea

router = APIRouter(
    prefix="/demanda-perdida",
    tags=["motored-demanda-perdida"],
    dependencies=[Depends(require_motored_ready)],
)


@router.get("/cobertura-bot")
async def cobertura_bot(
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(get_current_motored_user),
) -> List[dict]:
    stmt = (
        select(DemandaPerdidaBotLinea.sucursal_id, func.max(DemandaPerdidaBotLinea.fecha))
        .where(DemandaPerdidaBotLinea.estado == "ACTIVA")
        .group_by(DemandaPerdidaBotLinea.sucursal_id)
    )

    if user.role == "SUCURSAL":
        propias = [uuid.UUID(sid) for sid in user.sucursal_ids]
        if not propias:
            return []
        stmt = stmt.where(DemandaPerdidaBotLinea.sucursal_id.in_(propias))

    result = await db.execute(stmt)
    return [
        {"sucursal_id": str(sucursal_id), "ultima_fecha_bot": fecha.isoformat()}
        for sucursal_id, fecha in result.all()
    ]
