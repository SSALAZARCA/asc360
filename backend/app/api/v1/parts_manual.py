import io
import json
import logging
import os
import tempfile
import uuid as _uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
import pdfplumber
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from minio import Minio
from pydantic import BaseModel
from sqlalchemy import delete as sa_delete, update as sa_update, text, exists
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from openai import AsyncOpenAI

from app.api.deps import get_current_user
from app.config import settings
from app.database import get_db, async_session_maker
from app.models.order import ServiceOrder
from app.models.imports import VehicleModel, SparePartItem
from app.models.logistics import PartCatalog
from app.models.parts_manual import (
    PartsManualItem, PartsManualSection, PartsReference, VehicleCatalogMap,
    PartsCodeReviewTask,
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
        code = stem
        name = stem
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
          -- El candidato no existe ya como código activo
          AND NOT EXISTS (
              SELECT 1 FROM parts_references pr2
              WHERE pr2.factory_part_number = spi.part_number
          )
          -- El candidato no es un código previo ya conocido de esta parte
          AND NOT (pr.prev_codes @> to_jsonb(spi.part_number::text))
          -- No hay ya una tarea pendiente o aprobada para este par
          AND NOT EXISTS (
              SELECT 1 FROM parts_code_review_tasks t
              WHERE t.candidate_code = spi.part_number
                AND t.existing_code = pr.factory_part_number
                AND t.status IN ('pending', 'approved')
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

class CatalogItemUpdate(BaseModel):
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
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Devuelve todos los repuestos cargados con su sección, modelo y datos del catálogo interno."""
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Solo superadmin")

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
        .order_by(PartsCodeReviewTask.existing_code, PartsCodeReviewTask.created_at.desc())
        .subquery("pending_sq")
    )

    def _base_joins(q):
        q = (q
            .join(PartsManualItem, PartsManualItem.factory_part_number == PartsReference.factory_part_number)
            .join(PartsManualSection, PartsManualSection.id == PartsManualItem.section_id)
            .outerjoin(PartCatalog, PartCatalog.part_code == PartsReference.factory_part_number)
            .outerjoin(spi_latest, spi_latest.c.part_number == PartsReference.factory_part_number)
            .outerjoin(pending_sq, pending_sq.c.existing_code == PartsReference.factory_part_number)
        )
        if model_code:
            q = q.where(PartsManualSection.model_code == model_code)
        if search:
            term = f"%{search}%"
            q = q.where(or_(
                PartsReference.factory_part_number.ilike(term),
                PartsReference.description.ilike(term),
                spi_latest.c.description_es.ilike(term),
            ))
        if only_pending:
            q = q.where(pending_sq.c.task_id.isnot(None))
        return q

    # Total
    count_q = select(func.count()).select_from(
        _base_joins(select(PartsReference.factory_part_number)).distinct().subquery()
    )
    total = (await db.execute(count_q)).scalar_one()

    # Filas
    rows_q = _base_joins(
        select(
            PartsReference.factory_part_number,   # 0
            PartsReference.description,            # 1
            func.coalesce(PartsReference.description_es_manual, spi_latest.c.description_es).label("description_es"),  # 2
            PartCatalog.public_price,              # 3
            PartsManualSection.section_code,       # 4
            PartsManualSection.section_name,       # 5
            PartsManualSection.model_code,         # 6
            VehicleCatalogMap.vehicle_model_pattern,  # 7
            pending_sq.c.task_id,                  # 8
            pending_sq.c.candidate_code,           # 9
            pending_sq.c.score,                    # 10
        )
        .distinct(PartsReference.factory_part_number)
    )
    rows_q = rows_q.order_by(
        PartsReference.factory_part_number,
        PartsManualSection.model_code,
        PartsManualSection.section_code,
    ).offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(rows_q)).all()

    return CatalogListResult(
        total=total,
        items=[
            CatalogItemResult(
                factory_part_number=r[0],
                description=r[1],
                description_es=r[2],
                public_price=float(r[3]) if r[3] is not None else None,
                section_code=r[4],
                section_name=r[5],
                vehicle_model_name=r[7],
                pending_task_id=str(r[8]) if r[8] else None,
                pending_candidate_code=r[9],
                pending_score=float(r[10]) if r[10] is not None else None,
            )
            for r in rows
        ],
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


# ── Edición inline de un repuesto del catálogo ───────────────────────────────

@router.patch("/admin/catalog/{factory_part_number}", status_code=200)
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

    await db.commit()
    return {"ok": True}


# ── Detección manual y revisión de cambios de código ─────────────────────────

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
        # Construir nuevo prev_codes: [código que sale] + prev anteriores, máx 2
        new_prev = ([task.existing_code] + list(existing_ref.prev_codes or []))[:2]
        candidate_ref = PartsReference(
            factory_part_number=task.candidate_code,
            um_part_number=existing_ref.um_part_number,
            description=existing_ref.description,
            unit=existing_ref.unit,
            prev_codes=new_prev,
        )
        db.add(candidate_ref)
        await db.flush()
    else:
        # El candidato ya existe — solo actualizar prev_codes si hace falta
        existing_in_prev = task.existing_code in (candidate_ref.prev_codes or [])
        if not existing_in_prev:
            candidate_ref.prev_codes = ([task.existing_code] + list(candidate_ref.prev_codes or []))[:2]

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
