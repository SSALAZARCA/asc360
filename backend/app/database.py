from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.config import settings

# Dependencia para inyección de la sesión DB en FastAPI
# Engine asíncrono
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    pool_size=5,
    max_overflow=10
)

# Fábrica de sesiones
async_session_maker = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)

from typing import AsyncGenerator
# Clase base para todos los modelos
Base = declarative_base()

# Dependencia para inyección de la sesión DB en FastAPI
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

from app.models.tenant import Tenant, TenantType
from app.models.user import User, Role
from app.models.vehicle import Vehicle
from app.models.order import ServiceOrder, OrderHistory, ServiceStatus, ServiceType
from app.models.vin_master import VinMaster
from app.models.logistics import PartCatalog, PartsOrder, PartsOrderItem, PurchaseOrder, PurchaseOrderItem
from app.models.warranty_policies import VehicleLimitedWarranty, MandatoryMaintenanceSchedule
from app.models.imports import (
    ShipmentOrder, ShipmentMotoUnit, SparePartLot, SparePartItem,
    PackingList, PackingListItem, ReconciliationResult,
    Backorder, ImportAttachment, ImportAuditLog, VehicleModel,
)
