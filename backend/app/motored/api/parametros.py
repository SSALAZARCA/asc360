"""
Motored Pedidos — router de `parametro_metodologia` (sdd/motored-pedidos-
cimientos, Fase 4, §6.10). Solo estructura en Fase 1 -- ningún motor la lee
todavía (ver docstring de `services/parametros.py`).

POST es ADMIN únicamente (cambiar la metodología es una decisión
administrativa que crea una versión nueva, nunca una actualización en
sitio). GET de la versión vigente es de lectura para cualquier rol
autenticado.
"""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.deps import MotoredUser, get_current_motored_user, get_motored_db_or_503, require_motored_ready, require_roles
from app.motored.schemas.parametro_metodologia import ParametroMetodologiaCreate, ParametroMetodologiaRead
from app.motored.services.parametros import obtener_vigente, registrar_cambio

router = APIRouter(
    prefix="/parametros",
    tags=["motored-parametros"],
    dependencies=[Depends(require_motored_ready)],
)

_require_admin = require_roles("ADMIN")


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ParametroMetodologiaRead)
async def crear_parametro(
    payload: ParametroMetodologiaCreate,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_admin),
):
    nueva_version = await registrar_cambio(
        db, payload.clave, payload.valor, payload.vigente_desde, uuid.UUID(user.user_id)
    )
    await db.commit()
    return nueva_version


@router.get("/{clave}/vigente", response_model=ParametroMetodologiaRead)
async def parametro_vigente(
    clave: str,
    db: AsyncSession = Depends(get_motored_db_or_503),
    _user: MotoredUser = Depends(get_current_motored_user),
):
    resultado = await obtener_vigente(db, clave, date.today())
    if resultado is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sin versión vigente para esta clave")
    return resultado
