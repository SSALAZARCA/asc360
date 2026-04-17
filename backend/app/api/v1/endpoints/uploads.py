from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from typing import List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models.order import ServiceOrderReception
from app.services.pdf_service import upload_file_to_minio

router = APIRouter()

@router.post("/{order_id}/photos", status_code=status.HTTP_200_OK)
async def upload_reception_photos(
    order_id: UUID,
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db)
):
    """Sube 1 o varias fotos de evidencia para la Recepción y las guarda en MinIO y DB."""
    
    # 1. Buscar la Orden y su Recepción hija
    stmt = select(ServiceOrderReception).where(ServiceOrderReception.order_id == order_id)
    reception = (await db.execute(stmt)).scalar_one_or_none()
    
    if not reception:
        raise HTTPException(status_code=404, detail="Recepción no encontrada para esa Orden")
        
    uploaded_urls = []
    
    # 2. Iterar sobre los archivos binarios que envíe Sonia
    for file in files:
        contents = await file.read()
        file_url = await upload_file_to_minio(
            file_bytes=contents, 
            file_name=file.filename, 
            content_type=file.content_type
        )
        if file_url:
            uploaded_urls.append(file_url)
            
    # 3. Anexar al arreglo en BD
    # Debido a que JSONB manipulación directa puede requerir cast en SQLite, pero en AsyncPG lo podemos reemplazar:
    current_photos = list(reception.damage_photos_urls) if reception.damage_photos_urls else []
    current_photos.extend(uploaded_urls)
    
    reception.damage_photos_urls = current_photos
    await db.commit()
    
    return {"message": "Fotos procesadas con éxito", "uploaded_urls": uploaded_urls}
