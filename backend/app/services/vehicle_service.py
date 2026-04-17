from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.repositories.vehicle_repository import vehicle_repository
from app.models.vehicle import Vehicle
from app.schemas.vehicle import VehicleCreate, VehicleUpdate
from app.services.vin_master_service import vin_master_service

class VehicleService:
    """Capa de lógica de negocio para los Vehículos del entorno Taller (Tenant-isolated)."""

    def __init__(self):
        self.repository = vehicle_repository

    async def register_or_update_vehicle(
        self,
        db: AsyncSession,
        vehicle_in: VehicleCreate,
        tenant_id: UUID
    ) -> Vehicle:
        """Crea o actualiza un vehículo cuando entra al taller. Enriqueciendo datos con VIN Master si está disponible."""
        
        # Limpiar Placa (Quitar todos los espacios)
        clean_plate = "".join(vehicle_in.plate.split()).upper()
        vehicle_in.plate = clean_plate
        vehicle_in.tenant_id = tenant_id
        
        # Intentar enriquecer desde VIN MASTER si tiene VIN
        if vehicle_in.vin:
            vin_data = await vin_master_service.query_vin(db, vehicle_in.vin)
            if vin_data:
                # Pre-llenamos marca y modelo desde la matriz general
                if not vehicle_in.brand: vehicle_in.brand = vin_data.brand
                if not vehicle_in.model: vehicle_in.model = vin_data.model
                if not vehicle_in.year: vehicle_in.year = vin_data.year

        existing = await self.repository.get_by_plate(db, clean_plate, tenant_id)
        if existing:
            # Update fields
            return await self.repository.update(db, existing, vehicle_in)
        
        # Create
        return await self.repository.create(db, vehicle_in)
        
    async def get_vehicle_by_plate(
        self,
        db: AsyncSession,
        plate: str,
        tenant_id: UUID = None
    ) -> Optional[Vehicle]:
        clean_plate = "".join(str(plate).split()).upper()
        vehicle = await self.repository.get_by_plate(db, clean_plate, tenant_id)
        
        if not vehicle:
            # Si no está en el taller, el flujo del bot a veces envía la placa 
            # pero el VinMaster no tiene placas. Sin embargo, en un sistema real de UM,
            # podríamos tener una tabla de relación Placa-VIN central.
            # Por ahora, si no hay vehículo, el bot pedirá el VIN o foto.
            return None

        # Si el vehículo existe en el taller pero le faltan datos (Marca, Modelo, Año)
        # intentamos enriquecerlo desde VinMaster usando su VIN
        if vehicle and vehicle.vin:
            vin_data = await vin_master_service.query_vin(db, vehicle.vin)
            if vin_data:
                if not vehicle.brand: vehicle.brand = vin_data.model_name # VinMaster usa model_name
                if not vehicle.model: vehicle.model = vin_data.model_code
                if not vehicle.year: vehicle.year = vin_data.year
                if not vehicle.color: vehicle.color = vin_data.color
                
                # Inyectar datos de garantía para Sonia
                setattr(vehicle, 'warranty_info', {
                    "motor_km": vin_data.garantia_motor_km,
                    "motor_months": vin_data.garantia_motor_meses,
                    "general_km": vin_data.garantia_general_km,
                    "general_months": vin_data.garantia_general_meses
                })

        return vehicle

vehicle_service = VehicleService()
