from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.vin_master_repository import vin_master_repository
from app.models.vin_master import VinMaster
from app.schemas.vin_master import VinMasterCreate, VinMasterUpdate

class VinMasterService:
    """Capa de lógica de negocio para las maestras de VIN (Base de datos global de red)."""

    def __init__(self):
        self.repository = vin_master_repository

    async def query_vin(
        self,
        db: AsyncSession,
        vin: str
    ) -> Optional[VinMaster]:
        """Consulta el maestro de motocicletas por VIN específico."""
        # Limpieza básica
        clean_vin = str(vin).strip().upper()
        if len(clean_vin) != 17: # Regla estándar VIN
            return None
        
        return await self.repository.get_by_vin(db, clean_vin)

    # TODO: Métodos para importes en lote desde Excel o WebScraping Aduanero

vin_master_service = VinMasterService()
