from dataclasses import dataclass
from typing import Optional
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.imports import ShipmentMotoUnit


@dataclass
class VinLookupResult:
    id: object
    vin: str
    engine_number: Optional[str]
    model: Optional[str]
    year: Optional[int]
    color: Optional[str]


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
    ) -> Optional[VinLookupResult]:
        if len(vin.strip()) != 17:  # Regla estándar VIN
            return None

        stmt = select(ShipmentMotoUnit).options(selectinload(ShipmentMotoUnit.shipment_order))

        # Exact match first (packing lists a veces traen mayúsc./espacios
        # ya normalizados), luego un fallback normalizado.
        unit = (await db.execute(
            stmt.where(ShipmentMotoUnit.vin_number == vin)
        )).scalar_one_or_none()
        if unit is None:
            vin_norm = vin.strip().upper()
            unit = (await db.execute(
                stmt.where(ShipmentMotoUnit.vin_number == vin_norm)
            )).scalar_one_or_none()
        if unit is None:
            return None

        # `ShipmentMotoUnit.model`/`.model_year` solo se llenan cuando esa
        # unidad puntual difiere del pedido -- la mayoría de las unidades de
        # un mismo pedido comparten el modelo/año del `ShipmentOrder` y por
        # eso quedan en NULL a nivel de unidad. Mismo fallback y misma
        # normalización que ya usa `_serialize_moto_unit` (imports.py) para
        # la pestaña Motocicletas, así ambas pantallas siempre coinciden.
        order = unit.shipment_order
        model = ' '.join(((unit.model or (order.model if order else None)) or '').split()).upper() or None
        year = unit.model_year or (order.model_year if order else None)

        return VinLookupResult(
            id=unit.id,
            vin=unit.vin_number,
            engine_number=unit.engine_number,
            model=model,
            year=year,
            color=unit.color_runt,
        )


vin_master_service = VinMasterService()
