from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.imports import ShipmentMotoUnit


class VinMasterService:
    """Búsqueda de VIN para prefill de marca/modelo/año/color.

    Consulta `ShipmentMotoUnit` (la tabla real, poblada por los packing
    lists de motos importadas -- la misma que alimenta la pestaña
    "Motocicletas" de Importaciones). La tabla `VinMaster` original (ver
    `app.models.vin_master`) nunca tuvo ningún flujo de import que la
    llenara -- toda consulta contra ella devolvía 404 sin importar el VIN.
    """

    async def query_vin(
        self,
        db: AsyncSession,
        vin: str
    ) -> Optional[ShipmentMotoUnit]:
        if len(vin.strip()) != 17:  # Regla estándar VIN
            return None

        # Exact match first (packing lists a veces traen mayúsc./espacios
        # ya normalizados), luego un fallback normalizado.
        unit = (await db.execute(
            select(ShipmentMotoUnit).where(ShipmentMotoUnit.vin_number == vin)
        )).scalar_one_or_none()
        if unit is None:
            vin_norm = vin.strip().upper()
            unit = (await db.execute(
                select(ShipmentMotoUnit).where(ShipmentMotoUnit.vin_number == vin_norm)
            )).scalar_one_or_none()
        return unit


vin_master_service = VinMasterService()
