# El archivo __init__.py expone los modelos para que alembic/env.py pueda importar Base
# garantizando que todas las tablas sean descubiertas.

from app.database import Base

from .system_config import SystemConfig
from .parts_manual import PartsManualSection, PartsManualItem, VehicleCatalogMap
from .tenant import Tenant, TenantType
from .user import User, Role
from .vehicle import Vehicle
from .order import ServiceOrder, OrderHistory, ServiceStatus, ServiceType
from .logistics import (
    PartCatalog, 
    PartsOrder, PartsOrderItem, PartsOrderStatus,
    PurchaseOrder, PurchaseOrderItem, PurchaseOrderStatus, PurchaseOrderItemStatus
)
from .vin_master import VinMaster
from .warranty_policies import VehicleLimitedWarranty, MandatoryMaintenanceSchedule
from .vehicle_lifecycle import VehicleLifecycleEvent, LifecycleEventType
from .imports import (
    ShipmentOrder, ShipmentMotoUnit, SparePartLot, SparePartItem,
    PackingList, PackingListItem, ReconciliationResult,
    Backorder, ImportAttachment, ImportAuditLog, VehicleModel,
)

# Esto exporta todo correctamente.
__all__ = [
    "Base", "SystemConfig", "Tenant", "TenantType", "User", "Role", "Vehicle",
    "ServiceOrder", "OrderHistory", "ServiceStatus", "ServiceType",
    "PartCatalog", "PartsOrder", "PartsOrderItem", "PartsOrderStatus",
    "PurchaseOrder", "PurchaseOrderItem", "PurchaseOrderStatus", "PurchaseOrderItemStatus",
    "VinMaster", "VehicleLimitedWarranty", "MandatoryMaintenanceSchedule",
    "VehicleLifecycleEvent", "LifecycleEventType",
    "ShipmentOrder", "ShipmentMotoUnit", "SparePartLot", "SparePartItem",
    "PackingList", "PackingListItem", "ReconciliationResult",
    "Backorder", "ImportAttachment", "ImportAuditLog", "VehicleModel",
    "PartsManualSection", "PartsManualItem", "VehicleCatalogMap",
]
