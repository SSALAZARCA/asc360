from fastapi import APIRouter

from app.api.v1.endpoints import vehicles, users, uploads, tenants
from app.api.v1 import orders
from app.api.v1 import warranty_policies
from app.api.v1 import vehicle_lifecycle
from app.api.v1 import auth
from app.api.v1 import imports as imports_module
from app.api.v1 import vehicle_models
from app.api.v1 import settings as settings_module
from app.api.v1 import parts_manual as parts_manual_module
from app.api.v1 import color_runt_mappings as color_runt_mappings_module
from app.api.v1 import ai_miniapp as ai_miniapp_module
from app.api.v1 import remisiones as remisiones_module
from app.api.v1 import reports as reports_module
from app.api.v1 import superadmin_data as superadmin_data_module
from app.api.v1 import superadmin_historical_orders as superadmin_historical_orders_module
from app.api.v1 import distributor_deliveries as distributor_deliveries_module

api_router = APIRouter()

api_router.include_router(vehicles.router, prefix="/vehicles", tags=["vehiculos"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(tenants.router, prefix="/tenants", tags=["tenants"])
api_router.include_router(uploads.router, prefix="/orders", tags=["upload_photos"])
api_router.include_router(warranty_policies.router)
api_router.include_router(orders.router)
api_router.include_router(vehicle_lifecycle.router)
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(imports_module.router)
api_router.include_router(vehicle_models.router)
api_router.include_router(settings_module.router)
api_router.include_router(parts_manual_module.router)
api_router.include_router(color_runt_mappings_module.router)
api_router.include_router(ai_miniapp_module.router)
api_router.include_router(remisiones_module.router)
api_router.include_router(reports_module.router)
api_router.include_router(superadmin_data_module.router)
api_router.include_router(superadmin_historical_orders_module.router)
api_router.include_router(distributor_deliveries_module.router)
