"""
Motored Pedidos — CRUD de maestros (sdd/motored-pedidos-cimientos, Fase 3,
task 3.3). Soft-delete ÚNICAMENTE (`activa = false`) para sucursal, bodega,
proveedor y referencia -- ninguna función de este módulo llama jamás
`db.delete(...)` sobre un maestro (owner decision #3, spec "No endpoint
offers hard delete"). Upsert por llave natural: `referencia` por
(`codigo`, `proveedor_id`), `sucursal` por `nombre` (trimmed), `bodega` por
`codigo`, `proveedor` por `codigo` (owner decision #2).
"""
import uuid
from typing import Any, Dict, Optional, Set, Tuple

from sqlalchemy import select

from app.motored.models.bodega import Bodega
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.schemas.bodega import BodegaCreate, BodegaUpdate
from app.motored.schemas.proveedor import ProveedorCreate, ProveedorUpdate
from app.motored.schemas.referencia import ReferenciaCreate, ReferenciaUpdate
from app.motored.schemas.sucursal import SucursalCreate, SucursalUpdate
from app.motored.services import auditoria
from app.motored.services.validators import coerce_unidad_empaque, normalize_sucursal_nombre


def _updateable_fields(create_data, natural_key_fields: Set[str]) -> Dict[str, Any]:
    """Campos EXPLÍCITAMENTE provistos en un `*Create` (excluyendo la llave
    natural), listos para aplicarse como una actualización parcial. Usa
    `exclude_unset` -- un campo con su valor default (p.ej. `es_principal`
    no enviado) NUNCA pisa el valor ya guardado en un upsert."""
    dumped = create_data.model_dump(exclude_unset=True)
    return {k: v for k, v in dumped.items() if k not in natural_key_fields}


def _apply_and_diff(row, update_dict: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    before = {field: getattr(row, field) for field in update_dict}
    for field, value in update_dict.items():
        setattr(row, field, value)
    after = {field: getattr(row, field) for field in update_dict}
    return before, after


# ---------------------------------------------------------------------------
# Proveedor -- llave natural: codigo
# ---------------------------------------------------------------------------

async def get_proveedor_by_codigo(db, codigo: str) -> Optional[Proveedor]:
    result = await db.execute(select(Proveedor).where(Proveedor.codigo == codigo))
    return result.scalars().first()


async def create_proveedor(db, data: ProveedorCreate, usuario_id: Optional[uuid.UUID] = None) -> Proveedor:
    proveedor = Proveedor(
        id=uuid.uuid4(),
        codigo=data.codigo,
        nombre=data.nombre,
        es_principal=data.es_principal,
        dias_empaque_default=data.dias_empaque_default,
        dias_transito_default=data.dias_transito_default,
        created_by=usuario_id,
    )
    db.add(proveedor)
    auditoria.audit_create(db, "proveedor", proveedor.id, usuario_id)
    return proveedor


async def update_proveedor(db, proveedor: Proveedor, data: ProveedorUpdate, usuario_id: Optional[uuid.UUID] = None) -> Proveedor:
    update_dict = data.model_dump(exclude_unset=True)
    before, after = _apply_and_diff(proveedor, update_dict)
    auditoria.diff_and_audit(db, "proveedor", proveedor.id, usuario_id, before, after)
    return proveedor


async def deactivate_proveedor(db, proveedor: Proveedor, usuario_id: Optional[uuid.UUID] = None) -> Proveedor:
    proveedor.activa = False
    auditoria.audit_deactivate(db, "proveedor", proveedor.id, usuario_id)
    return proveedor


async def upsert_proveedor(
    db, data: ProveedorCreate, usuario_id: Optional[uuid.UUID] = None
) -> Tuple[Proveedor, None, bool]:
    """Retorna `(proveedor, None, created)` -- el segundo elemento existe
    solo para que las 4 funciones `upsert_*` compartan una forma uniforme
    (`referencia` sí tiene advertencia real); `created` es explícito porque
    inferirlo después (p.ej. mirando qué quedó "pendiente" en la sesión) no
    es confiable: una sesión real de SQLAlchemy no expone eso como un
    atributo público inspeccionable así, y la sesión falsa de tests no
    reproduce fielmente ese estado interno."""
    existing = await get_proveedor_by_codigo(db, data.codigo)
    if existing:
        update_fields = _updateable_fields(data, {"codigo"})
        updated = await update_proveedor(db, existing, ProveedorUpdate(**update_fields), usuario_id)
        return updated, None, False
    created = await create_proveedor(db, data, usuario_id)
    return created, None, True


# ---------------------------------------------------------------------------
# Sucursal -- llave natural: nombre (trimmed)
# ---------------------------------------------------------------------------

async def get_sucursal_by_nombre(db, nombre: str) -> Optional[Sucursal]:
    normalized = normalize_sucursal_nombre(nombre)
    result = await db.execute(select(Sucursal).where(Sucursal.nombre == normalized))
    return result.scalars().first()


async def create_sucursal(db, data: SucursalCreate, usuario_id: Optional[uuid.UUID] = None) -> Sucursal:
    sucursal = Sucursal(
        id=uuid.uuid4(),
        nombre=normalize_sucursal_nombre(data.nombre),
        sic=data.sic,
        dias_seguridad=data.dias_seguridad,
        created_by=usuario_id,
    )
    db.add(sucursal)
    auditoria.audit_create(db, "sucursal", sucursal.id, usuario_id)
    return sucursal


async def update_sucursal(db, sucursal: Sucursal, data: SucursalUpdate, usuario_id: Optional[uuid.UUID] = None) -> Sucursal:
    update_dict = data.model_dump(exclude_unset=True)
    if "nombre" in update_dict and update_dict["nombre"] is not None:
        update_dict["nombre"] = normalize_sucursal_nombre(update_dict["nombre"])
    before, after = _apply_and_diff(sucursal, update_dict)
    auditoria.diff_and_audit(db, "sucursal", sucursal.id, usuario_id, before, after)
    return sucursal


async def deactivate_sucursal(db, sucursal: Sucursal, usuario_id: Optional[uuid.UUID] = None) -> Sucursal:
    sucursal.activa = False
    auditoria.audit_deactivate(db, "sucursal", sucursal.id, usuario_id)
    return sucursal


async def upsert_sucursal(
    db, data: SucursalCreate, usuario_id: Optional[uuid.UUID] = None
) -> Tuple[Sucursal, None, bool]:
    """Retorna `(sucursal, None, created)` -- ver nota en `upsert_proveedor`."""
    existing = await get_sucursal_by_nombre(db, data.nombre)
    if existing:
        update_fields = _updateable_fields(data, {"nombre"})
        updated = await update_sucursal(db, existing, SucursalUpdate(**update_fields), usuario_id)
        return updated, None, False
    created = await create_sucursal(db, data, usuario_id)
    return created, None, True


# ---------------------------------------------------------------------------
# Bodega -- llave natural: codigo
# ---------------------------------------------------------------------------

async def get_bodega_by_codigo(db, codigo: str) -> Optional[Bodega]:
    result = await db.execute(select(Bodega).where(Bodega.codigo == codigo))
    return result.scalars().first()


async def create_bodega(db, data: BodegaCreate, usuario_id: Optional[uuid.UUID] = None) -> Bodega:
    bodega = Bodega(
        id=uuid.uuid4(),
        codigo=data.codigo,
        sucursal_id=data.sucursal_id,
        bodega_principal=data.bodega_principal,
        created_by=usuario_id,
    )
    db.add(bodega)
    auditoria.audit_create(db, "bodega", bodega.id, usuario_id)
    return bodega


async def update_bodega(db, bodega: Bodega, data: BodegaUpdate, usuario_id: Optional[uuid.UUID] = None) -> Bodega:
    update_dict = data.model_dump(exclude_unset=True)
    before, after = _apply_and_diff(bodega, update_dict)
    auditoria.diff_and_audit(db, "bodega", bodega.id, usuario_id, before, after)
    return bodega


async def deactivate_bodega(db, bodega: Bodega, usuario_id: Optional[uuid.UUID] = None) -> Bodega:
    bodega.activa = False
    auditoria.audit_deactivate(db, "bodega", bodega.id, usuario_id)
    return bodega


async def upsert_bodega(
    db, data: BodegaCreate, usuario_id: Optional[uuid.UUID] = None
) -> Tuple[Bodega, None, bool]:
    """Retorna `(bodega, None, created)` -- ver nota en `upsert_proveedor`."""
    existing = await get_bodega_by_codigo(db, data.codigo)
    if existing:
        update_fields = _updateable_fields(data, {"codigo"})
        updated = await update_bodega(db, existing, BodegaUpdate(**update_fields), usuario_id)
        return updated, None, False
    created = await create_bodega(db, data, usuario_id)
    return created, None, True


# ---------------------------------------------------------------------------
# Referencia -- llave natural: (codigo, proveedor_id)
# ---------------------------------------------------------------------------

async def get_referencia_by_codigo_proveedor(db, codigo: str, proveedor_id: uuid.UUID) -> Optional[Referencia]:
    result = await db.execute(
        select(Referencia).where(Referencia.codigo == codigo, Referencia.proveedor_id == proveedor_id)
    )
    return result.scalars().first()


async def create_referencia(
    db, data: ReferenciaCreate, usuario_id: Optional[uuid.UUID] = None
) -> Tuple[Referencia, Optional[str]]:
    unidad_empaque, warning = coerce_unidad_empaque(data.unidad_empaque)
    referencia = Referencia(
        id=uuid.uuid4(),
        codigo=data.codigo,
        proveedor_id=data.proveedor_id,
        descripcion=data.descripcion,
        unidad_empaque=unidad_empaque,
        unidad_empaque_advertencia=bool(warning),
        precio_normal=data.precio_normal,
        precio_venta=data.precio_venta,
        precio_publico=data.precio_publico,
        sustituida_por=data.sustituida_por,
        activa=data.sustituida_por is None,
        created_by=usuario_id,
    )
    db.add(referencia)
    auditoria.audit_create(db, "referencia", referencia.id, usuario_id)
    return referencia, warning


async def update_referencia(db, referencia: Referencia, data: ReferenciaUpdate, usuario_id: Optional[uuid.UUID] = None) -> Referencia:
    update_dict = data.model_dump(exclude_unset=True)

    if "unidad_empaque" in update_dict:
        coerced, warning = coerce_unidad_empaque(update_dict["unidad_empaque"])
        update_dict["unidad_empaque"] = coerced
        update_dict["unidad_empaque_advertencia"] = bool(warning)

    if update_dict.get("sustituida_por") is not None:
        update_dict["activa"] = False

    before, after = _apply_and_diff(referencia, update_dict)
    auditoria.diff_and_audit(db, "referencia", referencia.id, usuario_id, before, after)
    return referencia


async def deactivate_referencia(db, referencia: Referencia, usuario_id: Optional[uuid.UUID] = None) -> Referencia:
    referencia.activa = False
    auditoria.audit_deactivate(db, "referencia", referencia.id, usuario_id)
    return referencia


async def upsert_referencia(
    db, data: ReferenciaCreate, usuario_id: Optional[uuid.UUID] = None
) -> Tuple[Referencia, Optional[str], bool]:
    """Retorna `(referencia, advertencia_o_None, created)`."""
    existing = await get_referencia_by_codigo_proveedor(db, data.codigo, data.proveedor_id)
    if existing:
        update_fields = _updateable_fields(data, {"codigo", "proveedor_id"})
        updated = await update_referencia(db, existing, ReferenciaUpdate(**update_fields), usuario_id)
        return updated, None, False
    created, warning = await create_referencia(db, data, usuario_id)
    return created, warning, True
