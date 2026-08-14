from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.repositories.vehicle_repository import vehicle_repository
from app.models.vehicle import Vehicle
from app.schemas.vehicle import VehicleCreate
from app.services.vin_master_service import vin_master_service


class VehicleService:
    """Capa de lógica de negocio para los Vehículos del entorno Taller."""

    def __init__(self):
        self.repository = vehicle_repository

    async def register_or_update_vehicle(
        self,
        db: AsyncSession,
        vehicle_in: VehicleCreate,
    ) -> Vehicle:
        """Crea o actualiza un vehículo cuando entra al taller.

        Enriquece datos con el maestro de VINs si está disponible.

        NOTE (sdd/vehicle-tenant-checkin-release, PR2): this function has
        ZERO tenant semantics -- it never reads, sets, nor filters by any
        tenant_id. THE LIVE BUG this fixes: `vehicle_in.tenant_id =
        tenant_id` put `tenant_id` into `BaseRepository.update`'s
        `model_dump(exclude_unset=True)` dump on every UPDATE, silently
        rewriting a vehicle's owning taller any time ANY tenant serviced
        it. Ownership is now a derived, temporary claim computed from open
        `ServiceOrder` rows (`vehicle_repository.visible_to_tenant`/
        `get_open_claim`), enforced only at order creation (Design
        Decision 1) -- never here.
        """

        # Limpiar Placa (Quitar todos los espacios)
        clean_plate = "".join(vehicle_in.plate.split()).upper()
        vehicle_in.plate = clean_plate

        # Intentar enriquecer desde el maestro de VINs (packing list) si tiene VIN.
        # No incluye marca -- el packing list no la registra por unidad, y en
        # este sistema la marca siempre es UM.
        if vehicle_in.vin:
            vin_data = await vin_master_service.query_vin(db, vehicle_in.vin)
            if vin_data:
                if not vehicle_in.model:
                    vehicle_in.model = vin_data.model
                if not vehicle_in.year:
                    vehicle_in.year = vin_data.year

        # Buscar por placa SIN filtro de tenant -- encontrar un vehículo
        # existente no depende de quién pregunta; la visibilidad del claim
        # se evalúa en la creación de la orden (Decision 1), no aquí.
        existing = await self.repository.get_by_plate(db, clean_plate, None)
        if existing:
            # Update fields
            return await self.repository.update(db, existing, vehicle_in)

        # Create
        return await self.repository.create(db, vehicle_in)

    async def get_vehicle_by_plate(
        self,
        db: AsyncSession,
        plate: str,
        tenant_id: Optional[UUID] = None
    ) -> Optional[Vehicle]:
        clean_plate = "".join(str(plate).split()).upper()
        vehicle = await self.repository.get_by_plate(db, clean_plate, tenant_id)

        if not vehicle:
            # Si no está en el taller, el flujo del bot a veces envía la placa
            # pero el VinMaster no tiene placas. Sin embargo, en un sistema real de UM,
            # podríamos tener una tabla de relación Placa-VIN central.
            # Por ahora, si no hay vehículo, el bot pedirá el VIN o foto.
            return None

        # Si el vehículo existe en el taller pero le faltan datos de garantía,
        # intentamos enriquecerlo desde VinMaster usando su VIN. Consulta
        # aparte de query_vin -- VinMaster guarda términos de garantía del
        # fabricante, no datos del packing list, y tiene su propio set de
        # columnas (model_name/model_code, no model/color como ShipmentMotoUnit).
        if vehicle and vehicle.vin:
            vin_data = await vin_master_service.query_warranty_vin(db, vehicle.vin)
            if vin_data:
                if not vehicle.brand:
                    vehicle.brand = vin_data.model_name  # VinMaster usa model_name
                if not vehicle.model:
                    vehicle.model = vin_data.model_code
                if not vehicle.year:
                    vehicle.year = vin_data.year
                if not vehicle.color:
                    vehicle.color = vin_data.color

                # Inyectar datos de garantía para Sonia
                setattr(vehicle, 'warranty_info', {
                    "motor_km": vin_data.garantia_motor_km,
                    "motor_months": vin_data.garantia_motor_meses,
                    "general_km": vin_data.garantia_general_km,
                    "general_months": vin_data.garantia_general_meses
                })

        return vehicle

    async def delete_vehicle_by_plate(
        self,
        db: AsyncSession,
        plate: str,
        tenant_id: Optional[UUID] = None,
    ) -> str:
        """Elimina un vehículo por placa -- SOLO si no tiene
        `service_orders`. Mecanismo de rollback (compensating
        transaction) usado por el bot de Sonia: cuando la creación de la
        moto tiene éxito pero la orden de servicio subsiguiente falla, el
        bot llama a esto (vía `DELETE /vehicles/{plate}`) para deshacer la
        moto recién creada y no dejar un `Vehicle` huérfano registrado con
        cero órdenes.

        Devuelve uno de `"deleted"` / `"not_found"` / `"has_orders"` -- el
        endpoint traduce esto a 204 / 404 / 409 respectivamente.
        """
        clean_plate = "".join(str(plate).split()).upper()
        vehicle = await self.repository.get_by_plate(db, clean_plate, tenant_id)
        if not vehicle:
            return "not_found"
        if vehicle.service_orders:
            return "has_orders"
        await self.repository.delete_vehicle(db, vehicle)
        return "deleted"


vehicle_service = VehicleService()
