from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.repositories.base_repository import BaseRepository
from app.models.vin_master import VinMaster
from app.schemas.vin_master import VinMasterCreate, VinMasterUpdate

class VinMasterRepository(BaseRepository[VinMaster, VinMasterCreate, VinMasterUpdate]):
    """Repositorio específico para la entidad VinMaster."""

    async def get_by_vin(self, db: AsyncSession, vin: str) -> Optional[VinMaster]:
        """Obtener registro de VinMaster exacto por VIN."""
        result = await db.execute(
            select(VinMaster).where(VinMaster.vin == vin)
        )
        return result.scalars().first()

vin_master_repository = VinMasterRepository(VinMaster)
