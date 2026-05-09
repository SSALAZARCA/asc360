import json as json_lib
from fastapi import APIRouter, Depends, Header, HTTPException, status, UploadFile, File, Form
from typing import List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models.order import ServiceOrderReception
from app.services.pdf_service import upload_file_to_minio
from app.config import settings
from app.core.security import verify_sonia_secret

router = APIRouter()

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

@router.post("/{order_id}/photos", status_code=status.HTTP_200_OK)
async def upload_reception_photos(
    order_id: UUID,
    files: Optional[List[UploadFile]] = File(None),
    descriptions: Optional[str] = Form(None),
    text_observations: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    x_sonia_secret: Optional[str] = Header(None),
):
    if not verify_sonia_secret(x_sonia_secret, settings.SONIA_BOT_SECRET):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado")
    """
    Sube fotos de evidencia y/o observaciones de texto para la Recepción.
    - files: lista de imágenes (opcional)
    - descriptions: JSON array de strings, una por foto, en el mismo orden
    - text_observations: JSON array de strings para observaciones sin foto

    Almacena en damage_photos_urls como objetos:
      {"url": "...", "desc": "..."}  para fotos
      {"type": "text", "desc": "..."}  para texto puro
    """
    stmt = select(ServiceOrderReception).where(ServiceOrderReception.order_id == order_id)
    reception = (await db.execute(stmt)).scalar_one_or_none()

    if not reception:
        raise HTTPException(status_code=404, detail="Recepción no encontrada para esa Orden")

    desc_list: list[str] = []
    if descriptions:
        try:
            desc_list = json_lib.loads(descriptions)
        except Exception:
            desc_list = []

    current_evidence = list(reception.damage_photos_urls) if reception.damage_photos_urls else []
    uploaded_urls = []

    if files:
        for i, file in enumerate(files):
            if file.content_type not in ALLOWED_MIME_TYPES:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Tipo de archivo no permitido: {file.content_type}. Solo se aceptan imágenes."
                )
            contents = await file.read()
            if len(contents) > MAX_FILE_SIZE_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"El archivo '{file.filename}' supera el límite de 10 MB."
                )
            file_url = await upload_file_to_minio(
                file_bytes=contents,
                file_name=file.filename,
                content_type=file.content_type
            )
            if file_url:
                desc = desc_list[i] if i < len(desc_list) else ""
                current_evidence.append({"url": file_url, "desc": desc})
                uploaded_urls.append(file_url)

    if text_observations:
        try:
            obs_list = json_lib.loads(text_observations)
            for obs in obs_list:
                if obs and obs.strip():
                    current_evidence.append({"type": "text", "desc": obs.strip()})
        except Exception:
            pass

    reception.damage_photos_urls = current_evidence
    await db.commit()

    return {
        "message": "Evidencia procesada con éxito",
        "uploaded_urls": uploaded_urls,
        "total_evidence": len(current_evidence),
    }
