"""
Maestro de vendedores (feature motored-tablero-asesores, T3): consulta y
edicion manual. La CARGA por Excel vive en el router generico de maestros
(`/maestros/vendedor/carga...` y `/plantilla.xlsx`): todo-o-nada, upsert por
`nombre_norm`, nunca borra gente.

`GET /vendedores/sin-registrar` lista a quienes aparecen vendiendo en
`venta_detalle` (cargas no ANULADAS) pero no estan en el maestro: es la forma de
encontrar a quien falta agregar. Todo el que no este en el maestro cuenta como
"resto de compania" en el tablero.

Dato personal (Ley 1581): nombre y cedula de empleados. Todo el modulo es
ADMIN|COMPRAS, los mismos roles que pueden cargar el maestro.

Rutas estaticas (`sin-registrar`, `usuarios-disponibles`) antes de las que
llevan `{vendedor_id}`; no hay `GET /{id}` asi que no hay choque posible.
"""
import uuid
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy import exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.motored.deps import MotoredUser, get_motored_db_or_503, require_motored_ready, require_roles
from app.motored.models.carga_archivo import CargaArchivo
from app.motored.models.sucursal import Sucursal
from app.motored.models.usuario import Usuario
from app.motored.models.vendedor import Vendedor
from app.motored.models.venta_detalle import VentaDetalle
from app.motored.schemas.vendedor import VendedorCreate, VendedorRead, VendedorUpdate
from app.motored.services import auditoria, maestros
from app.motored.services.ingesta.ventas import normalizar_vendedor

router = APIRouter(
    prefix="/vendedores",
    tags=["motored-vendedores"],
    dependencies=[Depends(require_motored_ready)],
)

_require_rol = require_roles("ADMIN", "COMPRAS")

LISTA_MAX = 2000
SIN_REGISTRAR_MAX = 500


def _a_dict(vendedor: Vendedor, sucursal_nombre: Optional[str], usuario_nombre: Optional[str]) -> dict:
    cuerpo = VendedorRead.model_validate(vendedor).model_dump(mode="json")
    cuerpo["sucursal_nombre"] = sucursal_nombre
    cuerpo["usuario_nombre"] = usuario_nombre
    return cuerpo


async def _nombres_de(db: AsyncSession, vendedor: Vendedor) -> Tuple[Optional[str], Optional[str]]:
    """Nombre de la sucursal y del usuario enlazados (para la respuesta de
    crear/editar, igual que el listado)."""
    if vendedor.sucursal_id is None and vendedor.usuario_id is None:
        return None, None
    fila = (
        await db.execute(
            select(Sucursal.nombre, Usuario.nombre)
            .select_from(Vendedor)
            .outerjoin(Sucursal, Sucursal.id == Vendedor.sucursal_id)
            .outerjoin(Usuario, Usuario.id == Vendedor.usuario_id)
            .where(Vendedor.id == vendedor.id)
        )
    ).first()
    return (fila[0], fila[1]) if fila else (None, None)


def _validado_o_422(schema_cls, payload: Dict[str, Any]):
    try:
        return schema_cls(**payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(include_context=False),
        )


async def _vendedor_o_404(db: AsyncSession, vendedor_id: uuid.UUID) -> Vendedor:
    result = await db.execute(select(Vendedor).where(Vendedor.id == vendedor_id))
    vendedor = result.scalars().first()
    if vendedor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No encontrado")
    return vendedor


async def _verificar_referencias(
    db: AsyncSession, sucursal_id: Optional[uuid.UUID], usuario_id: Optional[uuid.UUID]
) -> None:
    """La sucursal y el usuario elegidos tienen que existir: sin esto una FK
    rota aparece como un 500 al confirmar."""
    if sucursal_id is not None:
        if (await db.execute(select(Sucursal.id).where(Sucursal.id == sucursal_id))).first() is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="La sucursal elegida no existe.",
            )
    if usuario_id is not None:
        if (await db.execute(select(Usuario.id).where(Usuario.id == usuario_id))).first() is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="El usuario elegido no existe.",
            )


async def _confirmar_o_409(db: AsyncSession) -> None:
    """Confirma la transaccion. Dos pedidos simultaneos con el mismo nombre
    pasan ambos `_verificar_nombre_libre`; el segundo choca con el indice unico
    `uq_vendedor_nombre_norm` y debe verse como el mismo 409, no como un 500."""
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un vendedor con ese nombre.",
        )


async def _verificar_nombre_libre(db: AsyncSession, nombre: str, excepto_id: Optional[uuid.UUID] = None) -> None:
    existente = await maestros.get_vendedor_by_nombre_norm(db, normalizar_vendedor(nombre))
    if existente is not None and existente.id != excepto_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un vendedor con ese nombre ('{existente.nombre}').",
        )


@router.get("")
async def listar_vendedores(
    q: Optional[str] = None,
    cargo: Optional[str] = None,
    activo: Optional[bool] = None,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_rol),
) -> List[dict]:
    consulta = (
        select(Vendedor, Sucursal.nombre, Usuario.nombre)
        .outerjoin(Sucursal, Sucursal.id == Vendedor.sucursal_id)
        .outerjoin(Usuario, Usuario.id == Vendedor.usuario_id)
        .order_by(Vendedor.nombre)
        .limit(LISTA_MAX)
    )
    texto = (q or "").strip()
    if texto:
        consulta = consulta.where(or_(Vendedor.nombre.ilike(f"%{texto}%"), Vendedor.cedula.ilike(f"%{texto}%")))
    if cargo and cargo.strip():
        consulta = consulta.where(Vendedor.cargo == cargo.strip().upper())
    if activo is not None:
        consulta = consulta.where(Vendedor.activo == activo)
    filas = (await db.execute(consulta)).all()
    return [_a_dict(v, suc, usr) for v, suc, usr in filas]


@router.get("/sin-registrar")
async def vendedores_sin_registrar(
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_rol),
) -> List[dict]:
    """Vendedores que aparecen en `venta_detalle` (cargas no ANULADAS) y no
    estan en el maestro (activo o no). `vendedor_ejemplo` es un nombre crudo
    de muestra (el mayor alfabeticamente) para que el usuario lo reconozca."""
    registrado = exists().where(Vendedor.nombre_norm == VentaDetalle.vendedor_norm)
    lineas = func.count().label("lineas")
    consulta = (
        select(
            VentaDetalle.vendedor_norm,
            func.max(VentaDetalle.vendedor).label("vendedor_ejemplo"),
            func.max(VentaDetalle.fecha).label("ultima_venta"),
            lineas,
        )
        .join(CargaArchivo, CargaArchivo.id == VentaDetalle.carga_id)
        .where(
            CargaArchivo.estado != "ANULADO",
            VentaDetalle.vendedor_norm.is_not(None),
            VentaDetalle.vendedor_norm != "",
            ~registrado,
        )
        .group_by(VentaDetalle.vendedor_norm)
        .order_by(lineas.desc(), VentaDetalle.vendedor_norm)
        .limit(SIN_REGISTRAR_MAX)
    )
    filas = (await db.execute(consulta)).all()
    return [
        {
            "vendedor_norm": norm,
            "vendedor_ejemplo": ejemplo,
            "ultima_venta": ultima.isoformat() if ultima else None,
            "lineas": total,
        }
        for norm, ejemplo, ultima, total in filas
    ]


@router.get("/usuarios-disponibles")
async def usuarios_disponibles(
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_rol),
) -> List[dict]:
    """Usuarios activos para el selector de enlace (solo id, nombre y rol: el
    correo no sale de `/usuarios`, que es solo ADMIN)."""
    filas = (
        await db.execute(
            select(Usuario.id, Usuario.nombre, Usuario.role)
            .where(Usuario.activo.is_(True))
            .order_by(Usuario.nombre)
        )
    ).all()
    return [
        {"id": str(uid), "nombre": nombre, "role": getattr(rol, "value", rol)}
        for uid, nombre, rol in filas
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def crear_vendedor(
    payload: Dict[str, Any],
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_rol),
) -> dict:
    data = _validado_o_422(VendedorCreate, payload)
    await _verificar_nombre_libre(db, data.nombre)
    await _verificar_referencias(db, data.sucursal_id, data.usuario_id)
    vendedor = await maestros.create_vendedor(db, data, uuid.UUID(user.user_id))
    await _confirmar_o_409(db)
    sucursal_nombre, usuario_nombre = await _nombres_de(db, vendedor)
    return _a_dict(vendedor, sucursal_nombre, usuario_nombre)


@router.patch("/{vendedor_id}")
async def editar_vendedor(
    vendedor_id: uuid.UUID,
    payload: Dict[str, Any],
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_rol),
) -> dict:
    vendedor = await _vendedor_o_404(db, vendedor_id)
    data = _validado_o_422(VendedorUpdate, payload)
    if not (vendedor.cedula or "").strip() and data.cedula is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Este vendedor no tiene cédula: complétela para guardar los cambios.",
        )
    if data.nombre is not None:
        await _verificar_nombre_libre(db, data.nombre, excepto_id=vendedor.id)
    await _verificar_referencias(db, data.sucursal_id, data.usuario_id)
    await maestros.update_vendedor(db, vendedor, data, uuid.UUID(user.user_id))
    await _confirmar_o_409(db)
    sucursal_nombre, usuario_nombre = await _nombres_de(db, vendedor)
    return _a_dict(vendedor, sucursal_nombre, usuario_nombre)


@router.delete("/{vendedor_id}")
async def desactivar_vendedor(
    vendedor_id: uuid.UUID,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_rol),
) -> dict:
    """Desactiva (`activo = false`), nunca borra: las ventas viejas siguen
    cruzando por `nombre_norm`."""
    vendedor = await _vendedor_o_404(db, vendedor_id)
    await maestros.deactivate_vendedor(db, vendedor, uuid.UUID(user.user_id))
    await db.commit()
    return _a_dict(vendedor, None, None)


@router.post("/{vendedor_id}/reactivar")
async def reactivar_vendedor(
    vendedor_id: uuid.UUID,
    db: AsyncSession = Depends(get_motored_db_or_503),
    user: MotoredUser = Depends(_require_rol),
) -> dict:
    vendedor = await _vendedor_o_404(db, vendedor_id)
    if not vendedor.activo:
        vendedor.activo = True
        auditoria.audit_reactivate(db, "vendedor", vendedor.id, uuid.UUID(user.user_id))
        await db.commit()
    return _a_dict(vendedor, None, None)
