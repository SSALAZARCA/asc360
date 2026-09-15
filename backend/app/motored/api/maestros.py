"""
Motored Pedidos — router de maestros (sdd/motored-pedidos-cimientos,
Fase 4). Envoltorio HTTP DELGADO sobre `services/maestros.py`: cada
endpoint arma el objeto Pydantic desde el request, llama a la función de
servicio correspondiente (que ya contiene toda la regla de negocio --
coerción de `unidad_empaque`, trim de `sucursal.nombre`, soft-delete-only,
auditoría) y hace el `commit()` explícito que `get_motored_db` (ADR-5)
deliberadamente NO hace.

RBAC (proposal §7.15): lectura (list/get) permitida a los 4 roles
autenticados -- CONSULTA y SUCURSAL son read-only sobre maestros, per
alcance de esta fase (sin filtrado por sucursal todavía, ver nota de
alcance en el `README`/apply-progress). Escritura (create/update/
deactivate) restringida a ADMIN|COMPRAS.
"""
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Type

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.deps import MotoredUser, get_current_motored_user, get_motored_db_or_503, require_motored_ready, require_roles
from app.motored.models.bodega import Bodega
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.schemas.bodega import BodegaCreate, BodegaRead, BodegaUpdate
from app.motored.schemas.proveedor import ProveedorCreate, ProveedorRead, ProveedorUpdate
from app.motored.schemas.referencia import ReferenciaCreate, ReferenciaRead, ReferenciaUpdate
from app.motored.schemas.sucursal import SucursalCreate, SucursalRead, SucursalUpdate
from app.motored.services import maestros

router = APIRouter(
    prefix="/maestros",
    tags=["motored-maestros"],
    dependencies=[Depends(require_motored_ready)],
)

# Una única instancia compartida: FastAPI cachea resultados de dependencia
# por identidad de callable dentro de una misma request. Si cada endpoint
# llamara `require_roles("ADMIN", "COMPRAS")` por su cuenta, cada llamada
# produciría un closure DISTINTO y perdería el cacheo -- esto asegura que
# `get_current_motored_user` (que sí va a la base de datos) se resuelva una
# sola vez por request sin importar cuántos endpoints la usen.
_require_write = require_roles("ADMIN", "COMPRAS")


@dataclass(frozen=True)
class _MaestroConfig:
    model: type
    create_schema: Type[BaseModel]
    update_schema: Type[BaseModel]
    read_schema: Type[BaseModel]
    create_fn: Callable
    update_fn: Callable
    deactivate_fn: Callable


_CONFIGS: Dict[str, _MaestroConfig] = {
    "proveedores": _MaestroConfig(
        Proveedor, ProveedorCreate, ProveedorUpdate, ProveedorRead,
        maestros.create_proveedor, maestros.update_proveedor, maestros.deactivate_proveedor,
    ),
    "sucursales": _MaestroConfig(
        Sucursal, SucursalCreate, SucursalUpdate, SucursalRead,
        maestros.create_sucursal, maestros.update_sucursal, maestros.deactivate_sucursal,
    ),
    "bodegas": _MaestroConfig(
        Bodega, BodegaCreate, BodegaUpdate, BodegaRead,
        maestros.create_bodega, maestros.update_bodega, maestros.deactivate_bodega,
    ),
    "referencias": _MaestroConfig(
        Referencia, ReferenciaCreate, ReferenciaUpdate, ReferenciaRead,
        maestros.create_referencia, maestros.update_referencia, maestros.deactivate_referencia,
    ),
}


def _config_or_404(entidad: str) -> _MaestroConfig:
    config = _CONFIGS.get(entidad)
    if config is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Maestro desconocido: '{entidad}'")
    return config


def _validated_or_422(schema_cls: Type[BaseModel], payload: Dict[str, Any]) -> BaseModel:
    try:
        return schema_cls(**payload)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors())


async def _get_or_404(db: AsyncSession, config: _MaestroConfig, entity_id: uuid.UUID):
    result = await db.execute(select(config.model).where(config.model.id == entity_id))
    obj = result.scalars().first()
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")
    return obj


def _to_read(config: _MaestroConfig, obj: Any) -> dict:
    return config.read_schema.model_validate(obj).model_dump(mode="json")


@router.get("/{entidad}")
async def list_maestro(
    entidad: str,
    db: AsyncSession = Depends(get_motored_db_or_503),
    _user: MotoredUser = Depends(get_current_motored_user),
) -> List[dict]:
    config = _config_or_404(entidad)
    result = await db.execute(select(config.model))
    return [_to_read(config, row) for row in result.scalars().all()]


@router.get("/{entidad}/{entity_id}")
async def get_maestro(
    entidad: str,
    entity_id: uuid.UUID,
    db: AsyncSession = Depends(get_motored_db_or_503),
    _user: MotoredUser = Depends(get_current_motored_user),
) -> dict:
    config = _config_or_404(entidad)
    obj = await _get_or_404(db, config, entity_id)
    return _to_read(config, obj)


@router.post("/{entidad}", status_code=status.HTTP_201_CREATED)
async def create_maestro(
    entidad: str,
    payload: Dict[str, Any],
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_write),
) -> dict:
    config = _config_or_404(entidad)
    data = _validated_or_422(config.create_schema, payload)

    created = await config.create_fn(db, data, uuid.UUID(user.user_id))
    # `create_referencia` retorna `(referencia, advertencia_o_None)`; el
    # resto retorna el objeto solo -- única asimetría entre las 4 funciones
    # `create_*` de `services/maestros.py`.
    obj = created[0] if isinstance(created, tuple) else created

    await db.commit()
    return _to_read(config, obj)


@router.patch("/{entidad}/{entity_id}")
async def update_maestro(
    entidad: str,
    entity_id: uuid.UUID,
    payload: Dict[str, Any],
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_write),
) -> dict:
    config = _config_or_404(entidad)
    obj = await _get_or_404(db, config, entity_id)
    data = _validated_or_422(config.update_schema, payload)

    updated = await config.update_fn(db, obj, data, uuid.UUID(user.user_id))
    await db.commit()
    return _to_read(config, updated)


@router.delete("/{entidad}/{entity_id}")
async def deactivate_maestro(
    entidad: str,
    entity_id: uuid.UUID,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_write),
) -> dict:
    """Soft-delete ÚNICAMENTE (`activa = false`) -- nunca un DELETE SQL real
    (owner decision #3, spec 'No endpoint offers hard delete')."""
    config = _config_or_404(entidad)
    obj = await _get_or_404(db, config, entity_id)

    deactivated = await config.deactivate_fn(db, obj, uuid.UUID(user.user_id))
    await db.commit()
    return _to_read(config, deactivated)
