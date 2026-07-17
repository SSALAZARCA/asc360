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
from app.models.user import User
from app.schemas.remisiones import (
    RemisionCreate,
    RemisionUpdate,
    RemisionRead,
    RemisionDetail,
    RemisionItemCreate,
    RemisionItemRead,
    RemisionItemUpdate,
    DispatchResponse,
    CancelRequest,
    AvailabilityItem,
    RemisionListResponse,
    RemisionInvoicedUpdate,
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

    stmt = select(InventoryRemision).options(selectinload(InventoryRemision.items))
    if filters:
        stmt = stmt.where(*filters)
    stmt = stmt.order_by(InventoryRemision.created_at.desc()).offset(skip).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()

    remision_reads = []
    for r in rows:
        read = RemisionRead.model_validate(r)
        read.items_count = len(r.items)
        remision_reads.append(read)

    return RemisionListResponse(
        items=remision_reads,
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
# GET /export — Excel export, one row per ITEM (remisión header fields
# repeated per item row), date-range filtered on the remisión's created_at.
# MUST be registered before GET /{remision_id} — same HTTP method + single
# path segment, so route order decides which one "export" would match.
# ---------------------------------------------------------------------------

REMISION_TYPE_LABELS = {
    "PEDIDO": "Pedido",
    "GARANTIA": "Garantía",
    "CORTESIA": "Cortesía",
    "VEHICULO_PROPIO": "Consumo Interno",
}

REMISION_STATUS_LABELS = {
    "BORRADOR": "Borrador",
    "DESPACHADO": "Despachado",
    "ANULADO": "Anulado",
}


async def _resolve_remision_actor_names(db: AsyncSession, remisiones: list) -> dict:
    """Batch-resolves created_by/dispatched_by user ids to display names for
    the export — one extra query total, not one per remisión."""
    user_ids = set()
    for r in remisiones:
        if r.created_by:
            user_ids.add(r.created_by)
        if r.dispatched_by:
            user_ids.add(r.dispatched_by)

    if not user_ids:
        return {}
    result = await db.execute(select(User.id, User.name).where(User.id.in_(user_ids)))
    return {row[0]: row[1] for row in result.all()}


async def _resolve_avg_fob_costs(db: AsyncSession, remisiones: list) -> dict:
    """Batch-resolves each distinct dispatched part_number to its catalog
    `avg_fob_cost` (or None if no PartsReference/cost history exists yet —
    a real, expected case, not an error). One `_find_reference_for_part_number`
    call per DISTINCT part_number across the whole export, not per row."""
    from app.services.pricing_service import _find_reference_for_part_number

    # Insertion-ordered de-dup (not a bare set): keeps resolution order
    # deterministic/reproducible instead of depending on hash-seed-dependent
    # set iteration order.
    part_numbers = list(dict.fromkeys(item.part_number for r in remisiones for item in r.items))
    costs_by_part: dict = {}
    for part_number in part_numbers:
        ref = await _find_reference_for_part_number(db, part_number)
        costs_by_part[part_number] = ref.avg_fob_cost if ref else None
    return costs_by_part


def _price_column_value(remision_type: str, avg_fob_cost, factors: dict):
    """Single price column whose meaning depends on the remisión's type:
    - GARANTIA / VEHICULO_PROPIO (Consumo Interno): costo nacionalizado (COP).
    - PEDIDO: valor a distribuidor (COP).
    - CORTESIA (or anything else): blank — no price was requested for this type.
    Blank (None) whenever there's no cost data for the part, never 0."""
    from app.services.pricing_service import compute_prices

    if remision_type not in ("GARANTIA", "VEHICULO_PROPIO", "PEDIDO"):
        return None
    prices = compute_prices(avg_fob_cost, factors)
    if remision_type == "PEDIDO":
        return prices["precio_distribuidor"]
    return prices["costo_importado"]


def _build_export_rows(remisiones: list, names_by_id: dict, costs_by_part: dict, factors: dict) -> list:
    """One row per dispatched item; remisión-level fields repeat across all
    of that remisión's item rows. A remisión with zero items (only possible
    for BORRADOR) still emits one row with blank part/qty, so it isn't
    silently dropped from the export."""
    rows = []
    for r in remisiones:
        header_fields = [
            r.remision_number,
            REMISION_TYPE_LABELS.get(r.type, r.type),
            REMISION_STATUS_LABELS.get(r.status, r.status),
            "Sí" if r.invoiced else "No",
        ]
        trailer_fields = [
            r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else None,
            names_by_id.get(r.created_by),
            r.dispatched_at.strftime("%Y-%m-%d %H:%M") if r.dispatched_at else None,
            names_by_id.get(r.dispatched_by) if r.dispatched_by else None,
            r.notes,
        ]
        if r.items:
            for item in r.items:
                price = _price_column_value(r.type, costs_by_part.get(item.part_number), factors)
                total = round(price * item.qty_dispatched, 0) if price is not None else None
                rows.append(
                    header_fields + [item.part_number, item.qty_dispatched, price, total] + trailer_fields
                )
        else:
            rows.append(header_fields + [None, None, None, None] + trailer_fields)
    return rows


@router.get("/export")
async def export_remisiones(
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_superadmin(current_user)

    from app.api.v1.imports import _excel_response

    filters = []
    if date_from:
        filters.append(InventoryRemision.created_at >= date_from)
    if date_to:
        filters.append(InventoryRemision.created_at <= date_to)

    stmt = select(InventoryRemision).options(selectinload(InventoryRemision.items))
    if filters:
        stmt = stmt.where(*filters)
    stmt = stmt.order_by(InventoryRemision.created_at.desc())
    remisiones = (await db.execute(stmt)).scalars().all()

    from app.services.pricing_service import get_pricing_factors

    names_by_id = await _resolve_remision_actor_names(db, remisiones)
    costs_by_part = await _resolve_avg_fob_costs(db, remisiones)
    factors = await get_pricing_factors(db)

    headers = [
        "Número", "Tipo", "Estado", "Facturada", "Part Number", "Cantidad Despachada",
        "Costo/Valor Distribuidor (COP)", "Total (COP)",
        "Fecha creación", "Creado por", "Fecha despacho", "Despachado por", "Notas",
    ]
    rows = _build_export_rows(remisiones, names_by_id, costs_by_part, factors)

    if date_from and date_to:
        filename = f"remisiones_{date_from.date()}_{date_to.date()}.xlsx"
    else:
        filename = f"remisiones_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"

    return _excel_response("Remisiones", headers, rows, filename)


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
    _seq_start = len(prefix) + 1
    seq_result = await db.execute(
        text(
            f"SELECT MAX(CAST(SUBSTRING(remision_number FROM {_seq_start}) AS INTEGER)) "
            "FROM inventory_remisions "
            "WHERE remision_number LIKE :prefix"
        ),
        {"prefix": f"{prefix}%"},
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


# ---------------------------------------------------------------------------
# PUT /{id} — update header + sync items of a BORRADOR remision
# ---------------------------------------------------------------------------

@router.put("/{remision_id}", response_model=RemisionDetail)
async def update_remision(
    remision_id: uuid.UUID,
    payload: RemisionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_superadmin(current_user)
    remision = await _get_remision_or_404(db, remision_id)

    if remision.status != "BORRADOR":
        raise HTTPException(
            status_code=409,
            detail=f"Solo se pueden editar remisiones en BORRADOR (status actual: {remision.status})",
        )

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # Update header fields
    remision.type = payload.type.value
    remision.reference_lot_id = payload.reference_lot_id
    remision.notes = payload.notes
    remision.updated_at = now

    # Sync items: delete existing and re-create from payload
    for item in remision.items:
        await db.delete(item)
    await db.flush()

    for item_data in payload.items:
        qty_available = await _get_availability(db, item_data.spare_part_item_id)
        available = qty_available if qty_available is not None else 0
        if item_data.qty_dispatched > available:
            raise HTTPException(
                status_code=409,
                detail=f"Stock insuficiente para {item_data.spare_part_item_id}: "
                       f"solicitado {item_data.qty_dispatched}, disponible {available}",
            )
        spi_result = await db.execute(
            select(SparePartItem).where(SparePartItem.id == item_data.spare_part_item_id)
        )
        spi = spi_result.scalar_one_or_none()
        if spi is None:
            raise HTTPException(status_code=404, detail=f"Repuesto no encontrado: {item_data.spare_part_item_id}")

        db.add(InventoryRemisionItem(
            id=uuid.uuid4(),
            remision_id=remision_id,
            spare_part_item_id=item_data.spare_part_item_id,
            part_number=spi.part_number,
            qty_dispatched=item_data.qty_dispatched,
        ))

    await db.commit()
    remision = await _get_remision_or_404(db, remision_id)
    return _build_detail(remision)


# ---------------------------------------------------------------------------
# DELETE /{id} — hard-delete a BORRADOR remision
# ---------------------------------------------------------------------------

@router.delete("/{remision_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_remision(
    remision_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_superadmin(current_user)
    remision = await _get_remision_or_404(db, remision_id)

    if remision.status != "BORRADOR":
        raise HTTPException(
            status_code=409,
            detail=f"Solo se pueden eliminar remisiones en BORRADOR (status actual: {remision.status})",
        )

    for item in remision.items:
        await db.delete(item)
    await db.delete(remision)
    await db.commit()


# ---------------------------------------------------------------------------
# PATCH /{id}/invoiced — toggle facturada flag (any status)
# ---------------------------------------------------------------------------

@router.patch("/{remision_id}/invoiced", response_model=RemisionRead)
async def update_invoiced(
    remision_id: uuid.UUID,
    payload: RemisionInvoicedUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_superadmin(current_user)
    remision = await db.get(InventoryRemision, remision_id)
    if remision is None:
        raise HTTPException(status_code=404, detail="Remisión no encontrada")

    remision.invoiced = payload.invoiced
    await db.commit()
    await db.refresh(remision)
    return RemisionRead.model_validate(remision)