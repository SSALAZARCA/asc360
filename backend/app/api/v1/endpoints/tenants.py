from fastapi import APIRouter, Depends, Query, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import or_, func
from app.database import get_db
from app.models.tenant import Tenant, TenantType, EstadoRed
from app.services.divipola_service import validate_ciudad_dpto, search_municipios
from pydantic import BaseModel, ConfigDict
from typing import Optional, List
import uuid
import re
import datetime

from app.api.deps import get_current_user, CurrentUser

router = APIRouter()

TIPO_SERVICIO_VALIDOS = {"Todos", "Revisiones/Express"}


class TenantOut(BaseModel):
    id: uuid.UUID
    name: str
    nit: Optional[str] = None
    phone: Optional[str] = None
    tenant_type: str
    ciudad: Optional[str] = None
    departamento: Optional[str] = None
    capacidad_bahias: Optional[int] = None
    numero_tecnicos: Optional[int] = None
    tipo_servicio: Optional[str] = None
    # Capacidades
    has_sales: bool = False
    has_parts: bool = False
    has_service: bool = False
    nivel_red: Optional[str] = None
    # Identificación extendida
    representante_legal: Optional[str] = None
    email: Optional[str] = None
    direccion: Optional[str] = None
    zona_geografica: Optional[str] = None
    fecha_vinculacion: Optional[datetime.date] = None
    estado_red: str = "activo"
    categoria: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_tenant(cls, t: Tenant) -> "TenantOut":
        return cls(
            id=t.id,
            name=t.name,
            nit=t.nit,
            phone=t.phone,
            tenant_type=t.tenant_type.value if t.tenant_type else "service_center",
            ciudad=t.ciudad,
            departamento=t.departamento,
            capacidad_bahias=t.capacidad_bahias,
            numero_tecnicos=t.numero_tecnicos,
            tipo_servicio=t.tipo_servicio,
            has_sales=t.has_sales or False,
            has_parts=t.has_parts or False,
            has_service=t.has_service or False,
            nivel_red=t.nivel_red,
            representante_legal=t.representante_legal,
            email=t.email,
            direccion=t.direccion,
            zona_geografica=t.zona_geografica,
            fecha_vinculacion=t.fecha_vinculacion,
            estado_red=t.estado_red.value if t.estado_red else "activo",
            categoria=t.categoria,
        )


class TenantCreate(BaseModel):
    name: str
    subdomain: Optional[str] = None
    nit: Optional[str] = None
    phone: Optional[str] = None
    tenant_type: str = "distribuidor"
    ciudad: Optional[str] = None
    departamento: Optional[str] = None
    capacidad_bahias: Optional[int] = None
    numero_tecnicos: Optional[int] = None
    tipo_servicio: Optional[str] = None
    # Capacidades
    has_sales: bool = False
    has_parts: bool = False
    has_service: bool = False
    # Identificación extendida
    representante_legal: Optional[str] = None
    email: Optional[str] = None
    direccion: Optional[str] = None
    zona_geografica: Optional[str] = None
    fecha_vinculacion: Optional[datetime.date] = None
    estado_red: str = "activo"
    categoria: Optional[str] = None


class TenantUpdate(BaseModel):
    name: Optional[str] = None
    nit: Optional[str] = None
    phone: Optional[str] = None
    tenant_type: Optional[str] = None
    ciudad: Optional[str] = None
    departamento: Optional[str] = None
    capacidad_bahias: Optional[int] = None
    numero_tecnicos: Optional[int] = None
    tipo_servicio: Optional[str] = None
    has_sales: Optional[bool] = None
    has_parts: Optional[bool] = None
    has_service: Optional[bool] = None
    representante_legal: Optional[str] = None
    email: Optional[str] = None
    direccion: Optional[str] = None
    zona_geografica: Optional[str] = None
    fecha_vinculacion: Optional[datetime.date] = None
    estado_red: Optional[str] = None
    categoria: Optional[str] = None


def _resolve_geo(ciudad: Optional[str], departamento: Optional[str]):
    if not ciudad:
        return ciudad, departamento
    try:
        resultado = validate_ciudad_dpto(ciudad, departamento or "")
        return resultado["municipio"], resultado["departamento"]
    except ValueError:
        return ciudad, departamento


def _resolve_tenant_type(value: str) -> TenantType:
    mapping = {
        "workshop": TenantType.service_center,
        "dealer": TenantType.distribuidor,
        "admin": TenantType.distribuidor,
        "service_center": TenantType.service_center,
        "parts_dealer": TenantType.parts_dealer,
        "distribuidor": TenantType.distribuidor,
    }
    return mapping.get(value, TenantType.distribuidor)


def _resolve_estado_red(value: str) -> EstadoRed:
    try:
        return EstadoRed[value]
    except KeyError:
        return EstadoRed.activo


@router.get("/", response_model=List[TenantOut])
async def list_tenants(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Acceso denegado. Solo la administración central puede ver la red completa.")
    result = await db.execute(select(Tenant))
    return [TenantOut.from_tenant(t) for t in result.scalars().all()]


@router.get("/bot-list", response_model=List[TenantOut])
async def list_tenants_for_bot(
    db: AsyncSession = Depends(get_db),
    x_sonia_secret: Optional[str] = Header(None),
):
    from app.config import settings
    if x_sonia_secret != settings.SONIA_BOT_SECRET:
        raise HTTPException(status_code=403, detail="Acceso no autorizado.")
    result = await db.execute(select(Tenant))
    return [TenantOut.from_tenant(t) for t in result.scalars().all()]


@router.get("/search", response_model=List[TenantOut])
async def search_tenants(q: str = Query(..., min_length=2), db: AsyncSession = Depends(get_db)):
    q_lower = f"%{q.lower()}%"
    stmt = select(Tenant).where(
        or_(
            func.lower(Tenant.name).like(q_lower),
            func.lower(Tenant.nit).like(q_lower)
        )
    ).limit(5)
    result = await db.execute(stmt)
    return [TenantOut.from_tenant(t) for t in result.scalars().all()]


@router.post("/", response_model=TenantOut, status_code=201)
async def create_tenant(
    data: TenantCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Permiso denegado para crear puntos de red")

    existing = await db.execute(
        select(Tenant).where(
            or_(
                func.lower(Tenant.name) == data.name.lower(),
                Tenant.nit == data.nit if data.nit else False
            )
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Ya existe un punto de red con ese nombre o NIT: {data.name}")

    base_sub = data.subdomain or re.sub(r'[^a-z0-9]+', '-', data.name.lower()).strip('-')
    subdomain = base_sub
    counter = 1
    while True:
        res = await db.execute(select(Tenant).where(Tenant.subdomain == subdomain))
        if not res.scalar_one_or_none():
            break
        subdomain = f"{base_sub}-{counter}"
        counter += 1

    ciudad_oficial, dpto_oficial = _resolve_geo(data.ciudad, data.departamento)

    tipo_srv = data.tipo_servicio.strip() if data.tipo_servicio else None
    if tipo_srv and tipo_srv not in TIPO_SERVICIO_VALIDOS:
        tipo_srv = "Todos"

    new_tenant = Tenant(
        id=uuid.uuid4(),
        name=data.name,
        subdomain=subdomain,
        nit=data.nit,
        phone=data.phone,
        tenant_type=_resolve_tenant_type(data.tenant_type),
        ciudad=ciudad_oficial,
        departamento=dpto_oficial,
        capacidad_bahias=data.capacidad_bahias,
        numero_tecnicos=data.numero_tecnicos,
        tipo_servicio=tipo_srv,
        config={},
        has_sales=data.has_sales,
        has_parts=data.has_parts,
        has_service=data.has_service,
        representante_legal=data.representante_legal,
        email=data.email,
        direccion=data.direccion,
        zona_geografica=data.zona_geografica,
        fecha_vinculacion=data.fecha_vinculacion,
        estado_red=_resolve_estado_red(data.estado_red),
        categoria=data.categoria,
    )
    db.add(new_tenant)
    await db.commit()
    await db.refresh(new_tenant)
    return TenantOut.from_tenant(new_tenant)


@router.put("/{tenant_id}", response_model=TenantOut)
async def update_tenant(
    tenant_id: uuid.UUID,
    data: TenantUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Permiso denegado")

    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Punto de red no encontrado")

    if data.name is not None:
        tenant.name = data.name
    if data.nit is not None:
        tenant.nit = data.nit
    if data.phone is not None:
        tenant.phone = data.phone
    if data.tenant_type is not None:
        tenant.tenant_type = _resolve_tenant_type(data.tenant_type)
    if data.has_sales is not None:
        tenant.has_sales = data.has_sales
    if data.has_parts is not None:
        tenant.has_parts = data.has_parts
    if data.has_service is not None:
        tenant.has_service = data.has_service
    if data.representante_legal is not None:
        tenant.representante_legal = data.representante_legal
    if data.email is not None:
        tenant.email = data.email
    if data.direccion is not None:
        tenant.direccion = data.direccion
    if data.zona_geografica is not None:
        tenant.zona_geografica = data.zona_geografica
    if data.fecha_vinculacion is not None:
        tenant.fecha_vinculacion = data.fecha_vinculacion
    if data.estado_red is not None:
        tenant.estado_red = _resolve_estado_red(data.estado_red)
    if data.categoria is not None:
        tenant.categoria = data.categoria
    if data.capacidad_bahias is not None:
        tenant.capacidad_bahias = data.capacidad_bahias
    if data.numero_tecnicos is not None:
        tenant.numero_tecnicos = data.numero_tecnicos
    if data.tipo_servicio is not None:
        tipo_srv = data.tipo_servicio.strip()
        tenant.tipo_servicio = tipo_srv if tipo_srv in TIPO_SERVICIO_VALIDOS else "Todos"

    if data.ciudad is not None or data.departamento is not None:
        ciudad = data.ciudad if data.ciudad is not None else tenant.ciudad
        dpto = data.departamento if data.departamento is not None else tenant.departamento
        tenant.ciudad, tenant.departamento = _resolve_geo(ciudad, dpto)

    await db.commit()
    await db.refresh(tenant)
    return TenantOut.from_tenant(tenant)


@router.get("/divipola/search")
async def divipola_search(q: str = Query(..., min_length=2)):
    return search_municipios(q)


@router.get("/divipola/departments")
async def get_departments():
    from app.services.divipola_service import _load_divipola
    municipios = _load_divipola()
    return sorted(set(m["departamento"] for m in municipios))


@router.get("/divipola/cities")
async def get_cities(departamento: str = Query(...)):
    from app.services.divipola_service import _load_divipola, normalize
    municipios = _load_divipola()
    dpto_norm = normalize(departamento)
    return sorted(m["municipio"] for m in municipios if m["departamento_norm"] == dpto_norm)


class TenantConfigUpdate(BaseModel):
    diagnosis_reminder_minutes: Optional[int] = None

    def model_post_init(self, __context):
        if self.diagnosis_reminder_minutes is not None and self.diagnosis_reminder_minutes < 5:
            raise ValueError("diagnosis_reminder_minutes debe ser mínimo 5")


@router.get("/{tenant_id}/config")
async def get_tenant_config(
    tenant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    if not current_user.is_superadmin and current_user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Sin permiso")
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Punto de red no encontrado")
    config = tenant.config or {}
    return {"tenant_id": str(tenant_id), "diagnosis_reminder_minutes": config.get("diagnosis_reminder_minutes", 60)}


@router.put("/{tenant_id}/config")
async def update_tenant_config(
    tenant_id: uuid.UUID,
    config_update: TenantConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    if not current_user.is_superadmin and current_user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Sin permiso")
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Punto de red no encontrado")
    config = dict(tenant.config or {})
    if config_update.diagnosis_reminder_minutes is not None:
        config["diagnosis_reminder_minutes"] = config_update.diagnosis_reminder_minutes
    tenant.config = config
    db.add(tenant)
    await db.commit()
    return {"tenant_id": str(tenant_id), "diagnosis_reminder_minutes": config.get("diagnosis_reminder_minutes", 60)}
