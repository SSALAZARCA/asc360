"""
Inventory Remisiones — outbound spare-part dispatch module.

Business rules:
- BORRADOR → DESPACHADO via /despachar (with pessimistic locking + re-validation)
- DESPACHADO → ANULADO via /anular (inserts counter-movements)
- Items can only be mutated while status == BORRADOR
- Availability is tracked via the VIEW spare_part_availability (immutable ledger)
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, text
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.api.deps import get_current_user, CurrentUser
from app.models.imports import (
    InventoryRemision,
    InventoryRemisionItem,
    InventoryRemisionMovement,
    SparePartLot,
    SparePartItem,
)
from app.schemas.remisiones import (
    RemisionCreate,
    RemisionRead,
    RemisionDetail,
    RemisionItemCreate,
    RemisionItemRead,
    RemisionItemUpdate,
    DispatchResponse,
    CancelRequest,
    AvailabilityItem,
    RemisionListResponse,
)

router = APIRouter(prefix="/remisiones", tags=["remisiones"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_superadmin(current_user: CurrentUser) -> CurrentUser:
    if not current_user.is_superadmin:
        raise HTTPException(status_code=403, detail="Solo superadmin puede realizar esta acción")
    return current_user


async def _get_remision_or_404(db: AsyncSession, remision_id: uuid.UUID) -> InventoryRemision:
    stmt = (
        select(InventoryRemision)
        .options(
            selectinload(InventoryRemision.items),
            selectinload(InventoryRemision.movements),
        )
        .where(InventoryRemision.id == remision_id)
    )
    result = await db.execute(stmt)
    remision = result.scalar_one_or_none()
    if remision is None:
        raise HTTPException(status_code=404, detail="Remisión no encontrada")
    return remision


async def _get_availability(db: AsyncSession, spare_part_item_id: uuid.UUID) -> Optional[int]:
    """Query the VIEW for the current available qty of a single item."""
    row = await db.execute(
        text("SELECT qty_available FROM spare_part_availability WHERE id = :id"),
        {"id": str(spare_part_item_id)},
    )
    record = row.fetchone()
    return record[0] if record else None


def _build_detail(remision: InventoryRemision) -> RemisionDetail:
    items = [RemisionItemRead.model_validate(i) for i in remision.items]
    movements = []
    from app.schemas.remisiones import RemisionMovementRead
    for m in remision.movements:
        movements.append(RemisionMovementRead.model_validate(m))
    return RemisionDetail(
        **RemisionRead.model_validate(remision).model_dump(),
        items=items,
        movements=movements,
    )


# ---------------------------------------------------------------------------
# POST / — create BORRADOR
# ---------------------------------------------------------------------------

@router.post("/", response_model=RemisionRead, status_code=status.HTTP_201_CREATED)
async def create_remision(
    payload: RemisionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_superadmin(current_user)

    # Validate reference_lot exists when provided
    if payload.reference_lot_id is not None:
        lot_check = await db.execute(
            select(SparePartLot.id).where(SparePartLot.id == payload.reference_lot_id)
        )
        if lot_check.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=422,
                detail=f"reference_lot_id {payload.reference_lot_id} does not exist",
            )

    remision = InventoryRemision(
        id=uuid.uuid4(),
        type=payload.type.value,
        status="BORRADOR",
        reference_lot_id=payload.reference_lot_id,
        notes=payload.notes,
        created_by=uuid.UUID(current_user.user_id),
    )
    db.add(remision)
    await db.commit()
    await db.refresh(remision)
    return RemisionRead.model_validate(remision)


# ---------------------------------------------------------------------------
# GET / — list with filters + pagination
# ---------------------------------------------------------------------------

@router.get("/", response_model=RemisionListResponse)
async def list_remisiones(
    type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    reference_lot_id: Optional[uuid.UUID] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_superadmin(current_user)

    filters = []
    if type:
        filters.append(InventoryRemision.type == type)
    if status:
        filters.append(InventoryRemision.status == status)
    if reference_lot_id:
        filters.append(InventoryRemision.reference_lot_id == reference_lot_id)
    if date_from:
        filters.append(InventoryRemision.created_at >= date_from)
    if date_to:
        filters.append(InventoryRemision.created_at <= date_to)

    count_stmt = select(func.count()).select_from(InventoryRemision)
    if filters:
        count_stmt = count_stmt.where(*filters)
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = select(InventoryRemision)
    if filters:
        stmt = stmt.where(*filters)
    stmt = stmt.order_by(InventoryRemision.created_at.desc()).offset(skip).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()

    return RemisionListResponse(
        items=[RemisionRead.model_validate(r) for r in rows],
        total=total,
        skip=skip,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# GET /availability — query VIEW spare_part_availability
# ---------------------------------------------------------------------------

@router.get("/availability", response_model=List[AvailabilityItem])
async def get_availability(
    lot_id: Optional[uuid.UUID] = Query(None),
    part_number: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_superadmin(current_user)

    sql = "SELECT id, part_number, lot_id, qty_available FROM spare_part_availability WHERE qty_available > 0"
    params: dict = {}

    if lot_id:
        sql += " AND lot_id = :lot_id"
        params["lot_id"] = str(lot_id)
    if part_number:
        sql += " AND part_number ILIKE :part_number"
        params["part_number"] = f"%{part_number.strip().upper().replace(' ', '')}%"

    sql += " ORDER BY part_number ASC"

    result = await db.execute(text(sql), params)
    rows = result.fetchall()

    return [
        AvailabilityItem(
            spare_part_item_id=row[0],
            part_number=row[1],
            lot_id=row[2],
            qty_available=row[3],
        )
        for row in rows
    ]


# ---------------------------------------------------------------------------
# GET /{id} — detail with items and movements
# ---------------------------------------------------------------------------

@router.get("/{remision_id}", response_model=RemisionDetail)
async def get_remision(
    remision_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_superadmin(current_user)
    remision = await _get_remision_or_404(db, remision_id)
    return _build_detail(remision)


# ---------------------------------------------------------------------------
# POST /{id}/items — add item (BORRADOR only)
# ---------------------------------------------------------------------------

@router.post("/{remision_id}/items", response_model=RemisionItemRead, status_code=status.HTTP_201_CREATED)
async def add_item(
    remision_id: uuid.UUID,
    payload: RemisionItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_superadmin(current_user)
    remision = await _get_remision_or_404(db, remision_id)

    if remision.status != "BORRADOR":
        raise HTTPException(status_code=409, detail="Solo se pueden agregar ítems a remisiones en BORRADOR")

    # Check spare_part_item exists
    spi_result = await db.execute(
        select(SparePartItem).where(SparePartItem.id == payload.spare_part_item_id)
    )
    spi = spi_result.scalar_one_or_none()
    if spi is None:
        raise HTTPException(status_code=422, detail="spare_part_item_id no existe")

    # Check availability from VIEW
    qty_available = await _get_availability(db, payload.spare_part_item_id)
    if qty_available is None or qty_available <= 0:
        raise HTTPException(
            status_code=409,
            detail=f"El ítem {payload.spare_part_item_id} no tiene stock disponible",
        )
    if payload.qty_dispatched > qty_available:
        raise HTTPException(
            status_code=409,
            detail=f"qty_dispatched ({payload.qty_dispatched}) excede qty_available ({qty_available})",
        )

    part_number = spi.part_number.strip().upper().replace(" ", "")

    item = InventoryRemisionItem(
        id=uuid.uuid4(),
        remision_id=remision_id,
        spare_part_item_id=payload.spare_part_item_id,
        part_number=part_number,
        qty_dispatched=payload.qty_dispatched,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)

    read = RemisionItemRead.model_validate(item)
    read = read.model_copy(update={"qty_available": qty_available})
    return read


# ---------------------------------------------------------------------------
# PUT /{id}/items/{item_id} — update qty (BORRADOR only)
# ---------------------------------------------------------------------------

@router.put("/{remision_id}/items/{item_id}", response_model=RemisionItemRead)
async def update_item(
    remision_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: RemisionItemUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_superadmin(current_user)
    remision = await _get_remision_or_404(db, remision_id)

    if remision.status != "BORRADOR":
        raise HTTPException(status_code=409, detail="Solo se pueden editar ítems de remisiones en BORRADOR")

    item_result = await db.execute(
        select(InventoryRemisionItem)
        .where(
            InventoryRemisionItem.id == item_id,
            InventoryRemisionItem.remision_id == remision_id,
        )
    )
    item = item_result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Ítem no encontrado en esta remisión")

    qty_available = await _get_availability(db, item.spare_part_item_id)
    if qty_available is None or qty_available <= 0:
        raise HTTPException(status_code=409, detail="El ítem ya no tiene stock disponible")
    if payload.qty_dispatched > qty_available:
        raise HTTPException(
            status_code=409,
            detail=f"qty_dispatched ({payload.qty_dispatched}) excede qty_available ({qty_available})",
        )

    item.qty_dispatched = payload.qty_dispatched
    await db.commit()
    await db.refresh(item)

    read = RemisionItemRead.model_validate(item)
    read = read.model_copy(update={"qty_available": qty_available})
    return read


# ---------------------------------------------------------------------------
# DELETE /{id}/items/{item_id} — remove item (BORRADOR only)
# ---------------------------------------------------------------------------

@router.delete("/{remision_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    remision_id: uuid.UUID,
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_superadmin(current_user)
    remision = await _get_remision_or_404(db, remision_id)

    if remision.status != "BORRADOR":
        raise HTTPException(status_code=409, detail="Solo se pueden eliminar ítems de remisiones en BORRADOR")

    item_result = await db.execute(
        select(InventoryRemisionItem)
        .where(
            InventoryRemisionItem.id == item_id,
            InventoryRemisionItem.remision_id == remision_id,
        )
    )
    item = item_result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Ítem no encontrado en esta remisión")

    await db.delete(item)
    await db.commit()


# ---------------------------------------------------------------------------
# POST /{id}/despachar — dispatch with pessimistic locking
# ---------------------------------------------------------------------------

@router.post("/{remision_id}/despachar", response_model=DispatchResponse)
async def despachar(
    remision_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_superadmin(current_user)

    # Reload inside transaction for freshness
    remision = await _get_remision_or_404(db, remision_id)

    if remision.status != "BORRADOR":
        raise HTTPException(status_code=409, detail=f"La remisión tiene status {remision.status}, debe ser BORRADOR")

    if not remision.items:
        raise HTTPException(status_code=409, detail="La remisión no tiene ítems — agregue al menos uno antes de despachar")

    item_ids = [item.spare_part_item_id for item in remision.items]

    # Pessimistic lock on spare_part_items rows
    await db.execute(
        select(SparePartItem).where(SparePartItem.id.in_(item_ids)).with_for_update()
    )

    # Re-validate availability from VIEW (inside the lock)
    conflicts = []
    for item in remision.items:
        qty_available = await _get_availability(db, item.spare_part_item_id)
        available = qty_available if qty_available is not None else 0
        if item.qty_dispatched > available:
            conflicts.append(
                f"{item.part_number}: requested {item.qty_dispatched}, available {available}"
            )

    if conflicts:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Stock insuficiente para: {'; '.join(conflicts)}",
        )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    actor_id = uuid.UUID(current_user.user_id)

    # Insert movements with delta = -qty_dispatched
    for item in remision.items:
        movement = InventoryRemisionMovement(
            id=uuid.uuid4(),
            remision_id=remision_id,
            spare_part_item_id=item.spare_part_item_id,
            part_number=item.part_number,
            delta=-item.qty_dispatched,
            movement_type="DESPACHO",
            created_by=actor_id,
            created_at=now,
        )
        db.add(movement)

    # Assign remision_number: REM-{YYYY}-{MAX(seq)+1:04d} under the same lock
    year = now.year
    prefix = f"REM-{year}-"
    seq_result = await db.execute(
        text(
            "SELECT MAX(CAST(SUBSTRING(remision_number FROM :start) AS INTEGER)) "
            "FROM inventory_remisions "
            "WHERE remision_number LIKE :prefix"
        ),
        {"start": len(prefix) + 1, "prefix": f"{prefix}%"},
    )
    current_max = seq_result.scalar()
    next_seq = (current_max or 0) + 1
    remision_number = f"{prefix}{next_seq:04d}"

    # Update remision status
    remision.status = "DESPACHADO"
    remision.remision_number = remision_number
    remision.dispatched_by = actor_id
    remision.dispatched_at = now
    remision.updated_at = now

    await db.commit()

    # Reload with all relationships
    remision = await _get_remision_or_404(db, remision_id)
    return _build_detail(remision)


# ---------------------------------------------------------------------------
# POST /{id}/anular — cancel a dispatched remision
# ---------------------------------------------------------------------------

@router.post("/{remision_id}/anular", response_model=DispatchResponse)
async def anular(
    remision_id: uuid.UUID,
    payload: CancelRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_superadmin(current_user)
    remision = await _get_remision_or_404(db, remision_id)

    if remision.status == "ANULADO":
        raise HTTPException(status_code=409, detail="La remisión ya fue anulada")

    if remision.status != "DESPACHADO":
        raise HTTPException(
            status_code=409,
            detail=f"Solo se pueden anular remisiones DESPACHADAS (status actual: {remision.status})",
        )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    actor_id = uuid.UUID(current_user.user_id)

    # Load dispatch movements to create counter-movements
    dispatch_movements_result = await db.execute(
        select(InventoryRemisionMovement)
        .where(
            InventoryRemisionMovement.remision_id == remision_id,
            InventoryRemisionMovement.movement_type == "DESPACHO",
        )
    )
    dispatch_movements = dispatch_movements_result.scalars().all()

    # Insert counter-movements with delta = +qty_dispatched (positive reversal)
    for dm in dispatch_movements:
        counter = InventoryRemisionMovement(
            id=uuid.uuid4(),
            remision_id=remision_id,
            spare_part_item_id=dm.spare_part_item_id,
            part_number=dm.part_number,
            delta=-dm.delta,  # reversal: if DESPACHO was -5, ANULACION is +5
            movement_type="ANULACION",
            created_by=actor_id,
            created_at=now,
        )
        db.add(counter)

    remision.status = "ANULADO"
    remision.cancelled_by = actor_id
    remision.cancelled_at = now
    remision.cancellation_reason = payload.cancellation_reason
    remision.updated_at = now

    await db.commit()

    remision = await _get_remision_or_404(db, remision_id)
    return _build_detail(remision)
