import io
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
import pdfplumber
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from minio import Minio
from pydantic import BaseModel
from sqlalchemy import delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from openai import AsyncOpenAI

from app.api.deps import get_current_user
from app.config import settings
from app.database import get_db
from app.models.order import ServiceOrder
from app.models.imports import VehicleModel
from app.models.parts_manual import (
    PartsManualItem, PartsManualSection, PartsReference, VehicleCatalogMap,
)

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
    """'B01_BODY COMP FRAME_FLOOR STEP.pdf' → ('B01', 'BODY COMP FRAME / FLOOR STEP')"""
    stem = Path(filename).stem
    parts = stem.split("_", 1)
    code = parts[0].strip()
    name = parts[1].replace("_", " / ").strip() if len(parts) > 1 else stem
    return code, name


_HEADER_KEYWORDS = {
    "order_num":   ["page", "no.", "no ", "item", "pos"],
    "factory":     ["factory", "part no", "part num"],
    "um":          ["um part", "um no"],
    "description": ["description", "descrip"],
    "unit":        ["unit"],
}


def _detect_col(header_row: list, keywords: list) -> int:
    for i, cell in enumerate(header_row):
        if cell is None:
            continue
        cell_lower = str(cell).lower().strip()
        for kw in keywords:
            if kw in cell_lower:
                return i
    return -1


def _parse_parts_table(pdf_path: str) -> list[dict]:
    parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for table in (page.extract_tables() or []):
                if not table or len(table) < 2:
                    continue
                header_idx, col_map = -1, {}
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
                        for field, kws in _HEADER_KEYWORDS.items():
                            col_map[field] = _detect_col(row, kws)
                        break
                if header_idx < 0:
                    continue
                for row in table[header_idx + 1:]:
                    if not row:
                        continue

                    def get(field):
                        idx = col_map.get(field, -1)
                        if idx < 0 or idx >= len(row):
                            return None
                        v = row[idx]
                        return str(v).strip() if v is not None else None

                    order_num = get("order_num")
                    factory   = get("factory")
                    if not order_num or not factory:
                        continue
                    if order_num.lower() in ("page", "no.", "no", "item", "pos", ""):
                        continue
                    parts.append({
                        "order_num":           order_num,
                        "factory_part_number": factory,
                        "um_part_number":      get("um") or "",
                        "description":         get("description") or "",
                        "unit":                get("unit"),
                    })
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
    if x_sonia_secret != settings.SONIA_BOT_SECRET:
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
):
    if x_sonia_secret != settings.SONIA_BOT_SECRET:
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

        # 1. Renderizar página → PNG → MinIO
        diagram_url = None
        try:
            doc = fitz.open(tmp_path)
            pix = doc[0].get_pixmap(matrix=fitz.Matrix(150 / 72, 150 / 72))
            png_bytes = pix.tobytes("png")

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
            logger.warning(f"load_section render/upload error ({filename}): {e}")

        # 2. Parsear tabla de repuestos
        parts: list[dict] = []
        try:
            parts = _parse_parts_table(tmp_path)
        except Exception as e:
            logger.warning(f"load_section parse error ({filename}): {e}")

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
