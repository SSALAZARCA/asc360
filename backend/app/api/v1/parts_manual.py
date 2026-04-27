import json
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel
from openai import AsyncOpenAI

from app.database import get_db
from app.models.parts_manual import PartsManualSection, PartsManualItem, VehicleCatalogMap
from app.models.order import ServiceOrder
from app.models.vehicle import Vehicle
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/parts", tags=["Parts Manual"])

_openai = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


# ── Schemas ────────────────────────────────────────────────────────────────────

class PartsSearchRequest(BaseModel):
    order_id: str
    description: str

class PartLookupResult(BaseModel):
    section_id: str
    section_code: str
    section_name: str
    diagram_url: Optional[str]

class PartItemResult(BaseModel):
    id: str
    section_id: str
    section_code: str
    section_name: str
    order_num: str
    factory_part_number: str
    um_part_number: str
    description: str
    unit: Optional[str]
    qty: Optional[int]


# ── AI helper ─────────────────────────────────────────────────────────────────

async def _classify_sections(description: str, sections: list[dict]) -> list[str]:
    """GPT-4o-mini classifica cuáles secciones del catálogo corresponden a la descripción."""
    sections_block = "\n".join(
        f"- {s['section_code']}: {s['section_name']}" for s in sections
    )
    system = (
        "Eres un experto en repuestos de motocicletas UM Colombia. "
        "El técnico describe en español la parte que necesita. "
        "Identifica las 2 o 3 secciones del catálogo de despiece que MÁS PROBABLEMENTE "
        "contienen esa parte. Devuelve ÚNICAMENTE un JSON: {\"codes\": [\"B2\", \"E11\"]}"
    )
    user = f"Descripción del técnico: {description}\n\nSecciones disponibles:\n{sections_block}"
    try:
        resp = await _openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format={"type": "json_object"},
            max_tokens=80,
            temperature=0,
        )
        data = json.loads(resp.choices[0].message.content)
        return data.get("codes", [])[:3]
    except Exception as e:
        logger.error(f"_classify_sections error: {e}")
        return []


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/search", response_model=list[PartLookupResult])
async def search_parts(
    body: PartsSearchRequest,
    db: AsyncSession = Depends(get_db),
    x_sonia_secret: str = Header(default=""),
):
    if x_sonia_secret != settings.SONIA_BOT_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")

    # 1. Obtener modelo del vehículo desde la orden
    result = await db.execute(
        select(ServiceOrder, Vehicle)
        .join(Vehicle, ServiceOrder.vehicle_id == Vehicle.id)
        .where(ServiceOrder.id == body.order_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Orden no encontrada")

    vehicle_model = row[1].model or ""

    # 2. Mapear modelo → catalog_model_code
    map_result = await db.execute(
        select(VehicleCatalogMap).where(
            VehicleCatalogMap.vehicle_model_pattern == vehicle_model
        )
    )
    catalog_map = map_result.scalar_one_or_none()

    if not catalog_map:
        raise HTTPException(
            status_code=404,
            detail=f"Catálogo de despiece no disponible para el modelo '{vehicle_model}'. "
                   "Solicitá al administrador que lo cargue."
        )

    model_code = catalog_map.catalog_model_code

    # 3. Cargar todas las secciones del modelo
    sections_result = await db.execute(
        select(PartsManualSection).where(PartsManualSection.model_code == model_code)
    )
    all_sections = sections_result.scalars().all()

    if not all_sections:
        raise HTTPException(status_code=404, detail="Sin secciones cargadas para este modelo")

    sections_list = [
        {"section_code": s.section_code, "section_name": s.section_name}
        for s in all_sections
    ]

    # 4. Clasificar con IA
    matched_codes = await _classify_sections(body.description, sections_list)

    # 5. Retornar secciones coincidentes
    matched = [
        s for s in all_sections if s.section_code in matched_codes
    ]

    # Fallback: si GPT no devolvió nada válido, retornar las primeras 2 secciones
    if not matched:
        matched = list(all_sections[:2])

    return [
        PartLookupResult(
            section_id=str(s.id),
            section_code=s.section_code,
            section_name=s.section_name,
            diagram_url=s.diagram_url,
        )
        for s in matched
    ]


@router.get("/section/{section_id}/item/{order_num}", response_model=PartItemResult)
async def get_part_by_number(
    section_id: str,
    order_num: str,
    db: AsyncSession = Depends(get_db),
    x_sonia_secret: str = Header(default=""),
):
    if x_sonia_secret != settings.SONIA_BOT_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")

    result = await db.execute(
        select(PartsManualItem, PartsManualSection)
        .join(PartsManualSection, PartsManualItem.section_id == PartsManualSection.id)
        .where(
            PartsManualItem.section_id == section_id,
            PartsManualItem.order_num == order_num,
        )
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Parte no encontrada")

    item, section = row
    return PartItemResult(
        id=str(item.id),
        section_id=str(section.id),
        section_code=section.section_code,
        section_name=section.section_name,
        order_num=item.order_num,
        factory_part_number=item.factory_part_number,
        um_part_number=item.um_part_number,
        description=item.description,
        unit=item.unit,
        qty=item.qty,
    )


@router.get("/factory/{factory_code}", response_model=PartItemResult)
async def get_part_by_factory_code(
    factory_code: str,
    model_code: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    x_sonia_secret: str = Header(default=""),
):
    if x_sonia_secret != settings.SONIA_BOT_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")

    query = (
        select(PartsManualItem, PartsManualSection)
        .join(PartsManualSection, PartsManualItem.section_id == PartsManualSection.id)
        .where(PartsManualItem.factory_part_number == factory_code)
    )
    if model_code:
        query = query.where(PartsManualSection.model_code == model_code)

    result = await db.execute(query)
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Código de fábrica no encontrado en el catálogo")

    item, section = row
    return PartItemResult(
        id=str(item.id),
        section_id=str(section.id),
        section_code=section.section_code,
        section_name=section.section_name,
        order_num=item.order_num,
        factory_part_number=item.factory_part_number,
        um_part_number=item.um_part_number,
        description=item.description,
        unit=item.unit,
        qty=item.qty,
    )
