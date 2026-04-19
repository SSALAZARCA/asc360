from fastapi import APIRouter, Depends, Query, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import or_, func
from app.database import get_db
from app.models.tenant import Tenant, TenantType
from app.services.divipola_service import validate_ciudad_dpto, search_municipios
from pydantic import BaseModel, ConfigDict
from typing import Optional, List
import uuid

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

    model_config = ConfigDict(from_attributes=True)

class TenantCreate(BaseModel):
    name: str
    subdomain: Optional[str] = None
    nit: Optional[str] = None
    phone: Optional[str] = None
    tenant_type: str = "service_center"
    ciudad: Optional[str] = None
    departamento: Optional[str] = None
    capacidad_bahias: Optional[int] = None
    numero_tecnicos: Optional[int] = None
    tipo_servicio: Optional[str] = None  # "Todos" o "Revisiones/Express"

@router.get("/", response_model=List[TenantOut])
async def list_tenants(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Lista Centros de Servicio. 
    Solo SuperAdmin puede ver la lista completa.
    """
    if not current_user.is_superadmin:
        raise HTTPException(
            status_code=403, 
            detail="Acceso denegado. Solo la administración central puede ver la red completa."
        )
    result = await db.execute(select(Tenant))
    return result.scalars().all()

@router.get("/bot-list", response_model=List[TenantOut])
async def list_tenants_for_bot(
    db: AsyncSession = Depends(get_db),
    x_sonia_secret: Optional[str] = Header(None),
):
    """
    Lista todos los centros de servicio para uso interno del bot Sonia.
    Protegido por el secreto compartido X-Sonia-Secret (no requiere JWT).
    """
    from app.config import settings
    if x_sonia_secret != settings.SONIA_BOT_SECRET:
        raise HTTPException(status_code=403, detail="Acceso no autorizado.")
    result = await db.execute(select(Tenant))
    return result.scalars().all()


@router.get("/search", response_model=List[TenantOut])
async def search_tenants(q: str = Query(..., min_length=2), db: AsyncSession = Depends(get_db)):
    """
    Busca Centros de Servicio / Distribuidoras por nombre o NIT.
    Usado durante el Onboarding de usuarios para validar que el taller está registrado.
    """
    q_lower = f"%{q.lower()}%"
    stmt = select(Tenant).where(
        or_(
            func.lower(Tenant.name).like(q_lower),
            func.lower(Tenant.nit).like(q_lower)
        )
    ).limit(5)
    result = await db.execute(stmt)
    return result.scalars().all()

@router.post("/", response_model=TenantOut, status_code=201)
async def create_tenant(
    data: TenantCreate, 
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """Crea un nuevo Centro de Servicio. Reservado para SuperAdmin."""
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Permiso denegado para crear talleres")
    # Validar duplicado por nombre o NIT
    existing = await db.execute(
        select(Tenant).where(
            or_(
                func.lower(Tenant.name) == data.name.lower(),
                Tenant.nit == data.nit if data.nit else False
            )
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Ya existe un tenant con ese nombre o NIT: {data.name}")

    # Asegurar subdominio único — auto-generar desde name si no se provee
    import re
    base_sub = data.subdomain or re.sub(r'[^a-z0-9]+', '-', data.name.lower()).strip('-')
    subdomain = base_sub
    counter = 1
    while True:
        res = await db.execute(select(Tenant).where(Tenant.subdomain == subdomain))
        if not res.scalar_one_or_none():
            break
        subdomain = f"{base_sub}-{counter}"
        counter += 1

    try:
        tenant_type_enum = TenantType[data.tenant_type]
    except KeyError:
        tenant_type_enum = TenantType.service_center

    # Validar ciudad y departamento contra DIVIPOLA
    ciudad_oficial = data.ciudad
    dpto_oficial = data.departamento
    if data.ciudad:
        try:
            resultado = validate_ciudad_dpto(data.ciudad, data.departamento or "")
            ciudad_oficial = resultado["municipio"]
            dpto_oficial = resultado["departamento"]
        except ValueError:
            pass  # DIVIPOLA no reconoció la ciudad — usar valor ingresado sin normalizar

    # Normalizar tipo_servicio
    tipo_srv = data.tipo_servicio.strip() if data.tipo_servicio else None
    if tipo_srv and tipo_srv not in TIPO_SERVICIO_VALIDOS:
        tipo_srv = "Todos"

    new_tenant = Tenant(
        id=uuid.uuid4(),
        name=data.name,
        subdomain=subdomain,
        nit=data.nit,
        phone=data.phone,
        tenant_type=tenant_type_enum,
        ciudad=ciudad_oficial,
        departamento=dpto_oficial,
        capacidad_bahias=data.capacidad_bahias,
        numero_tecnicos=data.numero_tecnicos,
        tipo_servicio=tipo_srv,
        config={}
    )
    db.add(new_tenant)
    await db.commit()
    await db.refresh(new_tenant)
    return new_tenant


@router.get("/divipola/search")
async def divipola_search(q: str = Query(..., min_length=2)):
    """Busca municipios/departamentos en el DIVIPOLA (tolera texto sin tildes)."""
    return search_municipios(q)


@router.get("/divipola/departments")
async def get_departments():
    """Retorna la lista de los 33 departamentos de Colombia."""
    from app.services.divipola_service import _load_divipola
    municipios = _load_divipola()
    return sorted(set(m["departamento"] for m in municipios))


@router.get("/divipola/cities")
async def get_cities(departamento: str = Query(...)):
    """Retorna los municipios de un departamento dado."""
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
    """Retorna la configuración del taller (diagnosis_reminder_minutes, etc.)."""
    if not current_user.is_superadmin and current_user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Sin permiso")

    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Taller no encontrado")

    config = tenant.config or {}
    return {
        "tenant_id": str(tenant_id),
        "diagnosis_reminder_minutes": config.get("diagnosis_reminder_minutes", 60),
    }


@router.put("/{tenant_id}/config")
async def update_tenant_config(
    tenant_id: uuid.UUID,
    config_update: TenantConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """Actualiza la configuración del taller. Solo admin del taller o superadmin."""
    if not current_user.is_superadmin and current_user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Sin permiso")

    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Taller no encontrado")

    config = dict(tenant.config or {})
    if config_update.diagnosis_reminder_minutes is not None:
        config["diagnosis_reminder_minutes"] = config_update.diagnosis_reminder_minutes

    tenant.config = config
    db.add(tenant)
    await db.commit()

    return {
        "tenant_id": str(tenant_id),
        "diagnosis_reminder_minutes": config.get("diagnosis_reminder_minutes", 60),
    }

