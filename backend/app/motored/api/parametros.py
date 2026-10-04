"""
Motored Pedidos — router de `parametro_metodologia` (sdd/motored-pedidos-
cimientos, Fase 4, §6.10). Solo estructura en Fase 1 -- ningún motor la lee
todavía (ver docstring de `services/parametros.py`).

POST es ADMIN únicamente (cambiar la metodología es una decisión
administrativa que crea una versión nueva, nunca una actualización en
sitio). GET de la versión vigente es de lectura para cualquier rol
autenticado.

S4b (sdd/motored-pedidos-motor, ADR-7): el POST valida contra el registro de
claves (`services/parametros_claves.py`) y responde 422 codificado
(E-PARAM-001/002/003). El GET NO consulta el registro: una clave ya guardada
se lee siempre, sea o no conocida.
"""
import uuid
from datetime import date
from typing import List, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.deps import MotoredUser, get_current_motored_user, get_motored_db_or_503, require_motored_ready, require_roles
from app.motored.models.sucursal import Sucursal
from app.motored.schemas.parametro_metodologia import (
    ConfiguracionRespuesta,
    HistorialParametro,
    ParametroMetodologiaCreate,
    ParametroMetodologiaRead,
)
from app.motored.schemas.pedido import (
    ClaveCatalogo,
    TopesGuardados,
    TopesGuardar,
    TopesPresupuesto,
)
from app.motored.services import parametros_claves, parametros_topes
from app.motored.services.corridas import codigos
from app.motored.services.parametros import (
    leer_configuracion,
    listar_historial,
    obtener_vigente,
    registrar_cambio,
)
from app.motored.services.reloj import hoy_bogota

router = APIRouter(
    prefix="/parametros",
    tags=["motored-parametros"],
    dependencies=[Depends(require_motored_ready)],
)

_require_admin = require_roles("ADMIN")
# F4-16: el tope de presupuesto lo leen ADMIN y COMPRAS; sólo ADMIN lo escribe.
_require_lectura_topes = require_roles("ADMIN", "COMPRAS")
# F4 (B6): el catálogo de claves del motor lo leen los mismos dos roles.
_require_lectura_claves = require_roles("ADMIN", "COMPRAS")


def _rechazo_422(codigo: str, mensaje: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"code": codigo, "message": mensaje},
    )


async def _validar_escritura(db: AsyncSession, payload) -> date:
    """422 codificado si la clave, el valor, la vigencia o la sucursal no
    son válidos. Devuelve el día 1 del mes desde el que rige la versión."""
    try:
        parametros_claves.validar_escritura(
            payload.clave, payload.valor, payload.sucursal_id)
        vigente_desde = parametros_claves.normalizar_vigencia(
            payload.clave, payload.vigente_desde, hoy_bogota())
    except parametros_claves.ErrorParametro as error:
        raise _rechazo_422(error.codigo, error.mensaje) from error
    if payload.sucursal_id is None:
        return vigente_desde
    if await db.get(Sucursal, payload.sucursal_id) is None:
        codigo = codigos.E_PARAM_VALOR_INVALIDO
        raise _rechazo_422(codigo, codigos.mensaje(
            codigo, clave=payload.clave, detalle="la sucursal no existe"))
    return vigente_desde


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ParametroMetodologiaRead)
async def crear_parametro(
    payload: ParametroMetodologiaCreate,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_admin),
):
    vigente_desde = await _validar_escritura(db, payload)
    nueva_version = await registrar_cambio(
        db, payload.clave, payload.valor, vigente_desde,
        uuid.UUID(user.user_id), sucursal_id=payload.sucursal_id,
    )
    await db.commit()
    return nueva_version


@router.get("/configuracion", response_model=ConfiguracionRespuesta)
async def configuracion(
    db: AsyncSession = Depends(get_motored_db_or_503),
    _user: MotoredUser = Depends(_require_admin),
):
    """Todas las claves registradas por pestaña y grupo, con tipo, rango,
    ámbito, default, valor efectivo (global y por sucursal) y versiones
    programadas, para la pantalla de Configuración (sólo ADMIN)."""
    return {"secciones": await leer_configuracion(db, hoy_bogota())}


@router.get("/{clave}/historial", response_model=List[HistorialParametro])
async def historial_de_clave(
    clave: str,
    db: AsyncSession = Depends(get_motored_db_or_503),
    _user: MotoredUser = Depends(_require_admin),
):
    """Las versiones de una clave, la más nueva primero, con quién y
    cuándo la creó (sólo ADMIN)."""
    return [
        HistorialParametro(
            id=f.fila.id, clave=f.fila.clave, valor=f.fila.valor,
            vigente_desde=f.fila.vigente_desde,
            sucursal_id=f.fila.sucursal_id, created_by=f.fila.created_by,
            created_by_nombre=f.autor, created_at=f.fila.created_at)
        for f in await listar_historial(db, clave)
    ]


@router.get("/topes-presupuesto", response_model=TopesPresupuesto)
async def leer_topes_presupuesto(
    db: AsyncSession = Depends(get_motored_db_or_503),
    _user: MotoredUser = Depends(_require_lectura_topes),
):
    """El interruptor del modo tope y el tope de cada tienda (B5a, F4-7)."""
    return await parametros_topes.leer_topes(db, hoy_bogota())


@router.post(
    "/topes-presupuesto", status_code=status.HTTP_201_CREATED,
    response_model=TopesGuardados)
async def guardar_topes_presupuesto(
    payload: TopesGuardar,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_admin),
):
    """Fija o quita el tope de 1 a 200 tiendas: una versión por tienda que
    cambia, todo en una transacción (B5a, F4-7)."""
    try:
        resultado = await parametros_topes.guardar_topes(
            db, payload.topes, uuid.UUID(user.user_id), hoy_bogota())
    except parametros_claves.ErrorParametro as error:
        await db.rollback()
        raise _rechazo_422(error.codigo, error.mensaje) from error
    await db.commit()
    return resultado


@router.get(
    "/claves", response_model=List[ClaveCatalogo],
    response_model_exclude_unset=True)
async def catalogo_de_claves(
    grupo: Literal["MOTOR"] = "MOTOR",
    _user: MotoredUser = Depends(_require_lectura_claves),
):
    """Las claves del motor con su tipo, dominio y valor por defecto, para
    armar los campos de un escenario (B6, F4-8). Sólo el grupo MOTOR: el
    tope de presupuesto y la ingesta no son overrides válidos."""
    return parametros_claves.catalogo(grupo)


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
