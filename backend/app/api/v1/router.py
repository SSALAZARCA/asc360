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
