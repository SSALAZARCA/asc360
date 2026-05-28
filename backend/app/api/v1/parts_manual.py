import base64
import io
import json
import logging
import os
import re
import tempfile
import uuid as _uuid
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

import fitz  # PyMuPDF
import pdfplumber
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from minio import Minio
from pydantic import BaseModel
from sqlalchemy import delete as sa_delete, update as sa_update, text, exists, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from openai import AsyncOpenAI

from app.api.deps import get_current_user, get_optional_user
from app.core.security import verify_sonia_secret
from app.config import settings
from app.database import get_db, async_session_maker
from app.models.order import ServiceOrder
from app.models.imports import VehicleModel, SparePartItem
from app.models.logistics import PartCatalog
from app.models.parts_manual import (
    PartsManualItem, PartsManualSection, PartsReference, VehicleCatalogMap,
    PartsCodeReviewTask, PartSubstitute, PartCostHistory,
)
from app.models.system_config import SystemConfig

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/parts", tags=["Parts Manual"])

_openai = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

PARTS_BUCKET = "parts-manuals"


# ── Schemas ────────────────────────────────────────────────────────────────────

class PartsSearchRequest(BaseModel):
    order_id: str
    description: str

class PartLookupResult(BaseModel):
    section_id: str
    section_code: str
    section_name: str
    diagram_url: Optional[str]
    model_code: Optional[str] = None


class PartsByModelRequest(BaseModel):
    model_code: str
    description: str


class PartItemByCodeResult(BaseModel):
    factory_part_number: str
    description: str
    description_es: Optional[str] = None
    section_code: str
    section_name: str
    order_num: str

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

class PartReferenceResult(BaseModel):
    factory_part_number: str
    um_part_number: str
    description: str
    unit: Optional[str]

class LoadSectionResult(BaseModel):
    section_code: str
    section_name: str
    diagram_url: Optional[str]
    parts_loaded: int
    references_new: int


# ── Helpers internos ───────────────────────────────────────────────────────────

async def _classify_sections(description: str, sections: list[dict]) -> list[str]:
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


def _parse_section_filename(filename: str) -> tuple[str, str]:
    """
    'RENEGADE 200 SPORT_B1_FRAME.pdf'        → ('B1',  'FRAME')
    'RENEGADE 200 SPORT_B12_REAR FENDER_REAR TURN SIGNAL.pdf' → ('B12', 'REAR FENDER / REAR TURN SIGNAL')
    'B01_BODY COMP FRAME.pdf'                → ('B01', 'BODY COMP FRAME')
    'B01 - AIR CLEANER ASSY.pdf'             → ('B01', 'AIR CLEANER ASSY')
    'B04 FOOTREST & PEDALS.pdf'              → ('B04', 'FOOTREST & PEDALS')
    """
    stem = Path(filename).stem
    parts = [p.strip() for p in stem.split("_") if p.strip()]
    if len(parts) >= 3:
        # Formato: MODELO_CODIGO_DESCRIPCION[_DESCRIPCION...]
        code = parts[1]
        name = " / ".join(parts[2:])
    elif len(parts) == 2:
        # Formato simple: CODIGO_DESCRIPCION
        code = parts[0]
        name = parts[1]
    else:
        # Formato "B01 - DESCRIPCION" o "B04 DESCRIPCION" (sin guiones bajos, guion opcional)
        m = re.match(r'^([A-Z]\d+)\s*-*\s*(.+)$', stem, re.IGNORECASE)
        if m:
            code = m.group(1).strip().upper()
            name = m.group(2).strip()
        else:
            code = stem
            name = stem
    return code, name


_HEADER_KEYWORDS = {
    "order_num":   ["page", "no.", "no ", "item", "pos"],
    "factory":     ["factory", "part no", "part num", "code", "bom"],
    "um":          ["um part", "um no"],
    "description": ["description", "descrip"],
    "unit":        ["unit"],
}


def _detect_col(header_row: list, keywords: list, start: int = 0) -> int:
    for i in range(start, len(header_row)):
        cell = header_row[i]
        if cell is None:
            continue
        cell_lower = str(cell).lower().strip()
        for kw in keywords:
            if kw in cell_lower:
                return i
    return -1


def _find_col_groups(header_row: list) -> list[dict]:
    """Return all column groups (order_num, factory, …) found in a header row."""
    groups = []
    row_lower = [str(c).lower().strip() if c else "" for c in header_row]
    i = 0
    while i < len(row_lower):
        cell = row_lower[i]
        if cell and any(kw in cell for kw in ["no.", "no ", "n0.", "item", "pos"]):
            col_map = {field: _detect_col(header_row, kws, start=i) for field, kws in _HEADER_KEYWORDS.items()}
            col_map["order_num"] = i
            if col_map.get("factory", -1) > i:
                groups.append(col_map)
                i = max(v for v in col_map.values() if v > 0) + 1
                continue
        i += 1
    return groups


def _extract_tables_from_page(page) -> list[list[list]]:
    """Try default line-based extraction; fall back to text-alignment strategy."""
    tables = page.extract_tables() or []
    if tables:
        return tables
    for strategy in (
        {"vertical_strategy": "text", "horizontal_strategy": "lines"},
        {"vertical_strategy": "text", "horizontal_strategy": "text",
         "snap_tolerance": 5, "join_tolerance": 5, "text_tolerance": 5},
    ):
        try:
            t = page.extract_table(table_settings=strategy)
            if t and len(t) >= 2:
                return [t]
        except Exception:
            pass
    return []


def _parse_parts_from_text(text: str) -> list[dict]:
    """Fallback for PDFs without structured tables (plain-text layout)."""
    import re as _re
    parts = []
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    header_idx = -1
    for i, line in enumerate(lines):
        low = line.lower()
        if ("no" in low or "n0" in low or "item" in low) and ("factory" in low or "bom" in low or "part" in low):
            header_idx = i
            break
    if header_idx < 0:
        return parts
    pattern = _re.compile(r'^(\S+)\s+(\S+)\s+(.+)$')
    skip = {"no.", "no", "item", "pos", "page"}
    for line in lines[header_idx + 1:]:
        m = pattern.match(line)
        if not m:
            continue
        order_num, factory, description = m.group(1), m.group(2), m.group(3).strip()
        if order_num.lower() in skip:
            continue
        if len(factory) < 3 or not _re.search(r'[A-Z0-9]', factory, _re.I):
            continue
        parts.append({
            "order_num":           order_num,
            "factory_part_number": factory,
            "um_part_number":      "",
            "description":         description,
            "unit":                None,
        })
    return parts


def _parse_parts_table(pdf_path: str) -> list[dict]:
    parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_parts: list[dict] = []
            for table in _extract_tables_from_page(page):
                if not table or len(table) < 2:
                    continue
                header_idx, col_groups = -1, []
                for row_i, row in enumerate(table):
                    if not row:
                        continue
                    row_lower = [str(c).lower() if c else "" for c in row]
                    hits = sum(
                        1 for kw_list in _HEADER_KEYWORDS.values()
                        for kw in kw_list if any(kw in cell for cell in row_lower)
                    )
                    if hits >= 3:
                        header_idx = row_i
                        col_groups = _find_col_groups(row)
                        break
                if header_idx < 0 or not col_groups:
                    continue
                skip = {"page", "no.", "no", "item", "pos", ""}
                for row in table[header_idx + 1:]:
                    if not row:
                        continue
                    for col_map in col_groups:
                        def get(field, _cm=col_map, _row=row):
                            idx = _cm.get(field, -1)
                            if idx < 0 or idx >= len(_row):
                                return None
                            v = _row[idx]
                            return str(v).strip() if v is not None else None

                        order_num = get("order_num")
                        factory   = get("factory")
                        if not order_num or not factory:
                            continue
                        if order_num.lower() in skip:
                            continue
                        page_parts.append({
                            "order_num":           order_num,
                            "factory_part_number": factory,
                            "um_part_number":      get("um") or "",
                            "description":         get("description") or "",
                            "unit":                get("unit"),
                        })

            if page_parts:
                parts.extend(page_parts)
            else:
                text = page.extract_text() or ""
                parts.extend(_parse_parts_from_text(text))
    return parts


def _minio_client() -> Minio:
    return Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
    )


def _ensure_parts_bucket(client: Minio) -> None:
    if not client.bucket_exists(PARTS_BUCKET):
        client.make_bucket(PARTS_BUCKET)
        policy = json.dumps({
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow", "Principal": "*",
                "Action": "s3:GetObject",
                "Resource": f"arn:aws:s3:::{PARTS_BUCKET}/*",
            }]
        })
        client.set_bucket_policy(PARTS_BUCKET, policy)


def _diagram_public_url(object_name: str) -> str:
    public_base = settings.MINIO_PUBLIC_URL or f"http://{settings.MINIO_ENDPOINT}"
    return f"{public_base}/{PARTS_BUCKET}/{object_name}"


# ── Endpoint de administración — listado de modelos ───────────────────────────

@router.get("/admin/vehicle-models")
async def list_vehicle_models(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Devuelve el catálogo de modelos UM con su catalog_model_code si ya tiene secciones cargadas."""
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Solo superadmin")

    result = await db.execute(
        select(VehicleModel.model_name, VehicleCatalogMap.catalog_model_code)
        .outerjoin(VehicleCatalogMap, VehicleModel.model_name == VehicleCatalogMap.vehicle_model_pattern)
        .order_by(VehicleModel.model_name)
    )
    rows = result.all()
    return [
        {"vehicle_model": r[0], "catalog_model_code": r[1]}
        for r in rows if r[0]
    ]


# ── Endpoints de búsqueda (bot) ────────────────────────────────────────────────

@router.post("/search", response_model=list[PartLookupResult])
async def search_parts(
    body: PartsSearchRequest,
    db: AsyncSession = Depends(get_db),
    x_sonia_secret: str = Header(default=""),
):
    if not verify_sonia_secret(x_sonia_secret, settings.SONIA_BOT_SECRET):
        raise HTTPException(status_code=403, detail="Forbidden")

    result = await db.execute(
        select(ServiceOrder, Vehicle)
        .join(Vehicle, ServiceOrder.vehicle_id == Vehicle.id)
        .where(ServiceOrder.id == body.order_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Orden no encontrada")

    vehicle_model = row[1].model or ""

    map_result = await db.execute(
        select(VehicleCatalogMap).where(VehicleCatalogMap.vehicle_model_pattern == vehicle_model)
    )
    catalog_map = map_result.scalar_one_or_none()
    if not catalog_map:
        raise HTTPException(
            status_code=404,
            detail=f"Catálogo no disponible para el modelo '{vehicle_model}'."
        )

    sections_result = await db.execute(
        select(PartsManualSection).where(PartsManualSection.model_code == catalog_map.catalog_model_code)
    )
    all_sections = sections_result.scalars().all()
    if not all_sections:
        raise HTTPException(status_code=404, detail="Sin secciones cargadas para este modelo")

    sections_list = [{"section_code": s.section_code, "section_name": s.section_name} for s in all_sections]
    matched_codes = await _classify_sections(body.description, sections_list)
    matched = [s for s in all_sections if s.section_code in matched_codes] or list(all_sections[:2])

    return [
        PartLookupResult(
            section_id=str(s.id),
            section_code=s.section_code,
            section_name=s.section_name,
            diagram_url=s.diagram_url,
            model_code=catalog_map.catalog_model_code,
        )
        for s in matched
    ]


# ── Endpoints de catálogo para bot (superadmin) ───────────────────────────────

@router.get("/bot/catalog-models")
async def bot_catalog_models(
    db: AsyncSession = Depends(get_db),
    x_sonia_secret: str = Header(default=""),
    current_user=Depends(get_optional_user),
):
    if not verify_sonia_secret(x_sonia_secret, settings.SONIA_BOT_SECRET) and current_user is None:
        raise HTTPException(status_code=403, detail="Forbidden")

    result = await db.execute(
        select(VehicleModel.model_name, VehicleCatalogMap.catalog_model_code)
        .join(VehicleCatalogMap, VehicleModel.model_name == VehicleCatalogMap.vehicle_model_pattern)
        .where(VehicleCatalogMap.catalog_model_code.isnot(None))
        .order_by(VehicleModel.model_name)
    )
    return [
        {"vehicle_model": r[0], "catalog_model_code": r[1]}
        for r in result.all() if r[0]
    ]


@router.post("/search-by-model", response_model=list[PartLookupResult])
async def search_parts_by_model(
    body: PartsByModelRequest,
    db: AsyncSession = Depends(get_db),
    x_sonia_secret: str = Header(default=""),
    current_user=Depends(get_optional_user),
):
    if not verify_sonia_secret(x_sonia_secret, settings.SONIA_BOT_SECRET) and current_user is None:
        raise HTTPException(status_code=403, detail="Forbidden")

    sections_result = await db.execute(
        select(PartsManualSection).where(PartsManualSection.model_code == body.model_code)
    )
    all_sections = sections_result.scalars().all()
    if not all_sections:
        raise HTTPException(status_code=404, detail="Sin secciones cargadas para este modelo")

    sections_list = [{"section_code": s.section_code, "section_name": s.section_name} for s in all_sections]
    matched_codes = await _classify_sections(body.description, sections_list)
    matched = [s for s in all_sections if s.section_code in matched_codes] or list(all_sections[:3])

    return [
        PartLookupResult(
            section_id=str(s.id),
            section_code=s.section_code,
            section_name=s.section_name,
            diagram_url=s.diagram_url,
            model_code=body.model_code,
        )
        for s in matched
    ]


@router.get("/model/{model_code}/all-sections")
async def get_all_sections_for_model(
    model_code: str,
    db: AsyncSession = Depends(get_db),
    x_sonia_secret: str = Header(default=""),
    current_user=Depends(get_optional_user),
):
    if not verify_sonia_secret(x_sonia_secret, settings.SONIA_BOT_SECRET) and current_user is None:
        raise HTTPException(status_code=403, detail="Forbidden")

    result = await db.execute(
        select(PartsManualSection)
        .where(PartsManualSection.model_code == model_code)
        .order_by(PartsManualSection.section_code)
    )
    return [
        {
            "section_id": str(s.id),
            "section_code": s.section_code,
            "section_name": s.section_name,
            "diagram_url": s.diagram_url,
        }
        for s in result.scalars().all()
    ]


@router.get("/model/{model_code}/item/{order_num}", response_model=PartItemByCodeResult)
async def get_part_by_model_and_code(
    model_code: str,
    order_num: str,
    db: AsyncSession = Depends(get_db),
    x_sonia_secret: str = Header(default=""),
):
    if not verify_sonia_secret(x_sonia_secret, settings.SONIA_BOT_SECRET):
        raise HTTPException(status_code=403, detail="Forbidden")

    result = await db.execute(
        select(PartsManualItem, PartsManualSection, PartsReference)
        .join(PartsManualSection, PartsManualItem.section_id == PartsManualSection.id)
        .join(PartsReference, PartsManualItem.factory_part_number == PartsReference.factory_part_number)
        .where(
            PartsManualSection.model_code == model_code,
            PartsManualItem.order_num == order_num,
        )
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Parte no encontrada")

    item, section, ref = row
    return PartItemByCodeResult(
        factory_part_number=item.factory_part_number,
        description=ref.description,
        description_es=ref.description_es_manual,
        section_code=section.section_code,
        section_name=section.section_name,
        order_num=item.order_num,
    )


@router.get("/section/{section_id}/diagram-image")
async def get_diagram_image(
    section_id: str,
    db: AsyncSession = Depends(get_db),
    x_sonia_secret: str = Header(default=""),
    current_user=Depends(get_optional_user),
):
    """Proxy: descarga la imagen de diagrama desde MinIO. Acepta Sonia secret o JWT."""
    if not verify_sonia_secret(x_sonia_secret, settings.SONIA_BOT_SECRET) and current_user is None:
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        section_uuid = _uuid.UUID(section_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="section_id inválido")

    section = await db.get(PartsManualSection, section_uuid)
    if not section or not section.diagram_url:
        raise HTTPException(status_code=404, detail="Diagrama no encontrado")

    public_base = f"{settings.MINIO_PUBLIC_URL}/{PARTS_BUCKET}/"
    if not section.diagram_url.startswith(public_base):
        raise HTTPException(status_code=404, detail="URL de diagrama no reconocida")

    object_name = section.diagram_url[len(public_base):]
    try:
        client = _minio_client()
        minio_response = client.get_object(PARTS_BUCKET, object_name)
        data = minio_response.read()
        minio_response.close()
    except Exception as e:
        logger.error(f"get_diagram_image MinIO error: {e}")
        raise HTTPException(status_code=502, detail="No se pudo obtener el diagrama")

    content_type = "image/png" if object_name.lower().endswith(".png") else "image/jpeg"
    return Response(content=data, media_type=content_type)


@router.get("/section/{section_id}/item/{order_num}", response_model=PartItemResult)
async def get_part_by_number(
    section_id: str,
    order_num: str,
    db: AsyncSession = Depends(get_db),
    x_sonia_secret: str = Header(default=""),
    current_user=Depends(get_optional_user),
):
    if not verify_sonia_secret(x_sonia_secret, settings.SONIA_BOT_SECRET) and current_user is None:
        raise HTTPException(status_code=403, detail="Forbidden")

    result = await db.execute(
        select(PartsManualItem, PartsManualSection, PartsReference)
        .join(PartsManualSection, PartsManualItem.section_id == PartsManualSection.id)
        .join(PartsReference, PartsManualItem.factory_part_number == PartsReference.factory_part_number)
        .where(PartsManualItem.section_id == section_id, PartsManualItem.order_num == order_num)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Parte no encontrada")

    item, section, ref = row
    return PartItemResult(
        id=str(item.id),
        section_id=str(section.id),
        section_code=section.section_code,
        section_name=section.section_name,
        order_num=item.order_num,
        factory_part_number=item.factory_part_number,
        um_part_number=ref.um_part_number,
        description=ref.description,
        unit=ref.unit,
    )


@router.get("/factory/{factory_code}", response_model=PartReferenceResult)
async def get_part_by_factory_code(
    factory_code: str,
    db: AsyncSession = Depends(get_db),
    x_sonia_secret: str = Header(default=""),
    current_user=Depends(get_optional_user),
):
    if not verify_sonia_secret(x_sonia_secret, settings.SONIA_BOT_SECRET) and current_user is None:
        raise HTTPException(status_code=403, detail="Forbidden")

    result = await db.execute(
        select(PartsReference).where(PartsReference.factory_part_number == factory_code)
    )
    ref = result.scalar_one_or_none()
    if not ref:
        raise HTTPException(status_code=404, detail="Código de fábrica no encontrado")

    return PartReferenceResult(
        factory_part_number=ref.factory_part_number,
        um_part_number=ref.um_part_number,
        description=ref.description,
        unit=ref.unit,
    )


# ── Detección de cambios de código ────────────────────────────────────────────

async def _detect_code_changes(db: AsyncSession) -> int:
    """Detecta posibles cambios de código de fábrica usando similitud de descripción (pg_trgm).
    Crea tareas pendientes en parts_code_review_tasks. Inocuo si se ejecuta varias veces."""
    threshold_record = await db.get(SystemConfig, "parts_similarity_threshold")
    threshold = float(threshold_record.value) if threshold_record else 0.9

    result = await db.execute(text("""
        INSERT INTO parts_code_review_tasks
            (id, existing_code, candidate_code, existing_description, candidate_description,
             similarity_score, status, created_at)
        SELECT DISTINCT ON (spi.part_number, pr.factory_part_number)
            gen_random_uuid(),
            pr.factory_part_number,
            spi.part_number,
            pr.description,
            spi.description,
            similarity(spi.description, pr.description),
            'pending',
            now()
        FROM (
            SELECT DISTINCT ON (part_number) part_number, description, model_applicable
            FROM spare_part_items
            WHERE description IS NOT NULL AND description != ''
              AND model_applicable IS NOT NULL AND model_applicable != ''
            ORDER BY part_number, created_at DESC
        ) spi
        -- Restringir la comparación al mismo modelo de moto
        JOIN vehicle_catalog_map vcm ON vcm.vehicle_model_pattern = spi.model_applicable
        JOIN parts_manual_sections pms ON pms.model_code = vcm.catalog_model_code
        JOIN parts_manual_items pmi ON pmi.section_id = pms.id
        JOIN parts_references pr ON pr.factory_part_number = pmi.factory_part_number
        WHERE similarity(spi.description, pr.description) >= :threshold
          AND spi.part_number != pr.factory_part_number
          -- El candidato no existe ya como código activo en el catálogo con secciones asignadas
          AND NOT EXISTS (
              SELECT 1 FROM parts_references pr2
              JOIN parts_manual_items pmi2 ON pmi2.factory_part_number = pr2.factory_part_number
              WHERE pr2.factory_part_number = spi.part_number
          )
          -- El candidato no es un código previo ya conocido de esta parte (formato dict nuevo o string plano legado)
          AND NOT (
              pr.prev_codes @> to_jsonb(spi.part_number::text)
              OR pr.prev_codes @> jsonb_build_array(jsonb_build_object('code', spi.part_number))
          )
          -- No re-detectar el mismo par si ya está pendiente o rechazado
          AND NOT EXISTS (
              SELECT 1 FROM parts_code_review_tasks t
              WHERE t.candidate_code = spi.part_number
                AND t.existing_code = pr.factory_part_number
                AND t.status IN ('pending', 'rejected')
          )
          -- No agregar un segundo candidato mientras ya hay uno pendiente para este código
          AND NOT EXISTS (
              SELECT 1 FROM parts_code_review_tasks t2
              WHERE t2.existing_code = pr.factory_part_number
                AND t2.status = 'pending'
          )
        ORDER BY spi.part_number, pr.factory_part_number
    """), {"threshold": threshold})
    await db.commit()
    return result.rowcount


async def run_detection_bg() -> None:
    """Wrapper para ejecutar detección en segundo plano con sesión propia."""
    async with async_session_maker() as db:
        try:
            await _detect_code_changes(db)
        except Exception as e:
            logger.error(f"run_detection_bg error: {e}")


# ── Endpoint de consulta — tabla de repuestos cargados ────────────────────────

class PartSubstituteOut(BaseModel):
    substitute_part_code: str
    brand: str
    model: str
    position: int

class PartSubstituteIn(BaseModel):
    substitute_part_code: str
    brand: str
    model: str

class CatalogItemResult(BaseModel):
    factory_part_number: str
    description: str
    description_es: Optional[str]
    public_price: Optional[float]
    section_code: str
    section_name: str
    vehicle_model_name: Optional[str]
    pending_task_id: Optional[str] = None
    pending_candidate_code: Optional[str] = None
    pending_score: Optional[float] = None
    avg_fob_cost: Optional[float] = None
    costo_importado: Optional[float] = None
    precio_distribuidor: Optional[float] = None
    precio_publico_calculado: Optional[float] = None
    substitutes: list[PartSubstituteOut] = []
    rotation_class: Optional[str] = None
    prev_codes: list[str] = []
    needs_price_review: bool = False

class CatalogItemUpdate(BaseModel):
    description: Optional[str] = None
    description_es_manual: Optional[str] = None
    public_price: Optional[float] = None
    substitutes: Optional[list[PartSubstituteIn]] = None
    rotation_class: Optional[Literal['alta', 'media', 'baja']] = None
    prev_codes: Optional[list[str]] = None
    needs_price_review: Optional[bool] = None

class ReplaceCodeRequest(BaseModel):
    new_code: str
    description: Optional[str] = None
    description_es_manual: Optional[str] = None
    public_price: Optional[float] = None

class CatalogListResult(BaseModel):
    total: int
    items: list[CatalogItemResult]


@router.get("/admin/catalog", response_model=CatalogListResult)
async def list_catalog(
    search: str = "",
    model_code: str = "",
    only_pending: bool = False,
    only_price_review: bool = False,
    rotation_class: str = "",
    sort_col: str = "section_code",
    sort_dir: str = "asc",
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Devuelve todos los repuestos cargados con su sección, modelo y datos del catálogo interno."""
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Solo superadmin")

    from app.services.pricing_service import get_pricing_factors, compute_prices
    pricing_factors = await get_pricing_factors(db)

    from sqlalchemy import func, or_

    # Subquery: primera descripción ES por part_number — la primera que llegó queda fija
    spi_latest = (
        select(
            SparePartItem.part_number.label("part_number"),
            SparePartItem.description_es.label("description_es"),
        )
        .where(SparePartItem.description_es.isnot(None))
        .where(SparePartItem.description_es != "")
        .distinct(SparePartItem.part_number)
        .order_by(SparePartItem.part_number, SparePartItem.created_at.asc())
        .subquery("spi_latest")
    )

    # Subquery: tarea pendiente más reciente por existing_code
    pending_sq = (
        select(
            PartsCodeReviewTask.existing_code.label("existing_code"),
            PartsCodeReviewTask.id.label("task_id"),
            PartsCodeReviewTask.candidate_code.label("candidate_code"),
            PartsCodeReviewTask.similarity_score.label("score"),
        )
        .where(PartsCodeReviewTask.status == "pending")
        .distinct(PartsCodeReviewTask.existing_code)
        .order_by(PartsCodeReviewTask.existing_code, PartsCodeReviewTask.similarity_score.desc(), PartsCodeReviewTask.created_at.desc())
        .subquery("pending_sq")
    )

    def _base_joins(q):
        q = (q
            .join(PartsManualItem, PartsManualItem.factory_part_number == PartsReference.factory_part_number)
            .join(PartsManualSection, PartsManualSection.id == PartsManualItem.section_id)
            .outerjoin(VehicleCatalogMap, VehicleCatalogMap.catalog_model_code == PartsManualSection.model_code)
            .outerjoin(PartCatalog, PartCatalog.part_code == PartsReference.factory_part_number)
            .outerjoin(spi_latest, spi_latest.c.part_number == PartsReference.factory_part_number)
            .outerjoin(pending_sq, pending_sq.c.existing_code == PartsReference.factory_part_number)
        )
        if model_code:
            q = q.where(PartsManualSection.model_code == model_code)
        if search:
            term = f"%{search}%"
            from sqlalchemy import cast as sa_cast, Text as SAText
            q = q.where(or_(
                PartsReference.factory_part_number.ilike(term),
                PartsReference.description.ilike(term),
                PartsReference.description_es_manual.ilike(term),
                spi_latest.c.description_es.ilike(term),
                sa_cast(PartsReference.prev_codes, SAText).ilike(term),
            ))
        if only_pending:
            q = q.where(pending_sq.c.task_id.isnot(None))
        if only_price_review:
            q = q.where(PartsReference.needs_price_review == True)
        if rotation_class == "none":
            q = q.where(PartsReference.rotation_class.is_(None))
        elif rotation_class in ("alta", "media", "baja"):
            q = q.where(PartsReference.rotation_class == rotation_class)
        return q

    # Total — cuenta pares únicos (parte, modelo)
    count_q = select(func.count()).select_from(
        _base_joins(
            select(PartsReference.factory_part_number, PartsManualSection.model_code)
        ).distinct().subquery()
    )
    total = (await db.execute(count_q)).scalar_one()

    # Filas — DISTINCT ON (factory_part_number, model_code): una fila por par parte+modelo
    from sqlalchemy import nullslast, cast
    from sqlalchemy import Numeric as SANumeric
    inner_sq = _base_joins(
        select(
            PartsReference.factory_part_number.label("fpn"),
            PartsReference.description.label("description"),
            func.coalesce(PartsReference.description_es_manual, spi_latest.c.description_es).label("description_es"),
            PartCatalog.public_price.label("public_price"),
            PartsManualSection.section_code.label("section_code"),
            PartsManualSection.section_name.label("section_name"),
            PartsManualSection.model_code.label("model_code"),
            VehicleCatalogMap.vehicle_model_pattern.label("vehicle_model_pattern"),
            pending_sq.c.task_id.label("task_id"),
            pending_sq.c.candidate_code.label("candidate_code"),
            pending_sq.c.score.label("score"),
            PartsReference.avg_fob_cost.label("avg_fob_cost"),          # r[11]
            PartsReference.rotation_class.label("rotation_class"),        # r[12]
            PartsReference.needs_price_review.label("needs_price_review"), # r[13]
        )
        .distinct(PartsReference.factory_part_number, PartsManualSection.model_code)
    ).order_by(
        PartsReference.factory_part_number,
        PartsManualSection.model_code,
        PartsManualSection.section_code,
    ).subquery("inner_catalog")

    # Outer query — ORDER BY libre sobre el subquery
    # k_publico: multiplicador para precio_publico desde avg_fob_cost (USD → COP)
    # permite COALESCE(public_price, avg_fob_cost * k) para ordenar Precio Final
    # con fallback a precio calculado cuando no hay precio manual
    _pf = pricing_factors
    k_publico = (
        _pf["import_factor"]
        * (1 + _pf["provider_margin"])
        * (1 + _pf["iva_rate"])
        * (1 + _pf["distributor_margin"])
        * (1 + _pf["iva_rate"])
        * _pf["trm"]
    )
    _SORT_MAP = {
        "factory_part_number": inner_sq.c.fpn,
        "description":         inner_sq.c.description,
        "description_es":      inner_sq.c.description_es,
        "public_price":        func.coalesce(
            cast(inner_sq.c.public_price,  SANumeric(15, 2)),
            cast(inner_sq.c.avg_fob_cost * k_publico, SANumeric(15, 2)),
        ),
        "section_code":        inner_sq.c.section_code,
        "vehicle_model_name":  inner_sq.c.vehicle_model_pattern,
        "avg_fob_cost":        cast(inner_sq.c.avg_fob_cost, SANumeric(12, 4)),
        "rotation_class":       inner_sq.c.rotation_class,
        "needs_price_review":   inner_sq.c.needs_price_review,
    }
    sort_expr = _SORT_MAP.get(sort_col, inner_sq.c.section_code)
    order_expr = nullslast(sort_expr.asc() if sort_dir == "asc" else sort_expr.desc())

    rows_q = (
        select(inner_sq)
        .order_by(order_expr, inner_sq.c.fpn)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(rows_q)).all()

    # Sustitutos y prev_codes para las referencias de esta página
    fpns = [r[0] for r in rows]
    subs_by_fpn: dict[str, list[PartSubstitute]] = {}
    prev_codes_by_fpn: dict[str, list[str]] = {}
    if fpns:
        subs_q = (
            select(PartSubstitute)
            .where(PartSubstitute.factory_part_number.in_(fpns))
            .order_by(PartSubstitute.factory_part_number, PartSubstitute.position)
        )
        for s in (await db.execute(subs_q)).scalars().all():
            subs_by_fpn.setdefault(s.factory_part_number, []).append(s)

        refs_q = select(PartsReference.factory_part_number, PartsReference.prev_codes).where(
            PartsReference.factory_part_number.in_(fpns)
        )
        for fpn_r, codes in (await db.execute(refs_q)).all():
            extracted = []
            for entry in (codes or []):
                if isinstance(entry, dict) and "code" in entry:
                    extracted.append(entry["code"])
                elif isinstance(entry, str) and entry:
                    extracted.append(entry)
            prev_codes_by_fpn[fpn_r] = extracted

    def _build_item(r) -> CatalogItemResult:
        avg_fob = float(r[11]) if r[11] is not None else None
        prices  = compute_prices(avg_fob, pricing_factors)
        fpn = r[0]
        return CatalogItemResult(
            factory_part_number=fpn,
            description=r[1],
            description_es=r[2],
            public_price=float(r[3]) if r[3] is not None else None,
            section_code=r[4],
            section_name=r[5],
            vehicle_model_name=r[7],
            pending_task_id=str(r[8]) if r[8] else None,
            pending_candidate_code=r[9],
            pending_score=float(r[10]) if r[10] is not None else None,
            avg_fob_cost=avg_fob,
            costo_importado=prices["costo_importado"],
            precio_distribuidor=prices["precio_distribuidor"],
            precio_publico_calculado=prices["precio_publico"],
            substitutes=[
                PartSubstituteOut(
                    substitute_part_code=s.substitute_part_code,
                    brand=s.brand,
                    model=s.model,
                    position=s.position,
                )
                for s in subs_by_fpn.get(fpn, [])
            ],
            rotation_class=r[12],
            prev_codes=prev_codes_by_fpn.get(fpn, []),
            needs_price_review=bool(r[13]) if r[13] is not None else False,
        )

    return CatalogListResult(
        total=total,
        items=[_build_item(r) for r in rows],
    )


# ── Limpiar catálogo completo de un modelo ────────────────────────────────────

@router.delete("/admin/catalog/{model_code}", status_code=204)
async def delete_catalog(
    model_code: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Elimina todas las secciones (y sus ítems vía CASCADE) de un model_code. Solo superadmin."""
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Solo superadmin")

    await db.execute(
        sa_delete(PartsManualSection).where(PartsManualSection.model_code == model_code)
    )
    await db.commit()


# ── Eliminación de un repuesto individual del catálogo ───────────────────────

@router.delete("/admin/catalog/part/{factory_part_number:path}", status_code=204)
async def delete_catalog_part(
    factory_part_number: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Elimina un repuesto del catálogo. Bloqueado si tiene costos, historial o pedidos asociados."""
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Solo superadmin")

    ref = await db.get(PartsReference, factory_part_number)
    if not ref:
        raise HTTPException(status_code=404, detail="Referencia no encontrada")

    if ref.avg_fob_cost is not None:
        raise HTTPException(status_code=409, detail="No se puede eliminar: tiene costo promedio calculado.")

    history_count = (await db.execute(
        select(func.count()).select_from(PartCostHistory)
        .where(PartCostHistory.factory_part_number == factory_part_number)
    )).scalar_one()
    if history_count > 0:
        raise HTTPException(status_code=409, detail="No se puede eliminar: tiene historial de costos.")

    catalog = await db.get(PartCatalog, factory_part_number)
    if catalog:
        from app.models.logistics import PartsOrderItem, PurchaseOrderItem
        order_refs = (await db.execute(
            select(func.count()).select_from(PartsOrderItem)
            .where(PartsOrderItem.part_code == factory_part_number)
        )).scalar_one()
        purchase_refs = (await db.execute(
            select(func.count()).select_from(PurchaseOrderItem)
            .where(PurchaseOrderItem.part_code == factory_part_number)
        )).scalar_one()
        if order_refs > 0 or purchase_refs > 0:
            raise HTTPException(status_code=409, detail="No se puede eliminar: tiene órdenes de compra asociadas.")
        await db.delete(catalog)

    await db.execute(
        sa_delete(PartsManualItem).where(PartsManualItem.factory_part_number == factory_part_number)
    )
    await db.execute(
        sa_delete(PartsCodeReviewTask).where(
            (PartsCodeReviewTask.existing_code == factory_part_number) |
            (PartsCodeReviewTask.candidate_code == factory_part_number)
        )
    )
    await db.delete(ref)
    await db.commit()


# ── Edición inline de un repuesto del catálogo ───────────────────────────────

@router.patch("/admin/catalog/{factory_part_number:path}", status_code=200)
async def update_catalog_item(
    factory_part_number: str,
    payload: CatalogItemUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Actualiza descripción, descripción ES manual y/o precio público. Solo superadmin."""
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Solo superadmin")

    ref = await db.get(PartsReference, factory_part_number)
    if not ref:
        raise HTTPException(status_code=404, detail="Referencia no encontrada")

    if payload.description is not None:
        ref.description = payload.description
    if payload.description_es_manual is not None:
        ref.description_es_manual = payload.description_es_manual

    if payload.public_price is not None:
        catalog = await db.get(PartCatalog, factory_part_number)
        if catalog:
            catalog.public_price = payload.public_price
            if payload.description is not None:
                catalog.description = payload.description
        else:
            db.add(PartCatalog(
                part_code=factory_part_number,
                description=payload.description or ref.description,
                public_price=payload.public_price,
            ))

    if payload.rotation_class is not None:
        ref.rotation_class = payload.rotation_class

    if payload.needs_price_review is not None:
        ref.needs_price_review = payload.needs_price_review

    if payload.substitutes is not None:
        await db.execute(
            sa_delete(PartSubstitute).where(PartSubstitute.factory_part_number == factory_part_number)
        )
        for idx, sub in enumerate(payload.substitutes[:3], start=1):
            code = sub.substitute_part_code.strip()
            brand = sub.brand.strip()
            model = sub.model.strip()
            if code and brand and model:
                db.add(PartSubstitute(
                    factory_part_number=factory_part_number,
                    substitute_part_code=code,
                    brand=brand,
                    model=model,
                    position=idx,
                ))

    if payload.prev_codes is not None:
        clean = [c.strip() for c in payload.prev_codes if c.strip() and c.strip() != factory_part_number]
        ref.prev_codes = [{"code": c} for c in clean[:5]]
        from app.services.pricing_service import recalculate_part_cost
        await recalculate_part_cost(db, factory_part_number)

    await db.commit()
    return {"ok": True}


@router.post("/admin/catalog-replace/{factory_part_number:path}", status_code=200)
async def replace_catalog_code(
    factory_part_number: str,
    payload: ReplaceCodeRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Reemplaza manualmente el código de fábrica de un repuesto. Solo superadmin."""
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Solo superadmin")

    new_code = payload.new_code.strip()
    if not new_code:
        raise HTTPException(status_code=422, detail="El nuevo código no puede estar vacío")
    if new_code == factory_part_number:
        raise HTTPException(status_code=422, detail="El nuevo código es igual al actual")

    existing_ref = await db.get(PartsReference, factory_part_number)
    if not existing_ref:
        raise HTTPException(status_code=404, detail="Referencia no encontrada")

    # Si el nuevo código ya existe en el catálogo, no permitir — evitar colisión de PK
    conflict = await db.get(PartsReference, new_code)
    if conflict is not None:
        raise HTTPException(
            status_code=409,
            detail=f"El código '{new_code}' ya existe en el catálogo. Usá el flujo de Verificar si querés unificar dos entradas."
        )

    # Construir prev_codes: el código que sale entra al historial, máx 5
    new_prev = ([{"code": factory_part_number}] + list(existing_ref.prev_codes or []))[:5]

    new_ref = PartsReference(
        factory_part_number=new_code,
        um_part_number=existing_ref.um_part_number,
        description=payload.description.strip() if payload.description else existing_ref.description,
        description_es_manual=payload.description_es_manual,
        unit=existing_ref.unit,
        prev_codes=new_prev,
    )
    db.add(new_ref)
    await db.flush()

    # Redirigir todos los ítems del catálogo al nuevo código
    await db.execute(
        sa_update(PartsManualItem)
        .where(PartsManualItem.factory_part_number == factory_part_number)
        .values(factory_part_number=new_code)
    )
    await db.flush()

    # Migrar entrada de PartCatalog si existe
    old_catalog = await db.get(PartCatalog, factory_part_number)
    if old_catalog:
        new_price = payload.public_price if payload.public_price is not None else float(old_catalog.public_price)
        new_desc  = (payload.description.strip() if payload.description else None) or old_catalog.description
        db.add(PartCatalog(part_code=new_code, description=new_desc, public_price=new_price))
        await db.delete(old_catalog)
        await db.flush()
    elif payload.public_price is not None:
        desc = (payload.description.strip() if payload.description else None) or new_ref.description
        db.add(PartCatalog(part_code=new_code, description=desc, public_price=payload.public_price))

    # Eliminar la referencia vieja
    await db.delete(existing_ref)

    # Cerrar tareas pendientes de revisión que involucren el código viejo
    await db.execute(
        sa_update(PartsCodeReviewTask)
        .where(
            PartsCodeReviewTask.existing_code == factory_part_number,
            PartsCodeReviewTask.status == "pending",
        )
        .values(status="rejected", resolved_at=datetime.utcnow())
    )

    # Recalcular costo promedio para el nuevo código — puede haber SparePartItems con precio
    from app.services.pricing_service import recalculate_part_cost
    await recalculate_part_cost(db, new_code)

    await db.commit()
    return {"ok": True, "new_code": new_code}


# ── Detección manual y revisión de cambios de código ─────────────────────────

@router.post("/admin/backfill-costs")
async def backfill_costs(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Recalcula avg_fob_cost para todas las referencias sin costo que tienen precios en pedidos."""
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Solo superadmin")

    from app.services.pricing_service import recalculate_part_cost

    result = await db.execute(
        select(PartsReference.factory_part_number).where(PartsReference.avg_fob_cost.is_(None))
    )
    codes = [row[0] for row in result.all()]

    updated = 0
    for code in codes:
        before = (await db.get(PartsReference, code))
        await recalculate_part_cost(db, code)
        after = (await db.get(PartsReference, code))
        if after and after.avg_fob_cost is not None:
            updated += 1

    await db.commit()
    return {"checked": len(codes), "updated": updated}


@router.post("/admin/detect-code-changes")
async def detect_code_changes(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Lanza la detección de posibles cambios de código por similitud de descripción. Solo superadmin."""
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Solo superadmin")
    created = await _detect_code_changes(db)
    return {"tasks_created": created}


@router.get("/admin/diagnose-detection")
async def diagnose_detection(
    part_code: str = "",
    description: str = "",
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Diagnóstica por qué un spare_part_item no genera tarea de revisión de código.
    Pasá part_code (el código del pedido) o description (texto a buscar).
    """
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Solo superadmin")

    results = {}

    # Paso 1: ¿Existe el item en spare_part_items?
    if part_code:
        r1 = await db.execute(text("""
            SELECT part_number, description, description_es, model_applicable, unit_price, qty_ordered
            FROM spare_part_items
            WHERE part_number = :code
            ORDER BY created_at DESC LIMIT 5
        """), {"code": part_code.strip().upper().replace(" ", "")})
    else:
        r1 = await db.execute(text("""
            SELECT part_number, description, description_es, model_applicable, unit_price, qty_ordered
            FROM spare_part_items
            WHERE description ILIKE :desc OR description_es ILIKE :desc
            ORDER BY created_at DESC LIMIT 5
        """), {"desc": f"%{description}%"})
    results["1_spare_part_items"] = [dict(r._mapping) for r in r1.all()]

    if not results["1_spare_part_items"]:
        results["conclusion"] = "No existe ningún spare_part_item con ese código/descripción."
        return results

    sample = results["1_spare_part_items"][0]
    pn = sample["part_number"]
    desc = sample["description"]
    model_ap = sample["model_applicable"]

    # Paso 2: ¿Tiene description en inglés?
    results["2_description_en_null"] = desc is None or desc == ""
    results["2_description_es_null"] = sample["description_es"] is None or sample["description_es"] == ""

    # Paso 3: ¿Tiene model_applicable?
    results["3_model_applicable"] = model_ap
    results["3_model_applicable_null"] = model_ap is None or model_ap == ""

    # Paso 4: ¿Existe en vehicle_catalog_map?
    if model_ap:
        r4 = await db.execute(text("""
            SELECT vehicle_model_pattern, catalog_model_code
            FROM vehicle_catalog_map
            WHERE vehicle_model_pattern = :model
        """), {"model": model_ap})
        results["4_vehicle_catalog_map_match"] = [dict(r._mapping) for r in r4.all()]

        # También buscar coincidencias parciales para diagnóstico
        r4b = await db.execute(text("""
            SELECT vehicle_model_pattern, catalog_model_code
            FROM vehicle_catalog_map
            WHERE vehicle_model_pattern ILIKE :model
        """), {"model": f"%{model_ap}%"})
        results["4_vehicle_catalog_map_ilike"] = [dict(r._mapping) for r in r4b.all()]
    else:
        results["4_vehicle_catalog_map_match"] = []
        results["4_vehicle_catalog_map_ilike"] = []

    # Paso 5: ¿El código ya existe en parts_references?
    r5 = await db.execute(text("""
        SELECT factory_part_number, description FROM parts_references
        WHERE factory_part_number = :code
    """), {"code": pn})
    results["5_candidate_already_in_catalog"] = [dict(r._mapping) for r in r5.all()]

    # Paso 6: Similitud real contra el catálogo (sin filtros de modelo)
    if desc:
        r6 = await db.execute(text("""
            SELECT pr.factory_part_number, pr.description,
                   similarity(:desc, pr.description) AS score
            FROM parts_references pr
            WHERE similarity(:desc, pr.description) > 0.4
            ORDER BY score DESC LIMIT 10
        """), {"desc": desc})
        results["6_similarity_scores_in_catalog"] = [dict(r._mapping) for r in r6.all()]
    else:
        results["6_similarity_scores_in_catalog"] = "No hay description en inglés para comparar"

    # Paso 7: ¿Hay tareas ya existentes para este código?
    r7 = await db.execute(text("""
        SELECT id, existing_code, candidate_code, status, similarity_score
        FROM parts_code_review_tasks
        WHERE candidate_code = :code OR existing_code = :code
        ORDER BY created_at DESC LIMIT 5
    """), {"code": pn})
    results["7_existing_tasks"] = [dict(r._mapping) for r in r7.all()]

    # Conclusión automática
    issues = []
    if results["2_description_en_null"]:
        issues.append("description (inglés) es NULL — la query lo filtra antes de comparar")
    if results["3_model_applicable_null"]:
        issues.append("model_applicable es NULL — el JOIN con vehicle_catalog_map falla")
    elif not results["4_vehicle_catalog_map_match"]:
        issues.append(f"model_applicable '{model_ap}' no coincide exactamente con ningún vehicle_model_pattern")
    if results["5_candidate_already_in_catalog"]:
        issues.append("El código del pedido YA existe en parts_references — la detección lo ignora a propósito")
    if results["6_similarity_scores_in_catalog"] and isinstance(results["6_similarity_scores_in_catalog"], list):
        top = results["6_similarity_scores_in_catalog"]
        if top and top[0]["score"] < 0.9:
            issues.append(f"Mejor similitud encontrada: {top[0]['score']:.2f} (umbral es 0.9) — descripción difiere")

    results["conclusion"] = issues if issues else ["No se encontró el problema automáticamente — revisar manualmente los pasos"]
    return results


@router.post("/admin/review-tasks/{task_id}/approve", status_code=200)
async def approve_review_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Aprueba la sustitución de código: el candidato pasa a ser el código activo. Solo superadmin."""
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Solo superadmin")

    task = await db.get(PartsCodeReviewTask, _uuid.UUID(task_id))
    if not task or task.status != "pending":
        raise HTTPException(status_code=404, detail="Tarea no encontrada o ya resuelta")

    existing_ref = await db.get(PartsReference, task.existing_code)
    if not existing_ref:
        raise HTTPException(status_code=404, detail="Código existente no encontrado en el catálogo")

    # El candidato podría ya existir (cargado por otro camino)
    candidate_ref = await db.get(PartsReference, task.candidate_code)

    if candidate_ref is None:
        # Construir nuevo prev_codes: [código que sale] + prev anteriores, máx 5
        new_prev = ([{"code": task.existing_code}] + list(existing_ref.prev_codes or []))[:5]
        candidate_ref = PartsReference(
            factory_part_number=task.candidate_code,
            um_part_number=existing_ref.um_part_number,
            description=existing_ref.description,
            description_es_manual=existing_ref.description_es_manual,
            unit=existing_ref.unit,
            prev_codes=new_prev,
            rotation_class=existing_ref.rotation_class,
        )
        db.add(candidate_ref)
        await db.flush()
    else:
        # El candidato ya existe — heredar campos del existente si no los tiene
        prev = candidate_ref.prev_codes or []
        existing_in_prev = any(
            (e["code"] == task.existing_code if isinstance(e, dict) else e == task.existing_code)
            for e in prev
        )
        if not existing_in_prev:
            candidate_ref.prev_codes = ([{"code": task.existing_code}] + list(prev))[:5]
        if candidate_ref.rotation_class is None and existing_ref.rotation_class is not None:
            candidate_ref.rotation_class = existing_ref.rotation_class
        if candidate_ref.description_es_manual is None and existing_ref.description_es_manual is not None:
            candidate_ref.description_es_manual = existing_ref.description_es_manual

    # Redirigir todos los items del catálogo al nuevo código
    await db.execute(
        sa_update(PartsManualItem)
        .where(PartsManualItem.factory_part_number == task.existing_code)
        .values(factory_part_number=task.candidate_code)
    )
    await db.flush()

    # Eliminar la referencia vieja (ya no tiene items apuntando a ella)
    await db.delete(existing_ref)

    # Resolver tarea
    task.status = "approved"
    task.resolved_at = datetime.utcnow()
    task.resolved_by = current_user.user_id

    # Rechazar automáticamente otras tareas pendientes para el mismo código existente
    await db.execute(
        sa_update(PartsCodeReviewTask)
        .where(
            PartsCodeReviewTask.existing_code == task.existing_code,
            PartsCodeReviewTask.id != task.id,
            PartsCodeReviewTask.status == "pending",
        )
        .values(status="rejected", resolved_at=datetime.utcnow())
    )

    from app.services.pricing_service import recalculate_part_cost
    await recalculate_part_cost(db, task.candidate_code)

    await db.commit()
    return {"ok": True, "new_code": task.candidate_code}


@router.post("/admin/review-tasks/{task_id}/reject", status_code=200)
async def reject_review_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Descarta la sugerencia de cambio de código. Solo superadmin."""
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Solo superadmin")

    task = await db.get(PartsCodeReviewTask, _uuid.UUID(task_id))
    if not task or task.status != "pending":
        raise HTTPException(status_code=404, detail="Tarea no encontrada o ya resuelta")

    task.status = "rejected"
    task.resolved_at = datetime.utcnow()
    task.resolved_by = current_user.user_id
    await db.commit()
    return {"ok": True}


# ── Endpoint de administración (frontend) ──────────────────────────────────────

@router.post("/admin/load-section", response_model=LoadSectionResult)
async def load_section(
    pdf_file: UploadFile = File(...),
    model_code: str = Form(...),
    vehicle_model: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Carga una sección del catálogo de partes desde un PDF. Solo superadmin."""
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Solo superadmin puede cargar catálogos")

    filename = pdf_file.filename or "unknown.pdf"
    section_code, section_name = _parse_section_filename(filename)

    pdf_bytes = await pdf_file.read()

    fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(pdf_bytes)

        # 1. Extraer ilustración del PDF
        illus_bytes: bytes | None = None
        try:
            doc = fitz.open(tmp_path)
            imgs = doc[0].get_images(full=True)
            if imgs:
                base_img = doc.extract_image(imgs[0][0])
                illus_bytes = base_img["image"]
            else:
                pix = doc[0].get_pixmap(matrix=fitz.Matrix(2, 2))
                illus_bytes = pix.tobytes("png")
            doc.close()
        except Exception as e:
            logger.warning(f"load_section illustration extract error ({filename}): {e}")

        # 2. Parsear tabla de repuestos
        parts: list[dict] = []
        try:
            parts = _parse_parts_table(tmp_path)
        except Exception as e:
            logger.warning(f"load_section parse error ({filename}): {e}")

        # 3. Obtener logo de la configuración del sistema
        logo_bytes: bytes | None = None
        try:
            logo_record = await db.get(SystemConfig, "logo_base64")
            if logo_record and logo_record.value:
                b64 = logo_record.value
                if "," in b64:
                    b64 = b64.split(",", 1)[1]
                logo_bytes = base64.b64decode(b64)
        except Exception as e:
            logger.warning(f"load_section logo fetch error: {e}")

        # 4. Generar card estilizada y subir a MinIO
        diagram_url = None
        png_bytes: bytes | None = None

        if illus_bytes:
            try:
                from app.services.diagram_styler import create_diagram_card
                png_bytes = create_diagram_card(
                    illus_bytes=illus_bytes,
                    section_code=section_code,
                    section_name=section_name,
                    model_name=vehicle_model,
                    parts=parts,
                    logo_bytes=logo_bytes,
                )
            except Exception:
                logger.exception(f"load_section diagram_styler failed ({filename})")

        # Fallback: render página completa si el styler falló o no había ilustración
        if not png_bytes:
            logger.warning(f"load_section using full-page render fallback ({filename})")
            try:
                doc = fitz.open(tmp_path)
                pix = doc[0].get_pixmap(matrix=fitz.Matrix(2, 2))
                png_bytes = pix.tobytes("png")
                doc.close()
            except Exception as e:
                logger.error(f"load_section fallback render failed ({filename}): {e}")

        if png_bytes:
            try:
                client = _minio_client()
                _ensure_parts_bucket(client)
                object_name = f"{model_code}/{section_code}.png"
                client.put_object(
                    bucket_name=PARTS_BUCKET,
                    object_name=object_name,
                    data=io.BytesIO(png_bytes),
                    length=len(png_bytes),
                    content_type="image/png",
                )
                diagram_url = _diagram_public_url(object_name)
            except Exception as e:
                logger.error(f"load_section MinIO upload error ({filename}): {e}")

    finally:
        os.unlink(tmp_path)

    # 3. Eliminar sección anterior
    await db.execute(
        sa_delete(PartsManualSection).where(
            PartsManualSection.model_code == model_code,
            PartsManualSection.section_code == section_code,
        )
    )

    # 4. Insertar sección nueva
    section = PartsManualSection(
        model_code=model_code,
        section_code=section_code,
        section_name=section_name,
        diagram_url=diagram_url,
    )
    db.add(section)
    await db.flush()

    # 5. Upsert references + insertar items
    refs_new = 0
    seen_refs: set[str] = set()
    for p in parts:
        factory = p.get("factory_part_number", "").strip()
        if not factory:
            continue

        if factory not in seen_refs:
            existing_ref = await db.get(PartsReference, factory)
            if not existing_ref:
                db.add(PartsReference(
                    factory_part_number=factory,
                    um_part_number=p.get("um_part_number", ""),
                    description=p.get("description", ""),
                    unit=p.get("unit"),
                ))
                refs_new += 1
            seen_refs.add(factory)

        db.add(PartsManualItem(
            section_id=section.id,
            order_num=p["order_num"],
            factory_part_number=factory,
        ))

    # 6. Upsert VehicleCatalogMap
    catalog_map = await db.get(VehicleCatalogMap, vehicle_model)
    if catalog_map:
        catalog_map.catalog_model_code = model_code
    else:
        db.add(VehicleCatalogMap(
            vehicle_model_pattern=vehicle_model,
            catalog_model_code=model_code,
        ))

    await db.commit()

    return LoadSectionResult(
        section_code=section_code,
        section_name=section_name,
        diagram_url=diagram_url,
        parts_loaded=len(parts),
        references_new=refs_new,
    )


# ── Rotation class — bulk import, coverage dashboard, unordered export ─────────

import openpyxl


_VALID_ROTATION = {"alta", "media", "baja"}
_ROTATION_MAP = {
    "alta": "alta", "a": "alta",
    "media": "media", "b": "media",
    "baja": "baja", "c": "baja",
}


def _normalize_part_code(s: str) -> str:
    return str(s).strip().upper().replace(" ", "")


def _find_header_row(sheet, expected_cols: set[str]) -> int:
    """Return the 1-based row index of the header row (case-insensitive match)."""
    for row_idx in range(1, min(sheet.max_row + 1, 20)):
        row_vals = {
            str(sheet.cell(row_idx, c).value or "").strip().lower()
            for c in range(1, sheet.max_column + 1)
        }
        if expected_cols & row_vals:
            return row_idx
    raise ValueError("No header row found with required columns")


def _build_col_map(sheet, header_row: int) -> dict[str, int]:
    """Return {normalized_col_name: col_index (1-based)} for the header row."""
    col_map: dict[str, int] = {}
    for c in range(1, sheet.max_column + 1):
        val = sheet.cell(header_row, c).value
        if val is not None:
            col_map[str(val).strip().lower()] = c
    return col_map


def _cell(sheet, row_idx: int, col_map: dict[str, int], *col_names: str):
    """Return the value of the first matching column name found in col_map."""
    for name in col_names:
        if name in col_map:
            return sheet.cell(row_idx, col_map[name]).value
    return None


@router.post("/admin/rotation-import", status_code=200)
async def import_rotation(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Bulk-assign rotation_class from an Excel file. Solo superadmin."""
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Solo superadmin")

    content = await file.read()
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    sheet = wb.active

    _CODE_ALIASES = {"part_code", "factory_part_number", "codigo", "código", "codigo_parte",
                     "referencia", "ref", "part number", "reference", "numero_parte", "numero parte"}
    _RC_ALIASES   = {"rotation_class", "rotacion", "rotación", "clase", "clase_rotacion",
                     "clase_rotación", "clase rotacion", "clase rotación", "tipo_rotacion",
                     "tipo_rotación", "tipo rotacion"}
    expected = _CODE_ALIASES | _RC_ALIASES
    try:
        header_row = _find_header_row(sheet, expected)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    col_map = _build_col_map(sheet, header_row)

    # verify that at least one code column and one rotation column are present
    has_code = any(a in col_map for a in _CODE_ALIASES)
    has_rc   = any(a in col_map for a in _RC_ALIASES)
    if not has_code or not has_rc:
        missing = []
        if not has_code: missing.append("código de parte (ej: 'part_code' o 'codigo')")
        if not has_rc:   missing.append("clasificación (ej: 'rotation_class' o 'rotacion')")
        raise HTTPException(status_code=422, detail=f"Faltan columnas requeridas: {', '.join(missing)}")

    code_cols = list(_CODE_ALIASES)
    rc_cols   = list(_RC_ALIASES)

    updated, skipped, errors = 0, 0, []

    for row_idx in range(header_row + 1, sheet.max_row + 1):
        code_raw = _cell(sheet, row_idx, col_map, *code_cols)
        rc_raw   = _cell(sheet, row_idx, col_map, *rc_cols)

        if not code_raw and not rc_raw:
            # blank row — skip silently
            continue

        if not code_raw:
            skipped += 1
            errors.append({"row": row_idx, "code": None, "reason": "missing_part_code"})
            continue

        code_n = _normalize_part_code(code_raw)
        rc_n   = _ROTATION_MAP.get(str(rc_raw or "").strip().lower())

        if rc_n is None:
            skipped += 1
            errors.append({"row": row_idx, "code": code_n, "reason": "invalid_rotation_class"})
            continue

        res = await db.execute(
            sa_update(PartsReference)
            .where(PartsReference.factory_part_number == code_n)
            .where(PartsReference.rotation_class.is_(None))
            .values(rotation_class=rc_n)
        )
        if res.rowcount == 0:
            skipped += 1
            errors.append({"row": row_idx, "code": code_n, "reason": "part_not_found"})
        else:
            updated += 1

    await db.commit()
    return {"updated": updated, "skipped": skipped, "errors": errors}


# ── Coverage dashboard ─────────────────────────────────────────────────────────

from pydantic import BaseModel as _BM


class CoverageBucket(_BM):
    rotation_class: str
    total: int
    aqui: int
    en_camino: int
    no_pedidas: int
    pct_aqui: float
    pct_en_camino: float
    pct_no_pedidas: float


class CoverageResponse(_BM):
    sin_clasificar: int
    buckets: list[CoverageBucket]


@router.get("/admin/coverage", response_model=CoverageResponse)
async def get_coverage(
    model_code: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Resumen de cobertura de repuestos por rotation_class. Solo superadmin."""
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Solo superadmin")

    model_filter = """
        AND r.factory_part_number IN (
            SELECT i.factory_part_number
            FROM parts_manual_items i
            JOIN parts_manual_sections s ON s.id = i.section_id
            WHERE s.model_code = :model_code
        )
    """ if model_code else """
        AND EXISTS (
            SELECT 1 FROM parts_manual_items pmi
            WHERE pmi.factory_part_number = r.factory_part_number
        )
    """

    coverage_sql = text(f"""
        WITH
        aqui AS (
            SELECT UPPER(TRIM(REPLACE(part_number, ' ', ''))) AS pn
            FROM spare_part_items
            WHERE qty_physical IS NOT NULL AND qty_physical > 0
            GROUP BY 1
        ),
        en_camino AS (
            SELECT UPPER(TRIM(REPLACE(part_number, ' ', ''))) AS pn
            FROM spare_part_items
            WHERE qty_received > 0 AND qty_physical IS NULL
              AND UPPER(TRIM(REPLACE(part_number, ' ', ''))) NOT IN (SELECT pn FROM aqui)
            UNION
            SELECT UPPER(TRIM(part_code)) AS pn
            FROM part_catalog
            WHERE public_price IS NOT NULL
              AND UPPER(TRIM(part_code)) NOT IN (SELECT pn FROM aqui)
        ),
        coverage AS (
            SELECT
                r.rotation_class,
                COUNT(*) AS total,
                COUNT(CASE WHEN a.pn IS NOT NULL THEN 1 END) AS aqui,
                COUNT(CASE WHEN c.pn IS NOT NULL AND a.pn IS NULL THEN 1 END) AS en_camino,
                COUNT(CASE WHEN a.pn IS NULL AND c.pn IS NULL THEN 1 END) AS no_pedidas
            FROM parts_references r
            LEFT JOIN aqui      a ON a.pn = UPPER(TRIM(r.factory_part_number))
            LEFT JOIN en_camino c ON c.pn = UPPER(TRIM(r.factory_part_number))
            WHERE r.rotation_class IS NOT NULL
            {model_filter}
            GROUP BY r.rotation_class
        )
        SELECT * FROM coverage
        ORDER BY CASE rotation_class WHEN 'alta' THEN 1 WHEN 'media' THEN 2 WHEN 'baja' THEN 3 ELSE 4 END
    """)

    sin_sql = text(f"""
        SELECT COUNT(*) FROM parts_references r
        WHERE rotation_class IS NULL
        {model_filter}
    """)

    params = {"model_code": model_code} if model_code else {}
    rows = (await db.execute(coverage_sql, params)).all()
    sin_clasificar = (await db.execute(sin_sql, params)).scalar_one()

    clases: list[CoverageBucket] = []
    for row in rows:
        total     = row.total
        aqui      = row.aqui
        en_camino = row.en_camino
        no_pedidas = row.no_pedidas
        pct_aqui       = round((aqui      / total) * 100, 2) if total else 0.0
        pct_en_camino  = round((en_camino / total) * 100, 2) if total else 0.0
        pct_no_pedidas = round((no_pedidas / total) * 100, 2) if total else 0.0
        clases.append(CoverageBucket(
            rotation_class=row.rotation_class,
            total=total,
            aqui=aqui,
            en_camino=en_camino,
            no_pedidas=no_pedidas,
            pct_aqui=pct_aqui,
            pct_en_camino=pct_en_camino,
            pct_no_pedidas=pct_no_pedidas,
        ))

    return CoverageResponse(sin_clasificar=int(sin_clasificar), buckets=clases)


# ── Unordered parts export ─────────────────────────────────────────────────────

@router.get("/admin/coverage/unordered")
async def export_unordered(
    rotation_class: Optional[Literal['alta', 'media', 'baja', 'all']] = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Exporta repuestos clasificados sin SparePartItems a Excel. Solo superadmin."""
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Solo superadmin")

    params: dict = {}
    rc_clause = ""
    if rotation_class and rotation_class != 'all':
        rc_clause = "AND r.rotation_class = :rc"
        params["rc"] = rotation_class

    unordered_sql = text(f"""
        SELECT
            r.factory_part_number,
            r.um_part_number,
            r.description,
            r.description_es_manual,
            r.rotation_class,
            r.avg_fob_cost,
            (
                SELECT STRING_AGG(DISTINCT s.model_code, ', ' ORDER BY s.model_code)
                FROM parts_manual_items i
                JOIN parts_manual_sections s ON s.id = i.section_id
                WHERE i.factory_part_number = r.factory_part_number
            ) AS models
        FROM parts_references r
        WHERE r.rotation_class IS NOT NULL
          {rc_clause}
          AND UPPER(TRIM(r.factory_part_number)) NOT IN (
              SELECT DISTINCT UPPER(TRIM(REPLACE(part_number, ' ', '')))
              FROM spare_part_items
              WHERE qty_physical IS NOT NULL OR qty_received > 0
          )
        ORDER BY r.rotation_class, r.factory_part_number
    """)

    rows = (await db.execute(unordered_sql, params)).all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Unordered Parts"
    headers = [
        "factory_part_number",
        "um_part_number",
        "description",
        "description_es_manual",
        "rotation_class",
        "avg_fob_cost",
        "motocicleta",
    ]
    ws.append(headers)
    for row in rows:
        ws.append([
            row.factory_part_number,
            row.um_part_number,
            row.description,
            row.description_es_manual,
            row.rotation_class,
            float(row.avg_fob_cost) if row.avg_fob_cost is not None else None,
            row.models,
        ])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    rc_label = rotation_class or "all"
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    filename = f"unordered_parts_{rc_label}_{date_str}.xlsx"

    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


