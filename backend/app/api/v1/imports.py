import uuid
import io
import mimetypes
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from starlette.responses import StreamingResponse

from app.database import get_db
from app.api.deps import get_current_user, CurrentUser
from app.models.imports import ShipmentOrder, SparePartLot, ShipmentMotoUnit, ImportAttachment, SparePartItem, ReconciliationResult, Backorder, VehicleModel
from app.models.tenant import Tenant, EstadoRed
from app.schemas.imports import (
    ShipmentOrderRead, ShipmentOrderCreate, ShipmentOrderUpdate, ShipmentOrderListResponse,
    ImportExcelResult, MotoUnitRead, MotoUnitUpdate, ImportAttachmentRead,
    SparePartLotRead, SparePartItemRead, SparePartItemUpdate,
    ReconciliationResultRead, ReconciliationResultUpdate, BackorderRead, BackorderUpdate,
    BackorderBulkUpdatePI,
)
from app.services import imports_service
from app.services.imports_service import compute_status
from app.services import storage_service
from app.services import dim_parser_service, certificate_service

router = APIRouter(prefix="/imports", tags=["Imports"])

ALLOWED_EXCEL_TYPES = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/octet-stream",
)


def _require_imports_editor(current_user: CurrentUser) -> CurrentUser:
    if not current_user.is_imports_editor:
        raise HTTPException(status_code=403, detail="Sin permisos para el módulo de importaciones")
    return current_user


def _require_superadmin(current_user: CurrentUser) -> CurrentUser:
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Solo superadmin puede realizar esta acción")
    return current_user


# ---------------------------------------------------------------------------
# Importar Excel de Shipment Status
# ---------------------------------------------------------------------------

@router.post("/shipment-excel", response_model=ImportExcelResult, status_code=status.HTTP_200_OK)
async def upload_shipment_excel(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_superadmin(current_user)

    if not file.filename.endswith(".xlsx"):
        raise HTTPException(
            status_code=422,
            detail={"detail": "Solo se aceptan archivos .xlsx", "code": "INVALID_FILE_TYPE"}
        )

    file_bytes = await file.read()
    result = await imports_service.import_shipment_excel(db, file_bytes, current_user)
    return result


# ---------------------------------------------------------------------------
# Importar Packing List de motos (VINs + engine numbers por pedido)
# ---------------------------------------------------------------------------

@router.post("/shipping-doc-excel", status_code=status.HTTP_200_OK)
async def upload_shipping_doc_excel(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_superadmin(current_user)

    if not file.filename.endswith(".xlsx"):
        raise HTTPException(
            status_code=422,
            detail={"detail": "Solo se aceptan archivos .xlsx", "code": "INVALID_FILE_TYPE"}
        )

    file_bytes = await file.read()
    result = await imports_service.import_shipping_doc_excel(db, file_bytes, current_user)
    return {"message": "Procesado correctamente", "result": result}


# ---------------------------------------------------------------------------
# Listado de shipment orders con filtros y paginación
# ---------------------------------------------------------------------------

@router.get("/shipment-orders", response_model=ShipmentOrderListResponse)
async def list_shipment_orders(
    cycle: Optional[int] = None,
    is_spare_part: Optional[bool] = None,
    computed_status: Optional[str] = None,
    pi_number: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_imports_editor(current_user)

    page_size = min(page_size, 200)
    skip = (page - 1) * page_size

    # Construir filtros
    filters = []
    if cycle is not None:
        filters.append(ShipmentOrder.cycle == cycle)
    if is_spare_part is not None:
        filters.append(ShipmentOrder.is_spare_part == is_spare_part)
    if computed_status:
        filters.append(ShipmentOrder.computed_status == computed_status)
    if pi_number:
        filters.append(ShipmentOrder.pi_number.ilike(f"%{pi_number}%"))
    if search:
        filters.append(
            ShipmentOrder.pi_number.ilike(f"%{search}%") |
            ShipmentOrder.model.ilike(f"%{search}%")
        )

    # Total
    count_stmt = select(func.count()).select_from(ShipmentOrder)
    if filters:
        count_stmt = count_stmt.where(*filters)
    total = (await db.execute(count_stmt)).scalar_one()

    # Items
    stmt = select(ShipmentOrder).options(
        selectinload(ShipmentOrder.spare_part_lots),
        selectinload(ShipmentOrder.moto_units),
    )
    if filters:
        stmt = stmt.where(*filters)
    stmt = stmt.order_by(ShipmentOrder.cycle.desc().nullslast(), ShipmentOrder.pi_number.asc())
    stmt = stmt.offset(skip).limit(page_size)

    orders = (await db.execute(stmt)).scalars().all()

    # Recalcular status en tiempo real — el valor guardado puede estar desactualizado
    # si las fechas ETD/ETA ya pasaron desde la última importación.
    stale = []
    for o in orders:
        fresh = compute_status(o.etr_raw, o.etl_raw, o.etd, o.eta)
        if fresh != o.computed_status:
            o.computed_status = fresh
            stale.append(o)
    if stale:
        await db.commit()

    return ShipmentOrderListResponse(
        items=[ShipmentOrderRead.model_validate(o) for o in orders],
        total=total,
        page=page,
        page_size=page_size,
    )


# ---------------------------------------------------------------------------
# Detalle de un shipment order
# ---------------------------------------------------------------------------

@router.get("/shipment-orders/{order_id}", response_model=ShipmentOrderRead)
async def get_shipment_order(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_imports_editor(current_user)

    stmt = (
        select(ShipmentOrder)
        .where(ShipmentOrder.id == order_id)
        .options(
            selectinload(ShipmentOrder.moto_units),
            selectinload(ShipmentOrder.spare_part_lots),
        )
    )
    order = (await db.execute(stmt)).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail={"detail": "Pedido no encontrado", "code": "ORDER_NOT_FOUND"})

    return ShipmentOrderRead.model_validate(order)


# ---------------------------------------------------------------------------
# Crear un shipment order individual
# ---------------------------------------------------------------------------
# Crear pedido de repuestos desde Excel inicial
# ---------------------------------------------------------------------------

@router.post("/new-order-sp", status_code=status.HTTP_200_OK)
async def new_order_sp_from_excel(
    reference: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_imports_editor(current_user)
    if not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=422, detail={"detail": "Solo se aceptan archivos .xlsx", "code": "INVALID_FILE_TYPE"})
    file_bytes = await file.read()
    result = await imports_service.create_sp_order_from_excel(db, reference, file_bytes, current_user)
    await db.commit()
    return result


# ---------------------------------------------------------------------------
# Crear pedido de motos desde Excel inicial
# ---------------------------------------------------------------------------

@router.post("/new-order-motos", status_code=status.HTTP_200_OK)
async def new_order_motos_from_excel(
    cycle: Optional[int] = None,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_imports_editor(current_user)
    if not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=422, detail={"detail": "Solo se aceptan archivos .xlsx", "code": "INVALID_FILE_TYPE"})
    file_bytes = await file.read()
    result = await imports_service.create_moto_order_from_excel(db, cycle, file_bytes, current_user)
    await db.commit()
    return result


# ---------------------------------------------------------------------------

@router.post("/shipment-orders", response_model=ShipmentOrderRead, status_code=status.HTTP_201_CREATED)
async def create_shipment_order(
    payload: ShipmentOrderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_imports_editor(current_user)

    existing = (await db.execute(
        select(ShipmentOrder).where(
            ShipmentOrder.pi_number == payload.pi_number,
            ShipmentOrder.model == payload.model,
        )
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=409,
            detail={"detail": f"Ya existe un pedido con PI {payload.pi_number} y modelo {payload.model}", "code": "DUPLICATE"}
        )

    from app.services.imports_service import parse_excel_date, compute_status, detect_is_spare_part, compute_parent_pi

    etr_dt, etr_raw = parse_excel_date(payload.etr_raw)
    etl_dt, etl_raw = parse_excel_date(payload.etl_raw)
    etd_dt, etd_raw = parse_excel_date(payload.etd_raw)
    eta_dt, eta_raw = parse_excel_date(payload.eta_raw)

    order = ShipmentOrder(
        cycle=payload.cycle,
        pi_number=payload.pi_number,
        invoice_number=payload.invoice_number,
        model=payload.model,
        model_year=payload.model_year,
        qty=payload.qty,
        qty_numeric=int(payload.qty) if payload.qty and payload.qty.isdigit() else None,
        containers=payload.containers,
        departure_port=payload.departure_port,
        bl_container=payload.bl_container,
        vessel=payload.vessel,
        etr=etr_dt, etr_raw=etr_raw or payload.etr_raw,
        etl=etl_dt, etl_raw=etl_raw or payload.etl_raw,
        etd=etd_dt, etd_raw=etd_raw or payload.etd_raw,
        eta=eta_dt, eta_raw=eta_raw or payload.eta_raw,
        digital_docs_status=payload.digital_docs_status or "PENDING",
        original_docs_status=payload.original_docs_status or "PENDING",
        remarks=payload.remarks,
        is_spare_part=detect_is_spare_part(payload.qty, payload.pi_number),
        parent_pi_number=compute_parent_pi(payload.pi_number),
        computed_status=compute_status(etr_raw, etl_raw, etd_dt, eta_dt),
    )
    db.add(order)
    await db.commit()

    stmt = (
        select(ShipmentOrder)
        .where(ShipmentOrder.id == order.id)
        .options(
            selectinload(ShipmentOrder.spare_part_lots),
            selectinload(ShipmentOrder.moto_units),
        )
    )
    order = (await db.execute(stmt)).scalar_one()
    return ShipmentOrderRead.model_validate(order)


# ---------------------------------------------------------------------------
# Actualizar un shipment order
# ---------------------------------------------------------------------------

@router.patch("/shipment-orders/{order_id}", response_model=ShipmentOrderRead)
async def update_shipment_order(
    order_id: uuid.UUID,
    payload: ShipmentOrderUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_imports_editor(current_user)

    order = await db.get(ShipmentOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail={"detail": "Pedido no encontrado", "code": "ORDER_NOT_FOUND"})

    from app.services.imports_service import parse_excel_date, compute_status

    # Campos escalares simples
    simple_fields = {"cycle", "pi_number", "invoice_number", "model", "model_year", "qty", "containers",
                     "departure_port", "bl_container", "vessel", "order_date",
                     "digital_docs_status", "original_docs_status", "remarks", "computed_status"}
    update_data = payload.model_dump(exclude_none=True)
    for field in simple_fields:
        if field in update_data:
            setattr(order, field, update_data[field])

    # Fechas: parsear raw strings y actualizar tanto el campo datetime como el raw
    for prefix in ("etr", "etl", "etd", "eta"):
        raw_key = f"{prefix}_raw"
        if raw_key in update_data:
            dt, raw = parse_excel_date(update_data[raw_key])
            setattr(order, prefix, dt)
            setattr(order, raw_key, raw or update_data[raw_key])

    # Recomputar estado basado en fechas actuales del order
    order.computed_status = compute_status(order.etr_raw, order.etl_raw, order.etd, order.eta)
    order.updated_at = datetime.utcnow()

    await db.commit()

    # Recargar con relaciones para evitar MissingGreenlet en serialización
    stmt = (
        select(ShipmentOrder)
        .where(ShipmentOrder.id == order.id)
        .options(
            selectinload(ShipmentOrder.spare_part_lots),
            selectinload(ShipmentOrder.moto_units),
        )
    )
    order = (await db.execute(stmt)).scalar_one()
    return ShipmentOrderRead.model_validate(order)


# ---------------------------------------------------------------------------
# Eliminar un shipment order
# ---------------------------------------------------------------------------

@router.delete("/shipment-orders/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shipment_order(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_superadmin(current_user)

    order = await db.get(ShipmentOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail={"detail": "Pedido no encontrado", "code": "ORDER_NOT_FOUND"})

    await db.delete(order)


# ---------------------------------------------------------------------------
# Timeline de un pedido
# ---------------------------------------------------------------------------

@router.get("/shipment-orders/{order_id}/timeline")
async def get_order_timeline(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_imports_editor(current_user)

    order = await db.get(ShipmentOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail={"detail": "Pedido no encontrado", "code": "ORDER_NOT_FOUND"})

    now = datetime.utcnow()

    def stage_status(dt, raw):
        if dt and dt < now:
            return "reached"
        if dt and dt >= now:
            return "upcoming"
        return "pending"

    return [
        {"stage": "ETR", "value": order.etr, "raw": order.etr_raw, "status": stage_status(order.etr, order.etr_raw)},
        {"stage": "ETL", "value": order.etl, "raw": order.etl_raw, "status": stage_status(order.etl, order.etl_raw)},
        {"stage": "ETD", "value": order.etd, "raw": order.etd_raw, "status": stage_status(order.etd, order.etd_raw)},
        {"stage": "ETA", "value": order.eta, "raw": order.eta_raw, "status": stage_status(order.eta, order.eta_raw)},
    ]


# ---------------------------------------------------------------------------
# VINs de un pedido de motos
# ---------------------------------------------------------------------------

@router.get("/shipment-orders/{order_id}/moto-units", response_model=list[MotoUnitRead])
async def list_moto_units(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_imports_editor(current_user)

    order = await db.get(ShipmentOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail={"detail": "Pedido no encontrado", "code": "ORDER_NOT_FOUND"})

    stmt = select(ShipmentMotoUnit).where(ShipmentMotoUnit.shipment_order_id == order_id).order_by(ShipmentMotoUnit.item_no)
    units = (await db.execute(stmt)).scalars().all()
    return [MotoUnitRead.model_validate(u) for u in units]


# ---------------------------------------------------------------------------
# Adjuntos de un pedido
# ---------------------------------------------------------------------------

ALLOWED_ATTACHMENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "image/jpeg",
    "image/png",
    "application/octet-stream",
}

FILE_TYPE_OPTIONS = {"PACKING_LIST", "BL", "COMMERCIAL_INVOICE", "CERT_ORIGIN", "OTHER"}


@router.get("/shipment-orders/{order_id}/attachments", response_model=list[ImportAttachmentRead])
async def list_attachments(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_imports_editor(current_user)

    order = await db.get(ShipmentOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail={"detail": "Pedido no encontrado", "code": "ORDER_NOT_FOUND"})

    stmt = (
        select(ImportAttachment)
        .where(ImportAttachment.shipment_order_id == order_id)
        .order_by(ImportAttachment.uploaded_at.desc())
    )
    attachments = (await db.execute(stmt)).scalars().all()

    result = []
    for att in attachments:
        read = ImportAttachmentRead.model_validate(att)
        try:
            read.presigned_url = storage_service.get_presigned_url(
                storage_service.IMPORTS_BUCKET, att.minio_object_name
            )
        except Exception:
            read.presigned_url = None
        result.append(read)

    return result


@router.post("/shipment-orders/{order_id}/attachments", response_model=ImportAttachmentRead, status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    order_id: uuid.UUID,
    file: UploadFile = File(...),
    file_type: str = "OTHER",
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_imports_editor(current_user)

    if file_type.upper() not in FILE_TYPE_OPTIONS:
        raise HTTPException(status_code=422, detail=f"file_type debe ser uno de: {FILE_TYPE_OPTIONS}")

    order = await db.get(ShipmentOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail={"detail": "Pedido no encontrado", "code": "ORDER_NOT_FOUND"})

    file_bytes = await file.read()
    content_type = file.content_type or mimetypes.guess_type(file.filename)[0] or "application/octet-stream"

    object_name = f"orders/{order_id}/{file_type.lower()}/{uuid.uuid4()}_{file.filename}"
    await storage_service.upload_bytes(
        storage_service.IMPORTS_BUCKET,
        object_name,
        file_bytes,
        content_type=content_type,
    )

    attachment = ImportAttachment(
        shipment_order_id=order_id,
        uploaded_by=current_user.id,
        file_name=file.filename,
        file_type=file_type.upper(),
        minio_object_name=object_name,
        content_type=content_type,
    )
    db.add(attachment)
    await db.commit()
    await db.refresh(attachment)

    read = ImportAttachmentRead.model_validate(attachment)
    try:
        read.presigned_url = storage_service.get_presigned_url(
            storage_service.IMPORTS_BUCKET, object_name
        )
    except Exception:
        read.presigned_url = None

    return read


@router.delete("/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attachment(
    attachment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_superadmin(current_user)

    att = await db.get(ImportAttachment, attachment_id)
    if not att:
        raise HTTPException(status_code=404, detail={"detail": "Adjunto no encontrado", "code": "ATTACHMENT_NOT_FOUND"})

    try:
        storage_service.minio_client.remove_object(storage_service.IMPORTS_BUCKET, att.minio_object_name)
    except Exception:
        pass  # Si ya no existe en MinIO, igual eliminamos el registro

    await db.delete(att)
    await db.commit()


# ---------------------------------------------------------------------------
# Listado de spare part lots (con conteos calculados)
# ---------------------------------------------------------------------------

@router.get("/spare-part-lots", response_model=list[SparePartLotRead])
async def list_spare_part_lots(
    shipment_order_id: Optional[uuid.UUID] = None,
    detail_loaded: Optional[bool] = None,
    has_bl: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_imports_editor(current_user)

    stmt = (
        select(SparePartLot)
        .options(selectinload(SparePartLot.items))
    )
    if shipment_order_id:
        stmt = stmt.where(SparePartLot.shipment_order_id == shipment_order_id)
    if detail_loaded is not None:
        stmt = stmt.where(SparePartLot.detail_loaded == detail_loaded)
    if has_bl is not None:
        stmt = stmt.join(ShipmentOrder, SparePartLot.shipment_order_id == ShipmentOrder.id)
        if has_bl:
            stmt = stmt.where(
                ShipmentOrder.bl_container.isnot(None),
                ShipmentOrder.bl_container != "",
                ShipmentOrder.bl_container != "PENDING",
                ShipmentOrder.bl_container != "TBD",
            )
        else:
            stmt = stmt.where(
                (ShipmentOrder.bl_container.is_(None)) |
                (ShipmentOrder.bl_container == "") |
                (ShipmentOrder.bl_container == "PENDING") |
                (ShipmentOrder.bl_container == "TBD")
            )
    stmt = stmt.order_by(SparePartLot.created_at.desc())

    lots = (await db.execute(stmt)).scalars().all()

    result = []
    for lot in lots:
        read = SparePartLotRead.model_validate(lot)
        read.items_count = len(lot.items)
        if lot.items:
            total_ordered = sum(i.qty_ordered for i in lot.items)
            total_received = sum(i.qty_received for i in lot.items)
            read.pct_received = round((total_received / total_ordered * 100) if total_ordered > 0 else 0, 1)
        result.append(read)

    return result


@router.get("/spare-part-lots/{lot_id}/items", response_model=list[SparePartItemRead])
async def list_spare_part_items(
    lot_id: uuid.UUID,
    search: Optional[str] = None,
    item_status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_imports_editor(current_user)

    lot = await db.get(SparePartLot, lot_id)
    if not lot:
        raise HTTPException(status_code=404, detail={"detail": "Lote no encontrado", "code": "LOT_NOT_FOUND"})

    stmt = select(SparePartItem).where(SparePartItem.lot_id == lot_id)
    if search:
        stmt = stmt.where(
            SparePartItem.part_number.ilike(f"%{search}%") |
            SparePartItem.description.ilike(f"%{search}%")
        )
    if item_status:
        stmt = stmt.where(SparePartItem.status == item_status)
    stmt = stmt.order_by(SparePartItem.part_number)

    items = (await db.execute(stmt)).scalars().all()
    return [SparePartItemRead.model_validate(i) for i in items]


def _compute_reconciliation_result(qty_ordered, qty_in_packing) -> str:
    if qty_ordered is None:
        return "EXTRA"
    qty_pl = qty_in_packing or 0
    if qty_pl == 0:
        return "MISSING"
    if qty_pl >= qty_ordered:
        return "COMPLETE"
    return "PARTIAL"


@router.post("/spare-part-items/{item_id}/cancel-pending")
async def cancel_pending_backorder(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    if current_user.role not in ("superadmin", "administrativo"):
        raise HTTPException(status_code=403, detail="Solo superadmin o administrador pueden cancelar pendientes")

    item = await db.get(SparePartItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail={"detail": "Ítem no encontrado", "code": "ITEM_NOT_FOUND"})

    if (item.qty_pending or 0) == 0:
        raise HTTPException(status_code=400, detail={"detail": "El ítem no tiene unidades pendientes", "code": "NO_PENDING"})

    now = datetime.utcnow()
    open_bos = (await db.execute(
        select(Backorder).where(Backorder.spare_part_item_id == item.id, Backorder.resolved == False)
    )).scalars().all()

    for bo in open_bos:
        bo.resolved = True
        bo.resolved_at = now
        history = list(bo.history or [])
        history.append({"date": now.isoformat(), "event": "CANCELLED", "actor": current_user.role})
        bo.history = history
        bo.updated_at = now

    new_status = "CANCELLED" if item.status == "BACKORDER" else item.status
    item.qty_pending = 0
    item.status = new_status
    item.updated_at = now

    await db.commit()
    return {"cancelled": len(open_bos), "item_status": new_status}


@router.patch("/spare-part-items/{item_id}", response_model=SparePartItemRead)
async def update_spare_part_item(
    item_id: uuid.UUID,
    payload: SparePartItemUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_imports_editor(current_user)

    item = await db.get(SparePartItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail={"detail": "Ítem no encontrado", "code": "ITEM_NOT_FOUND"})

    update_data = payload.model_dump(exclude_none=True)
    for field, value in update_data.items():
        setattr(item, field, value)

    if "qty_received" in update_data or "qty_ordered" in update_data:
        item.qty_pending = max(0, item.qty_ordered - item.qty_received)

    # Propagar cambios a ReconciliationResult vinculado
    propagate_fields = {"qty_ordered", "part_number"}
    if propagate_fields & set(update_data.keys()):
        rr = (await db.execute(
            select(ReconciliationResult).where(ReconciliationResult.spare_part_item_id == item.id)
        )).scalar_one_or_none()
        if rr:
            if "qty_ordered" in update_data:
                rr.qty_ordered = item.qty_ordered
                rr.result = _compute_reconciliation_result(rr.qty_ordered, rr.qty_in_packing)
            if "part_number" in update_data:
                rr.part_number = item.part_number

    item.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(item)
    return SparePartItemRead.model_validate(item)


@router.patch("/reconciliation-results/{result_id}")
async def update_reconciliation_result(
    result_id: uuid.UUID,
    payload: ReconciliationResultUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_imports_editor(current_user)

    rr = await db.get(ReconciliationResult, result_id)
    if not rr:
        raise HTTPException(status_code=404, detail={"detail": "Resultado no encontrado", "code": "NOT_FOUND"})

    update_data = payload.model_dump(exclude_none=True)

    if "qty_in_packing" in update_data:
        rr.qty_in_packing = update_data["qty_in_packing"]
        rr.result = _compute_reconciliation_result(rr.qty_ordered, rr.qty_in_packing)
        if rr.spare_part_item_id:
            item = await db.get(SparePartItem, rr.spare_part_item_id)
            if item:
                item.qty_received = rr.qty_in_packing
                item.qty_pending = max(0, item.qty_ordered - item.qty_received)
                item.updated_at = datetime.utcnow()

    if "qty_physical" in update_data:
        lot = await db.get(SparePartLot, rr.lot_id)
        if not lot or not lot.packing_list_received:
            raise HTTPException(
                status_code=400,
                detail={"detail": "El inventario físico solo puede registrarse después de confirmar el cruce", "code": "RECONCILIATION_NOT_CONFIRMED"},
            )
        rr.qty_physical = update_data["qty_physical"]
        await imports_service.apply_physical_inspection(db, rr, update_data["qty_physical"])

    # Campos que viven en SparePartItem pero se muestran en reconciliación
    item_fields = {"part_number", "description_es", "model_applicable"}
    if item_fields & set(update_data.keys()):
        if rr.spare_part_item_id:
            item = await db.get(SparePartItem, rr.spare_part_item_id)
            if item:
                for field in item_fields & set(update_data.keys()):
                    setattr(item, field, update_data[field])
                item.updated_at = datetime.utcnow()
        if "part_number" in update_data:
            rr.part_number = update_data["part_number"]

    await db.commit()
    await db.refresh(rr)
    return {
        "id": str(rr.id),
        "result": rr.result,
        "qty_in_packing": rr.qty_in_packing,
        "qty_physical": rr.qty_physical,
        "part_number": rr.part_number,
    }


# ---------------------------------------------------------------------------
# Carga de detalle de orden de compra (PI Detail) → crea SparePartItems
# ---------------------------------------------------------------------------

@router.post("/spare-part-lots/{lot_id}/order-detail", status_code=status.HTTP_200_OK)
async def upload_lot_order_detail(
    lot_id: uuid.UUID,
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_imports_editor(current_user)

    if not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=422, detail={"detail": "Solo se aceptan archivos .xlsx", "code": "INVALID_FILE_TYPE"})

    lot = await db.get(SparePartLot, lot_id)
    if not lot:
        raise HTTPException(status_code=404, detail={"detail": "Lote no encontrado", "code": "LOT_NOT_FOUND"})

    file_bytes = await file.read()
    result = await imports_service.load_order_detail_excel(db, lot, file_bytes, current_user)
    await db.commit()

    # Detectar posibles cambios de código en segundo plano sin bloquear la respuesta
    if background_tasks is not None:
        from app.api.v1.parts_manual import run_detection_bg
        background_tasks.add_task(run_detection_bg)

    return result


# ---------------------------------------------------------------------------
# Reconciliación de packing list contra lote SP
# ---------------------------------------------------------------------------

@router.post("/spare-part-lots/{lot_id}/packing-list", status_code=status.HTTP_200_OK)
async def upload_lot_packing_list(
    lot_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_imports_editor(current_user)

    if not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="Solo se aceptan archivos .xlsx")

    lot = await db.get(SparePartLot, lot_id)
    if not lot:
        raise HTTPException(status_code=404, detail={"detail": "Lote no encontrado", "code": "LOT_NOT_FOUND"})

    file_bytes = await file.read()
    object_name = f"lots/{lot_id}/packing-lists/{uuid.uuid4()}_{file.filename}"

    await storage_service.upload_bytes(
        storage_service.IMPORTS_BUCKET,
        object_name,
        file_bytes,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    result = await imports_service.reconcile_lot_packing_list(
        db, lot, file_bytes, file.filename, object_name, current_user
    )
    await db.commit()
    return result


@router.get("/spare-part-lots/{lot_id}/reconciliation", response_model=list[ReconciliationResultRead])
async def get_reconciliation_results(
    lot_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_imports_editor(current_user)

    lot = await db.get(SparePartLot, lot_id)
    if not lot:
        raise HTTPException(status_code=404, detail={"detail": "Lote no encontrado", "code": "LOT_NOT_FOUND"})

    stmt = (
        select(ReconciliationResult)
        .where(ReconciliationResult.lot_id == lot_id)
        .order_by(ReconciliationResult.result, ReconciliationResult.part_number)
    )
    results = (await db.execute(stmt)).scalars().all()

    # Enriquecer con descripción y modelo del SparePartItem
    item_ids = [r.spare_part_item_id for r in results if r.spare_part_item_id]
    items_map = {}
    if item_ids:
        sp_items = (await db.execute(
            select(SparePartItem).where(SparePartItem.id.in_(item_ids))
        )).scalars().all()
        items_map = {i.id: i for i in sp_items}

    enriched = []
    for r in results:
        sp = items_map.get(r.spare_part_item_id)
        data = {
            "id": r.id, "lot_id": r.lot_id, "packing_list_id": r.packing_list_id,
            "spare_part_item_id": r.spare_part_item_id, "part_number": r.part_number,
            "description_es": sp.description_es if sp else None,
            "model_applicable": sp.model_applicable if sp else None,
            "qty_ordered": r.qty_ordered, "qty_in_packing": r.qty_in_packing,
            "qty_physical": r.qty_physical,
            "result": r.result, "confirmed_by": r.confirmed_by,
            "confirmed_at": r.confirmed_at, "created_at": r.created_at,
        }
        enriched.append(ReconciliationResultRead.model_validate(data, from_attributes=False))
    return enriched


@router.post("/spare-part-lots/{lot_id}/reconciliation/confirm", status_code=status.HTTP_200_OK)
async def confirm_lot_reconciliation(
    lot_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_imports_editor(current_user)

    lot = await db.get(SparePartLot, lot_id)
    if not lot:
        raise HTTPException(status_code=404, detail={"detail": "Lote no encontrado", "code": "LOT_NOT_FOUND"})

    result = await imports_service.confirm_reconciliation(db, lot, current_user)
    return result


# ---------------------------------------------------------------------------
# Backorders
# ---------------------------------------------------------------------------

@router.get("/backorders", response_model=list[BackorderRead])
async def list_backorders(
    resolved: Optional[bool] = None,
    part_number: Optional[str] = None,
    origin_pi: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_imports_editor(current_user)
    items = await imports_service.list_backorders(db, resolved=resolved, part_number=part_number, origin_pi=origin_pi)
    return [BackorderRead.model_validate(i, from_attributes=False) for i in items]


@router.patch("/backorders/{backorder_id}", response_model=BackorderRead)
async def update_backorder(
    backorder_id: uuid.UUID,
    payload: BackorderUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_imports_editor(current_user)

    bo = await db.get(Backorder, backorder_id)
    if not bo:
        raise HTTPException(status_code=404, detail={"detail": "Backorder no encontrado", "code": "BO_NOT_FOUND"})

    update_data = payload.model_dump(exclude_none=True)
    now = datetime.utcnow()
    history = list(bo.history or [])

    if "expected_in_pi" in update_data:
        history.append({"date": now.isoformat(), "event": "SET_EXPECTED_PI", "expected_in_pi": update_data["expected_in_pi"]})
        bo.expected_in_pi = update_data["expected_in_pi"]

    if update_data.get("resolved") is True and not bo.resolved:
        bo.resolved = True
        bo.resolved_at = now
        history.append({"date": now.isoformat(), "event": "RESOLVED_MANUAL", "actor": current_user.role})
        # Actualizar SparePartItem vinculado
        item = await db.get(SparePartItem, bo.spare_part_item_id)
        if item:
            item.qty_received = item.qty_ordered
            item.qty_pending = 0
            item.status = "RECEIVED"
            item.updated_at = now

    if "qty_pending" in update_data:
        history.append({"date": now.isoformat(), "event": "QTY_UPDATE", "qty_pending": update_data["qty_pending"]})
        bo.qty_pending = update_data["qty_pending"]

    bo.history = history
    bo.updated_at = now
    await db.commit()
    await db.refresh(bo)
    return BackorderRead.model_validate(bo)


@router.post("/backorders/bulk-expected-pi")
async def bulk_update_expected_pi(
    payload: BackorderBulkUpdatePI,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_imports_editor(current_user)
    now = datetime.utcnow()
    updated = 0
    for bo_id in payload.ids:
        bo = await db.get(Backorder, bo_id)
        if not bo or bo.resolved:
            continue
        bo.expected_in_pi = payload.expected_in_pi
        history = list(bo.history or [])
        history.append({"date": now.isoformat(), "event": "SET_EXPECTED_PI", "expected_in_pi": payload.expected_in_pi})
        bo.history = history
        bo.updated_at = now
        updated += 1
    await db.commit()
    return {"updated": updated}


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@router.get("/dashboard")
async def get_imports_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
    is_spare_part: Optional[bool] = Query(None),
):
    _require_imports_editor(current_user)

    from sqlalchemy import case, and_
    from datetime import timedelta
    from app.schemas.imports import ImportDashboardSummary

    now = datetime.utcnow()
    in_60_days = now + timedelta(days=60)

    def _sp_filter():
        if is_spare_part is None:
            return []
        return [ShipmentOrder.is_spare_part == is_spare_part]

    # Conteos por estado
    status_rows = (await db.execute(
        select(ShipmentOrder.computed_status, func.count().label("cnt"))
        .where(*_sp_filter())
        .group_by(ShipmentOrder.computed_status)
    )).all()
    status_map = {r.computed_status: r.cnt for r in status_rows}

    # Tipo moto vs SP
    type_rows = (await db.execute(
        select(ShipmentOrder.is_spare_part, func.count().label("cnt"))
        .where(*_sp_filter())
        .group_by(ShipmentOrder.is_spare_part)
    )).all()
    moto_count = next((r.cnt for r in type_rows if not r.is_spare_part), 0)
    sp_count   = next((r.cnt for r in type_rows if r.is_spare_part), 0)

    # Backorders activos (solo aplica a repuestos)
    from app.models.imports import Backorder, SparePartLot
    if is_spare_part is False:
        bo_count = 0
        bo_units = 0
        total_value = 0.0
    else:
        bo_count = (await db.execute(
            select(func.count()).select_from(Backorder).where(Backorder.resolved == False)
        )).scalar_one()
        bo_units = (await db.execute(
            select(func.coalesce(func.sum(Backorder.qty_pending), 0))
            .where(Backorder.resolved == False)
        )).scalar_one()
        from sqlalchemy import Numeric as SaNumeric
        total_value = (await db.execute(
            select(func.coalesce(func.sum(SparePartLot.total_declared_value), 0))
        )).scalar_one()

    # Por ciclo
    cycle_rows = (await db.execute(
        select(ShipmentOrder.cycle, func.count().label("cnt"))
        .where(ShipmentOrder.cycle.isnot(None), *_sp_filter())
        .group_by(ShipmentOrder.cycle)
        .order_by(ShipmentOrder.cycle.desc())
        .limit(8)
    )).all()
    by_cycle = [{"cycle": r.cycle, "count": r.cnt} for r in cycle_rows]

    # Próximas ETAs (60 días)
    eta_rows = (await db.execute(
        select(ShipmentOrder)
        .where(
            ShipmentOrder.eta.isnot(None),
            ShipmentOrder.eta >= now,
            ShipmentOrder.eta <= in_60_days,
            ShipmentOrder.computed_status.notin_(["completado"]),
            *_sp_filter(),
        )
        .order_by(ShipmentOrder.eta.asc())
        .limit(10)
    )).scalars().all()

    upcoming = [
        {
            "id": str(o.id),
            "pi_number": o.pi_number,
            "model": o.model,
            "eta": o.eta.isoformat() if o.eta else None,
            "eta_raw": o.eta_raw,
            "qty": o.qty,
            "is_spare_part": o.is_spare_part,
            "computed_status": o.computed_status,
            "cycle": o.cycle,
        }
        for o in eta_rows
    ]

    return ImportDashboardSummary(
        en_preparacion=status_map.get("en_preparacion", 0),
        listo_fabrica=status_map.get("listo_fabrica", 0),
        en_transito=status_map.get("en_transito", 0),
        en_destino=status_map.get("en_destino", 0),
        completado=status_map.get("completado", 0),
        backorder=status_map.get("backorder", 0),
        total_active=sum(v for k, v in status_map.items() if k != "completado"),
        moto_orders=moto_count,
        sp_orders=sp_count,
        pending_docs_digital=0,
        pending_docs_original=0,
        active_backorders=bo_count,
        total_backorder_units=int(bo_units),
        total_declared_value_usd=float(total_value),
        by_cycle=by_cycle,
        upcoming_etas=upcoming,
    )


# ---------------------------------------------------------------------------
# Listado global de moto units (con filtros y paginación)
# ---------------------------------------------------------------------------

@router.get("/moto-units", status_code=200)
async def list_all_moto_units(
    page: int = 1,
    page_size: int = 50,
    pi_number: Optional[str] = None,
    model: Optional[str] = None,
    vin: Optional[str] = None,
    engine: Optional[str] = None,
    certificado_generado: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_imports_editor(current_user)

    page_size = min(page_size, 200)
    skip = (page - 1) * page_size

    # Base join: ShipmentMotoUnit ← ShipmentOrder, only motos (not spare parts)
    # base_filters NO incluye certificado_generado para que los KPIs globales sean correctos
    base_filters = [ShipmentOrder.is_spare_part == False]

    if pi_number:
        base_filters.append(ShipmentOrder.pi_number.ilike(f"%{pi_number}%"))
    if model:
        base_filters.append(ShipmentOrder.model.ilike(f"%{model}%"))
    if vin:
        base_filters.append(ShipmentMotoUnit.vin_number.ilike(f"%{vin}%"))
    if engine:
        base_filters.append(ShipmentMotoUnit.engine_number.ilike(f"%{engine}%"))

    # Filtros completos (con certificado si aplica) para la paginación
    filters = list(base_filters)
    if certificado_generado is not None:
        filters.append(ShipmentMotoUnit.certificado_generado == certificado_generado)

    base_stmt = (
        select(ShipmentMotoUnit)
        .join(ShipmentOrder, ShipmentMotoUnit.shipment_order_id == ShipmentOrder.id)
        .where(*filters)
    )

    # Total paginado (respeta el filtro de certificado si está activo)
    count_stmt = select(func.count()).select_from(
        select(ShipmentMotoUnit)
        .join(ShipmentOrder, ShipmentMotoUnit.shipment_order_id == ShipmentOrder.id)
        .where(*filters)
        .subquery()
    )
    total = (await db.execute(count_stmt)).scalar_one()

    # KPIs — respetan los filtros activos (pi_number, model, vin, engine)
    # pero NO el filtro de certificado_generado para mostrar el universo completo del filtro
    total_empadronados = (await db.execute(
        select(func.count()).select_from(
            select(ShipmentMotoUnit)
            .join(ShipmentOrder, ShipmentMotoUnit.shipment_order_id == ShipmentOrder.id)
            .where(*base_filters, ShipmentMotoUnit.certificado_generado == True)
            .subquery()
        )
    )).scalar_one()

    total_global = (await db.execute(
        select(func.count()).select_from(
            select(ShipmentMotoUnit)
            .join(ShipmentOrder, ShipmentMotoUnit.shipment_order_id == ShipmentOrder.id)
            .where(*base_filters)
            .subquery()
        )
    )).scalar_one()

    total_pendientes = total_global - total_empadronados

    # Paginated items with the related order eagerly loaded
    stmt = (
        base_stmt
        .options(selectinload(ShipmentMotoUnit.shipment_order))
        .order_by(ShipmentMotoUnit.created_at.desc())
        .offset(skip)
        .limit(page_size)
    )
    units = (await db.execute(stmt)).scalars().all()

    items = []
    for u in units:
        o = u.shipment_order
        items.append({
            "id": str(u.id),
            "shipment_order_id": str(u.shipment_order_id),
            "item_no": u.item_no,
            "vin_number": u.vin_number,
            "engine_number": u.engine_number,
            "color": u.color,
            "container_no": u.container_no,
            "seal_no": u.seal_no,
            "source_pi": u.source_pi,
            "no_acep": u.no_acep,
            "f_acep": str(u.f_acep) if u.f_acep else None,
            "no_lev": u.no_lev,
            "f_lev": str(u.f_lev) if u.f_lev else None,
            "certificado_generado": u.certificado_generado,
            "certificado_fecha": u.certificado_fecha.isoformat() if u.certificado_fecha else None,
            "empadronamiento_fisico_enviado": u.empadronamiento_fisico_enviado,
            "empadronamiento_fisico_fecha": u.empadronamiento_fisico_fecha.isoformat() if u.empadronamiento_fisico_fecha else None,
            "empadronamiento_fisico_distribuidor_id": str(u.empadronamiento_fisico_distribuidor_id) if u.empadronamiento_fisico_distribuidor_id else None,
            "empadronamiento_fisico_distribuidor_nombre": u.empadronamiento_fisico_distribuidor_nombre,
            "dim_pdf_object_name": u.dim_pdf_object_name,
            "created_at": u.created_at.isoformat(),
            # Fields from the related order
            "pi_number": o.pi_number if o else None,
            "model": u.model or (o.model if o else None),
            # unit.model_year tiene prioridad sobre el de la orden
            "model_year": u.model_year or (o.model_year if o else None),
        })

    return {
        "items": items,
        "total": total,
        "total_global": total_global,
        "total_empadronados": total_empadronados,
        "total_pendientes": total_pendientes,
        "page": page,
        "page_size": page_size,
    }


# ---------------------------------------------------------------------------
# PATCH /moto-units/{unit_id} — editar campos de una unidad
# ---------------------------------------------------------------------------

@router.patch("/moto-units/{unit_id}", status_code=200)
async def update_moto_unit(
    unit_id: uuid.UUID,
    payload: MotoUnitUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    if current_user.role not in ("superadmin", "administrativo"):
        raise HTTPException(status_code=403, detail="Sin permisos para editar unidades")
    unit = (await db.execute(select(ShipmentMotoUnit).where(ShipmentMotoUnit.id == unit_id))).scalar_one_or_none()
    if not unit:
        raise HTTPException(status_code=404, detail="Unidad no encontrada")
    update_data = payload.model_dump(exclude_unset=True)

    distribuidor_id = update_data.pop("empadronamiento_fisico_distribuidor_id", None)

    for field, value in update_data.items():
        setattr(unit, field, value)

    # Si se marca el envío físico, registrar fecha y distribuidor
    if update_data.get("empadronamiento_fisico_enviado") is True:
        if unit.empadronamiento_fisico_fecha is None:
            unit.empadronamiento_fisico_fecha = datetime.utcnow()
        if distribuidor_id is not None:
            tenant = (await db.execute(select(Tenant).where(Tenant.id == distribuidor_id))).scalar_one_or_none()
            if tenant is None:
                raise HTTPException(status_code=404, detail="Distribuidor no encontrado")
            unit.empadronamiento_fisico_distribuidor_id = distribuidor_id
            unit.empadronamiento_fisico_distribuidor_nombre = tenant.name

    # Si se desmarca el envío físico, limpiar distribuidor y fecha
    if update_data.get("empadronamiento_fisico_enviado") is False:
        unit.empadronamiento_fisico_fecha = None
        unit.empadronamiento_fisico_distribuidor_id = None
        unit.empadronamiento_fisico_distribuidor_nombre = None

    await db.commit()
    await db.refresh(unit)
    return {
        "id": str(unit.id),
        "model": unit.model,
        "vin_number": unit.vin_number,
        "engine_number": unit.engine_number,
        "color": unit.color,
        "model_year": unit.model_year,
        "empadronamiento_fisico_enviado": unit.empadronamiento_fisico_enviado,
        "empadronamiento_fisico_fecha": unit.empadronamiento_fisico_fecha.isoformat() if unit.empadronamiento_fisico_fecha else None,
        "empadronamiento_fisico_distribuidor_id": str(unit.empadronamiento_fisico_distribuidor_id) if unit.empadronamiento_fisico_distribuidor_id else None,
        "empadronamiento_fisico_distribuidor_nombre": unit.empadronamiento_fisico_distribuidor_nombre,
    }


# ---------------------------------------------------------------------------
# GET /distribuidores-venta — tenants con venta de motos activos
# ---------------------------------------------------------------------------

@router.get("/distribuidores-venta", status_code=200)
async def list_distribuidores_venta(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_imports_editor(current_user)
    stmt = (
        select(Tenant)
        .where(Tenant.has_sales == True, Tenant.estado_red == EstadoRed.activo)
        .order_by(Tenant.name.asc())
    )
    tenants = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": str(t.id),
            "name": t.name,
            "ciudad": t.ciudad,
            "departamento": t.departamento,
            "nit": t.nit,
        }
        for t in tenants
    ]


# ---------------------------------------------------------------------------
# Carga de DIM PDF → actualiza datos de aduana en moto units
# ---------------------------------------------------------------------------

@router.post("/moto-units/dim", status_code=200)
async def upload_dim_pdf(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    if current_user.role not in ("superadmin", "administrativo"):
        raise HTTPException(status_code=403, detail="Sin permisos para cargar DIM")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="Solo se aceptan archivos .pdf")

    file_bytes = await file.read()

    try:
        vehicles = dim_parser_service.parse_dim_pdf(file_bytes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Guardar el PDF en MinIO una sola vez; todas las unidades emparejadas referencian el mismo objeto
    dim_object_name = f"dim/{uuid.uuid4()}.pdf"
    try:
        await storage_service.upload_bytes(
            storage_service.IMPORTS_BUCKET,
            dim_object_name,
            file_bytes,
            content_type="application/pdf",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al guardar el PDF en almacenamiento: {e}")

    matched = 0
    unmatched = 0
    unmatched_vins: list[str] = []

    for v in vehicles:
        vin_raw = v["vin"]

        # Exact match first
        unit = (await db.execute(
            select(ShipmentMotoUnit).where(ShipmentMotoUnit.vin_number == vin_raw)
        )).scalar_one_or_none()

        # Fallback: strip/upper normalisation
        if unit is None:
            vin_norm = vin_raw.strip().upper()
            unit = (await db.execute(
                select(ShipmentMotoUnit).where(ShipmentMotoUnit.vin_number == vin_norm)
            )).scalar_one_or_none()

        if unit is None:
            unmatched += 1
            unmatched_vins.append(vin_raw)
            continue

        # Parse dates from YYYY-MM-DD strings returned by dim_parser_service
        from datetime import date as _date

        def _parse_date(s: str):
            try:
                return _date.fromisoformat(s)
            except Exception:
                return None

        unit.no_acep = v.get("no_acep")
        unit.f_acep = _parse_date(v.get("f_acep", ""))
        unit.no_lev = v.get("no_lev")
        unit.f_lev = _parse_date(v.get("f_lev", ""))
        unit.certificado_generado = True
        unit.certificado_fecha = datetime.utcnow()
        unit.dim_pdf_object_name = dim_object_name
        matched += 1

    await db.commit()

    return {
        "matched": matched,
        "unmatched": unmatched,
        "total_in_dim": len(vehicles),
        "vins_not_found": unmatched_vins,
    }


# ---------------------------------------------------------------------------
# URL pre-firmada para consultar la DIM PDF de una moto unit
# ---------------------------------------------------------------------------

@router.get("/moto-units/{unit_id}/dim-url")
async def get_dim_pdf_url(
    unit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    unit = await db.get(ShipmentMotoUnit, unit_id)
    if not unit:
        raise HTTPException(status_code=404, detail="Unidad no encontrada")

    if not unit.dim_pdf_object_name:
        raise HTTPException(status_code=404, detail="Esta unidad no tiene DIM cargada")

    pdf_bytes = await storage_service.get_bytes(
        storage_service.IMPORTS_BUCKET,
        unit.dim_pdf_object_name,
    )
    if not pdf_bytes:
        raise HTTPException(status_code=404, detail="Archivo DIM no encontrado en almacenamiento")

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="DIM_{unit.vin_number}.pdf"'},
    )


# ---------------------------------------------------------------------------
# Descarga de certificado individual de aduanas para una moto unit
# ---------------------------------------------------------------------------

@router.get("/moto-units/{unit_id}/certificado")
async def download_certificado(
    unit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    unit = await db.get(ShipmentMotoUnit, unit_id)
    if not unit:
        raise HTTPException(status_code=404, detail="Unidad no encontrada")

    # Load related order
    order = await db.get(ShipmentOrder, unit.shipment_order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Pedido asociado no encontrado")

    if not unit.certificado_generado:
        raise HTTPException(
            status_code=404,
            detail="Certificado no generado aún. Cargá primero la DIM.",
        )

    # Load all VehicleModel records for spec matching
    vehicle_models = (await db.execute(select(VehicleModel))).scalars().all()
    matched_vm = certificate_service.encontrar_specs_para_modelo(list(vehicle_models), order.model)

    # encontrar_specs_para_modelo returns a dict of specs, not a VehicleModel ORM object.
    # generate_certificado_bytes expects an ORM object or None; build a simple namespace.
    vm_obj = None
    if matched_vm and matched_vm.get("cilindrada") != "N/A":
        class _SpecsProxy:
            def __init__(self, d):
                self.cilindrada = d.get("cilindrada")
                self.potencia = d.get("potencia")
                self.peso = d.get("peso")
                self.vueltas_aire = d.get("vueltas_aire")
                self.posicion_cortina = d.get("posicion_cortina")
                self.sistemas_control = d.get("sistemas_control")
                self.fuel_system = d.get("fuel_system")
        vm_obj = _SpecsProxy(matched_vm)

    if not unit.model_year:
        raise HTTPException(
            status_code=422,
            detail="La moto no tiene año modelo registrado. Completá ese campo antes de generar el empadronamiento.",
        )

    pdf_bytes = certificate_service.generate_certificado_bytes(unit, order, vm_obj)

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="Certificado_{unit.vin_number}.pdf"'},
    )


# ---------------------------------------------------------------------------
# DELETE /moto-units/{unit_id}/certificado — anular empadronamiento
# ---------------------------------------------------------------------------

@router.delete("/moto-units/{unit_id}/certificado", status_code=200)
async def delete_certificado(
    unit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    if current_user.role not in ("superadmin", "administrativo"):
        raise HTTPException(status_code=403, detail="Sin permisos para anular el empadronamiento")
    unit = await db.get(ShipmentMotoUnit, unit_id)
    if not unit:
        raise HTTPException(status_code=404, detail="Unidad no encontrada")
    if not unit.certificado_generado:
        raise HTTPException(status_code=400, detail="La unidad no tiene empadronamiento generado")
    unit.certificado_generado = False
    unit.certificado_fecha = None
    await db.commit()
    return {"ok": True, "id": str(unit.id)}
