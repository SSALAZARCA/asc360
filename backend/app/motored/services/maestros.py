"""
Motored Pedidos — CRUD de maestros (sdd/motored-pedidos-cimientos, Fase 3,
task 3.3). Soft-delete ÚNICAMENTE (`activa = false`) para sucursal, bodega,
proveedor y referencia -- ninguna función de este módulo llama jamás
`db.delete(...)` sobre un maestro (owner decision #3, spec "No endpoint
offers hard delete"). Upsert por llave natural: `referencia` por
`codigo` (único; la carga masiva vive en `reemplazo_referencias`), `sucursal` por `nombre` (trimmed), `bodega` por
`codigo`, `proveedor` por `codigo` (owner decision #2).
"""
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import delete, select

from app.motored.models.bodega import Bodega
from app.motored.models.cliente_tecnired import ClienteTecnired
from app.motored.models.proveedor import Proveedor
from app.motored.models.referencia import Referencia
from app.motored.models.sucursal import Sucursal
from app.motored.models.vendedor import Vendedor
from app.motored.schemas.bodega import BodegaCreate, BodegaUpdate
from app.motored.schemas.proveedor import ProveedorCreate, ProveedorUpdate
from app.motored.schemas.referencia import ReferenciaCreate, ReferenciaUpdate
from app.motored.schemas.sucursal import SucursalCreate, SucursalUpdate
from app.motored.schemas.vendedor import VendedorCreate, VendedorUpdate
from app.motored.services import auditoria
from app.motored.services.ingesta.ventas import normalizar_vendedor
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
        dias_seguridad_default=data.dias_seguridad_default,
        created_by=usuario_id,
    )
    db.add(proveedor)
    auditoria.audit_create(db, "proveedor", proveedor.id, usuario_id)
    return proveedor


async def update_proveedor(
    db, proveedor: Proveedor, data: ProveedorUpdate, usuario_id: Optional[uuid.UUID] = None
) -> Proveedor:
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
        dias_empaque=data.dias_empaque,
        dias_transito=data.dias_transito,
        bodega_principal=data.bodega_principal,
        departamento=data.departamento,
        ciudad=data.ciudad,
        fecha_apertura=data.fecha_apertura,
        created_by=usuario_id,
    )
    db.add(sucursal)
    auditoria.audit_create(db, "sucursal", sucursal.id, usuario_id)
    return sucursal


async def update_sucursal(
    db, sucursal: Sucursal, data: SucursalUpdate, usuario_id: Optional[uuid.UUID] = None
) -> Sucursal:
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
        descripcion=data.descripcion,
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
# Referencia -- llave natural: codigo
# ---------------------------------------------------------------------------

async def get_referencia_by_codigo(db, codigo: str) -> Optional[Referencia]:
    result = await db.execute(select(Referencia).where(Referencia.codigo == codigo.strip()))
    return result.scalars().first()


class SustitutaInvalidaError(ValueError):
    """La sustituta pedida no existe, es la misma referencia, o es de OTRO
    proveedor. Regla de negocio (decisión del usuario, 2026-09-28): la
    sustituta DEBE ser del mismo proveedor. El router la traduce a 422."""


async def _verificar_sustituta(
    db, referencia_id: Optional[uuid.UUID], proveedor_id: uuid.UUID, sustituida_por: Optional[uuid.UUID]
) -> None:
    """Chequeo server-side para escrituras unitarias (formulario/API). La
    carga masiva ya lo garantiza en `api/carga.py::_pick_sustituta` (resuelve
    el código SOLO dentro del proveedor de la fila), así que
    `reemplazo_referencias` lo saltea (`verificar_sustituta=False`) para no
    sumar un query por fila."""
    if sustituida_por is None:
        return
    if referencia_id is not None and sustituida_por == referencia_id:
        raise SustitutaInvalidaError(
            "'Código de referencia sustituta': una referencia no puede sustituirse a sí misma."
        )
    result = await db.execute(select(Referencia).where(Referencia.id == sustituida_por))
    sustituta = result.scalars().first()
    if sustituta is None:
        raise SustitutaInvalidaError("'Código de referencia sustituta': la referencia elegida no existe.")
    if sustituta.proveedor_id != proveedor_id:
        raise SustitutaInvalidaError(
            f"'Código de referencia sustituta': '{sustituta.codigo}' es de otro proveedor. "
            "La referencia sustituta debe ser del mismo proveedor."
        )


async def create_referencia(
    db, data: ReferenciaCreate, usuario_id: Optional[uuid.UUID] = None, verificar_sustituta: bool = True
) -> Tuple[Referencia, Optional[str]]:
    if verificar_sustituta:
        await _verificar_sustituta(db, None, data.proveedor_id, data.sustituida_por)
    unidad_empaque, warning = coerce_unidad_empaque(data.unidad_empaque)
    referencia = Referencia(
        id=uuid.uuid4(),
        codigo=data.codigo,
        proveedor_id=data.proveedor_id,
        nombre=data.nombre,
        linea_comercial=data.linea_comercial,
        unidad_empaque=unidad_empaque,
        unidad_empaque_advertencia=bool(warning),
        precio_normal=data.precio_normal,
        precio_venta=data.precio_venta,
        precio_publico=data.precio_publico,
        sustituida_por=data.sustituida_por,
        homologados=list(data.homologados),
        activa=data.sustituida_por is None,
        created_by=usuario_id,
    )
    db.add(referencia)
    auditoria.audit_create(db, "referencia", referencia.id, usuario_id)
    return referencia, warning


async def update_referencia(
    db, referencia: Referencia, data: ReferenciaUpdate, usuario_id: Optional[uuid.UUID] = None,
    verificar_sustituta: bool = True,
) -> Referencia:
    update_dict = data.model_dump(exclude_unset=True)
    if verificar_sustituta:
        await _verificar_sustituta(db, referencia.id, referencia.proveedor_id, update_dict.get("sustituida_por"))

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


def _aviso_vinculo_quitado(codigo: str, codigo_sustituta: str, motivo: str) -> str:
    return (
        f"'{codigo}': se quitó su referencia sustituta '{codigo_sustituta}' {motivo}. "
        "La sustituta debe ser del mismo proveedor."
    )


def quitar_vinculo_sustituta(
    db,
    apuntadora: Referencia,
    destino: Referencia,
    usuario_id: Optional[uuid.UUID],
    avisos: List[str],
) -> None:
    """Quita `apuntadora.sustituida_por` (apuntaba a `destino`, que ahora es de
    otro proveedor), con asiento de auditoría y un aviso legible."""
    before, after = _apply_and_diff(apuntadora, {"sustituida_por": None})
    auditoria.diff_and_audit(db, "referencia", apuntadora.id, usuario_id, before, after)
    avisos.append(_aviso_vinculo_quitado(
        apuntadora.codigo, destino.codigo, "porque esa referencia ahora es de otro proveedor"))


# ---------------------------------------------------------------------------
# Cliente Tecnired -- la carga REEMPLAZA la lista completa (sin upsert)
# ---------------------------------------------------------------------------

async def reemplazar_clientes_tecnired(
    db, rows: List[Dict[str, Any]], usuario_id: Optional[uuid.UUID] = None
) -> Tuple[int, int, List[Dict[str, Any]]]:
    """Borra TODA la lista actual e inserta `rows` (ya validadas) en la
    transaccion del caller -- el commit lo hace quien llama, asi que un fallo
    en el INSERT deja la lista anterior intacta (rollback). Un NIT repetido en
    el archivo se deduplica: gana la primera fila y las demas quedan como
    advertencia. Retorna `(insertados, eliminados, advertencias)`; las
    advertencias llevan la fila 1-indexada del archivo."""
    vistos: Dict[str, int] = {}
    nuevos: List[Dict[str, Any]] = []
    advertencias: List[Dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        nit = row["nit"]
        if nit in vistos:
            advertencias.append({
                "fila": index,
                "advertencias": [f"NIT repetido (igual a la fila {vistos[nit]}): se conserva la primera"],
            })
            continue
        vistos[nit] = index
        nuevos.append({
            "id": uuid.uuid4(),
            "nit": nit,
            "razon_social": row.get("razon_social"),
            "created_by": usuario_id,
        })

    resultado = await db.execute(delete(ClienteTecnired))
    eliminados = resultado.rowcount or 0
    for datos in nuevos:
        db.add(ClienteTecnired(**datos))
    return len(nuevos), eliminados, advertencias


# ---------------------------------------------------------------------------
# Vendedor -- llave natural: nombre_norm (la misma normalizacion que
# `venta_detalle.vendedor_norm`)
# ---------------------------------------------------------------------------

async def get_vendedor_by_nombre_norm(db, nombre_norm: str) -> Optional[Vendedor]:
    result = await db.execute(select(Vendedor).where(Vendedor.nombre_norm == nombre_norm))
    return result.scalars().first()


async def create_vendedor(db, data: VendedorCreate, usuario_id: Optional[uuid.UUID] = None) -> Vendedor:
    vendedor = Vendedor(
        id=uuid.uuid4(),
        nombre=data.nombre,
        nombre_norm=normalizar_vendedor(data.nombre),
        cargo=data.cargo,
        sucursal_id=data.sucursal_id,
        cedula=data.cedula,
        usuario_id=data.usuario_id,
        activo=data.activo,
    )
    db.add(vendedor)
    auditoria.audit_create(db, "vendedor", vendedor.id, usuario_id)
    return vendedor


async def update_vendedor(
    db, vendedor: Vendedor, data: VendedorUpdate, usuario_id: Optional[uuid.UUID] = None
) -> Vendedor:
    update_dict = data.model_dump(exclude_unset=True)
    # `nombre` y `cargo` son NOT NULL: un `null` explicito significa "no tocar".
    for campo in ("nombre", "cargo", "activo"):
        if campo in update_dict and update_dict[campo] is None:
            del update_dict[campo]
    if "nombre" in update_dict:
        update_dict["nombre_norm"] = normalizar_vendedor(update_dict["nombre"])
    before, after = _apply_and_diff(vendedor, update_dict)
    auditoria.diff_and_audit(db, "vendedor", vendedor.id, usuario_id, before, after)
    return vendedor


async def deactivate_vendedor(db, vendedor: Vendedor, usuario_id: Optional[uuid.UUID] = None) -> Vendedor:
    vendedor.activo = False
    auditoria.audit_deactivate(db, "vendedor", vendedor.id, usuario_id)
    return vendedor


async def upsert_vendedor(
    db, data: VendedorCreate, usuario_id: Optional[uuid.UUID] = None
) -> Tuple[Vendedor, None, bool]:
    """Carga por Excel: upsert por `nombre_norm`, nunca borra a nadie. Solo
    pisa lo que el archivo trae: una celda en blanco conserva el valor
    guardado, y el Excel jamas toca `usuario_id` ni `activo`. El `nombre`
    tampoco se reescribe (es la llave). Retorna `(vendedor, None, created)` --
    ver nota en `upsert_proveedor`."""
    existing = await get_vendedor_by_nombre_norm(db, normalizar_vendedor(data.nombre))
    if existing:
        update_fields = _updateable_fields(data, {"nombre", "usuario_id", "activo"})
        updated = await update_vendedor(db, existing, VendedorUpdate(**update_fields), usuario_id)
        return updated, None, False
    created = await create_vendedor(db, data, usuario_id)
    return created, None, True
