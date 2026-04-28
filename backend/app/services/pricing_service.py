import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.parts_manual import PartsReference, PartCostHistory
from app.models.imports import SparePartItem
from app.models.system_config import SystemConfig

logger = logging.getLogger(__name__)

_PRICING_KEYS = (
    "pricing.import_factor",
    "pricing.provider_margin",
    "pricing.distributor_margin",
    "pricing.iva_rate",
    "pricing.trm",
)

_PRICING_DEFAULTS = {
    "pricing.import_factor":      1.42,
    "pricing.provider_margin":    0.35,
    "pricing.distributor_margin": 0.35,
    "pricing.iva_rate":           0.19,
    "pricing.trm":                3800.0,
}


async def _find_reference_for_part_number(
    db: AsyncSession, part_number: str
) -> PartsReference | None:
    """
    Busca el PartsReference cuyo factory_part_number O cualquier código
    dentro de prev_codes[] coincide con el part_number dado.
    """
    stmt = select(PartsReference).where(
        PartsReference.factory_part_number == part_number
    )
    ref = (await db.execute(stmt)).scalar_one_or_none()
    if ref:
        return ref

    # prev_codes es JSONB array: [{"code": "...", "source": "...", "date_seen": "..."}]
    # @> verifica que el array contenga el elemento dado
    stmt = select(PartsReference).where(
        PartsReference.prev_codes.contains([{"code": part_number}])
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def recalculate_part_cost(
    db: AsyncSession,
    part_number: str,
    lot_identifier: str | None = None,
) -> None:
    """
    Recalcula el promedio ponderado FOB del PartsReference correspondiente
    al part_number dado. Solo actúa si existe entrada en el catálogo.
    Registra en PartCostHistory cuando se conoce el lot_identifier.
    """
    ref = await _find_reference_for_part_number(db, part_number)
    if not ref:
        logger.debug("recalculate_part_cost: %s sin entrada en catálogo, skip", part_number)
        return

    # Todos los códigos que mapean a este ref (canónico + alternativos)
    all_codes = [ref.factory_part_number]
    for entry in (ref.prev_codes or []):
        if isinstance(entry, dict) and "code" in entry:
            all_codes.append(entry["code"])

    stmt = select(SparePartItem).where(
        SparePartItem.part_number.in_(all_codes),
        SparePartItem.unit_price.isnot(None),
        SparePartItem.qty_ordered > 0,
    )
    items = (await db.execute(stmt)).scalars().all()

    if not items:
        return

    total_cost = sum(float(i.unit_price) * i.qty_ordered for i in items)
    total_qty  = sum(i.qty_ordered for i in items)
    new_avg    = round(total_cost / total_qty, 4)

    ref.avg_fob_cost      = new_avg
    ref.total_fob_qty     = total_qty
    ref.last_cost_updated = datetime.utcnow()

    if lot_identifier:
        # Registrar solo el item de este lote específico (el que disparó el recálculo)
        triggering_item = next(
            (i for i in items if i.part_number == part_number), None
        )
        if triggering_item and triggering_item.unit_price:
            db.add(PartCostHistory(
                factory_part_number=ref.factory_part_number,
                lot_identifier=lot_identifier,
                part_number_used=part_number,
                unit_price=triggering_item.unit_price,
                qty=triggering_item.qty_ordered,
                recorded_at=datetime.utcnow(),
            ))

    logger.info(
        "recalculate_part_cost: %s → avg_fob=%.4f (qty=%d, %d código/s)",
        ref.factory_part_number, new_avg, total_qty, len(all_codes),
    )


async def get_pricing_factors(db: AsyncSession) -> dict:
    """Lee los factores de precio desde SystemConfig con fallback a defaults."""
    stmt = select(SystemConfig).where(SystemConfig.key.in_(_PRICING_KEYS))
    rows = (await db.execute(stmt)).scalars().all()
    factors = {r.key: float(r.value) for r in rows if r.value is not None}
    return {
        "import_factor":       factors.get("pricing.import_factor",      _PRICING_DEFAULTS["pricing.import_factor"]),
        "provider_margin":     factors.get("pricing.provider_margin",    _PRICING_DEFAULTS["pricing.provider_margin"]),
        "distributor_margin":  factors.get("pricing.distributor_margin", _PRICING_DEFAULTS["pricing.distributor_margin"]),
        "iva_rate":            factors.get("pricing.iva_rate",           _PRICING_DEFAULTS["pricing.iva_rate"]),
        "trm":                 factors.get("pricing.trm",                _PRICING_DEFAULTS["pricing.trm"]),
    }


def compute_prices(avg_fob_cost: float | None, factors: dict) -> dict:
    """
    Calcula la cadena de precios en COP a partir del FOB promedio (USD) y los factores.
    La conversión USD → COP se aplica con el TRM configurado.
    Ningún precio se almacena — se deriva on-the-fly.
    """
    if avg_fob_cost is None:
        return {
            "costo_importado":     None,
            "precio_distribuidor": None,
            "precio_publico":      None,
        }
    f   = factors
    trm = f["trm"]
    costo_importado_usd  = float(avg_fob_cost) * f["import_factor"]
    precio_dist_usd      = costo_importado_usd * (1 + f["provider_margin"]) * (1 + f["iva_rate"])
    precio_publico_usd   = precio_dist_usd     * (1 + f["distributor_margin"]) * (1 + f["iva_rate"])
    return {
        "costo_importado":     round(costo_importado_usd * trm, 0),
        "precio_distribuidor": round(precio_dist_usd     * trm, 0),
        "precio_publico":      round(precio_publico_usd  * trm, 0),
    }
