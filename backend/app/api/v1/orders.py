from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
import uuid
from datetime import datetime
from pydantic import BaseModel
from app.database import get_db
from app.models.order import ServiceOrder, ServiceOrderReception, ServiceType, ServiceStatus
from app.models.user import User, Role
from app.models.vehicle import Vehicle
from app.schemas.order import OrderCreate, OrderRead, WorkLogCreate, PartCreate
from app.services.pdf_service import generate_and_upload_reception_pdf
from app.api.deps import get_current_user, get_optional_user, CurrentUser

from typing import Optional

# NOTA: get_current_user_mock se mantiene solo por compatibilidad con endpoints legacy
def get_current_user_mock() -> Optional[User]:
    return None

router = APIRouter(prefix="/orders", tags=["Orders"])

@router.post("/", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
async def create_service_order(
    order_in: OrderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_mock)
):
    # 1. Crear Entidad Principal: La Orden de Servicio
    new_order = ServiceOrder(
        tenant_id=order_in.tenant_id,
        vehicle_id=order_in.vehicle_id,
        client_id=order_in.client_id,
        service_type=order_in.service_type,
        technician_id=order_in.technician_id,
        status=ServiceStatus.pending_signature
    )
    db.add(new_order)
    await db.flush() # Para obtener el new_order.id
    
    # 2. Crear Entidad de Recepción (Checklist de Entrada)
    new_reception = ServiceOrderReception(
        order_id=new_order.id,
        mileage_km=order_in.reception.mileage_km,
        gas_level=order_in.reception.gas_level,
        customer_notes=order_in.reception.customer_notes,
        warranty_warnings=order_in.reception.warranty_warnings,
        damage_photos_urls=order_in.reception.damage_photos_urls
    )
    db.add(new_reception)
    
    # 2.1 Registrar estado inicial en el Historial para KPIs
    from app.models.order import OrderHistory
    initial_history = OrderHistory(
        order_id=new_order.id,
        from_status=None,
        to_status=ServiceStatus.pending_signature,
        changed_at=datetime.utcnow()
    )
    db.add(initial_history)
    
    # 3. Obtener metadatos del Cliente y Vehículo para poblar el PDF
    vehicle_obj = await db.get(Vehicle, order_in.vehicle_id)
    client_obj = await db.get(User, order_in.client_id) if order_in.client_id else None
    
    # 3.1 Actualizar teléfono del cliente si se provee en la orden
    if client_obj and order_in.client_phone and order_in.client_phone != "Registrado en BD":
        client_obj.phone = order_in.client_phone
        db.add(client_obj)
    
    # Pre-empacar datos como diccionarios simulando el DTO interno
    order_data = {"id": str(new_order.id), "service_type": order_in.service_type.value}
    reception_data = {
        "mileage_km": order_in.reception.mileage_km,
        "gas_level": order_in.reception.gas_level,
        "customer_notes": order_in.reception.customer_notes,
        "warranty_warnings": order_in.reception.warranty_warnings
    }
    vehicle_data = {
        "model": vehicle_obj.model if vehicle_obj else "Desconocido",
        "plate": vehicle_obj.plate if vehicle_obj else "N/A",
        "vin": vehicle_obj.vin if vehicle_obj else "N/A"
    }
    client_data = {
        "full_name": client_obj.name if client_obj else "Cliente Pendiente",
        "identification": client_obj.telegram_id if client_obj else "N/A" # TODO: Identificacion civil
    }

    # 4. Generación asíncrona del PDF con WeasyPrint subida a MinIO
    pdf_url = await generate_and_upload_reception_pdf(order_data, reception_data, vehicle_data, client_data)
    new_reception.reception_pdf_url = pdf_url

    await db.commit()
    
    # 5. Auto-registro en la Hoja de Vida del Vehículo
    try:
        from app.models.vehicle_lifecycle import VehicleLifecycleEvent, LifecycleEventType
        cliente_nombre = client_obj.name if client_obj else "Propietario no identificado"
        lifecycle_event = VehicleLifecycleEvent(
            vehicle_id=order_in.vehicle_id,
            event_type=LifecycleEventType.RECEPCION,
            km_at_event=order_in.reception.mileage_km,
            summary=f"Recepción en taller. KM: {order_in.reception.mileage_km}. Cliente: {cliente_nombre}.",
            details=order_in.reception.customer_notes,
            linked_order_id=new_order.id,
            is_automatic="auto"
        )
        db.add(lifecycle_event)
        await db.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error registrando evento en hoja de vida: {e}")
    
    # Recargar la orden con TODAS las relaciones usando eager load
    # (lazy loading no funciona en contextos async de SQLAlchemy)
    stmt = (
        select(ServiceOrder)
        .options(
            selectinload(ServiceOrder.reception),
            selectinload(ServiceOrder.vehicle),
        )
        .where(ServiceOrder.id == new_order.id)
    )
    result = await db.execute(stmt)
    final_order = result.scalar_one()
    return final_order

@router.get("/vehicle/{vehicle_id}/last-mileage")
async def get_last_mileage(vehicle_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """
    Retorna el kilometraje de la última orden de servicio registrada para un vehículo.
    Usado por Sonia para validar que el KM nuevo sea coherente con visitas previas.
    """
    from sqlalchemy import desc
    
    stmt = (
        select(ServiceOrderReception.mileage_km, ServiceOrder.created_at)
        .join(ServiceOrder, ServiceOrder.id == ServiceOrderReception.order_id)
        .where(ServiceOrder.vehicle_id == vehicle_id)
        .order_by(desc(ServiceOrder.created_at))
        .limit(1)
    )
    result = await db.execute(stmt)
    row = result.first()
    
    if not row:
        return {"last_mileage_km": None}
    
    return {"last_mileage_km": row[0], "last_visit_date": row[1].strftime("%Y-%m-%d") if row[1] else None}

@router.get("/{order_id}/pdf")
async def download_reception_pdf(
    order_id: uuid.UUID, 
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Proxy interno para descargar el PDF. 
    Verifica que el usuario tenga permiso para ver esta orden.
    """
    from ...services.pdf_service import get_pdf_stream_from_minio
    from fastapi.responses import StreamingResponse
    import io
    
    # Obtener el registro de Reception para ver dónde está el PDF en MinIO
    stmt = select(ServiceOrder).where(ServiceOrder.id == order_id).options(selectinload(ServiceOrder.reception))
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
        
    # Seguridad Multi-tenant: Si no es superadmin, debe ser de su taller
    if not current_user.is_superadmin and order.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="No tiene permiso para acceder a esta orden")

    if not order.reception or not order.reception.reception_pdf_url:
        raise HTTPException(status_code=404, detail="PDF no encontrado para esta orden")
        
    url_to_fetch = order.reception.reception_pdf_url
    
    # Extraer el object_name limpio de la URL, quitando query params de firma (?X-Amz-Algorithm=...)
    try:
        # 1. Quitar query string de la presigned URL
        url_path_only = url_to_fetch.split("?")[0]
        # 2. Ahora extraer el path despues del bucket name  
        object_name = url_path_only.split("um-service-docs/")[1]
    except IndexError:
        raise HTTPException(status_code=500, detail="Formato de URL en BD corrupto")
        
    # Pedir los bytes crudos a MinIO por el Backplane Docker
    pdf_bytes = await get_pdf_stream_from_minio(object_name)
    if not pdf_bytes:
         raise HTTPException(status_code=404, detail="El PDF físico no existe en MinIO")
         
    return StreamingResponse(
        io.BytesIO(pdf_bytes), 
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=Acta_{order_id.hex[:8]}.pdf"}
    )


@router.get("/{order_id}/detail")
async def get_order_detail(
    order_id: uuid.UUID, 
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Retorna el detalle completo de una orden para el modal del Kanban:
    - Datos de recepción (motivo ingreso, KM, nivel combustible, notas cliente, advertencias garantía, fotos)
    - Historial de cambios de estado con comentarios
    - Datos del vehículo (placa, modelo, VIN)
    - Datos del cliente y técnico asignado
    - URL del acta PDF de recepción
    """
    from sqlalchemy import desc
    from app.models.order import OrderHistory
    from app.models.vehicle import Vehicle
    from app.models.tenant import Tenant

    # Cargar orden con todas las relaciones
    stmt = (
        select(ServiceOrder)
        .options(
            selectinload(ServiceOrder.reception),
            selectinload(ServiceOrder.history),
            selectinload(ServiceOrder.vehicle),
            selectinload(ServiceOrder.client),
            selectinload(ServiceOrder.technician),
            selectinload(ServiceOrder.tenant),
            selectinload(ServiceOrder.work_logs),
            selectinload(ServiceOrder.parts),
        )
        .where(ServiceOrder.id == order_id)
    )
    res = await db.execute(stmt)
    order = res.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")

    # Seguridad Multi-tenant
    if not current_user.is_superadmin and order.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="No tiene permiso para acceder a esta orden")

    # Calcular días en taller
    end_time = order.delivered_at or datetime.utcnow()
    days_in_shop = (end_time - order.created_at).days if order.created_at else 0

    # Construir historial de estados con comentarios
    history_list = []
    if order.history:
        sorted_history = sorted(order.history, key=lambda h: h.changed_at)
        for h in sorted_history:
            history_list.append({
                "from_status": h.from_status.value if h.from_status else None,
                "to_status": h.to_status.value if h.to_status else None,
                "changed_at": h.changed_at.isoformat() if h.changed_at else None,
                "duration_minutes": float(h.duration_minutes) if h.duration_minutes else None,
                "comments": h.comments,
            })

    # Datos de recepción
    reception_data = None
    if order.reception:
        r = order.reception
        reception_data = {
            "mileage_km": float(r.mileage_km) if r.mileage_km else None,
            "gas_level": r.gas_level,
            "customer_notes": r.customer_notes,
            "warranty_warnings": r.warranty_warnings,
            "damage_photos_urls": r.damage_photos_urls or [],
            "reception_pdf_url": r.reception_pdf_url,
            "signature_url": r.signature_url,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }

    return {
        "order_id": str(order.id),
        "estado": order.status.value,
        "tipo_trabajo": order.service_type.value,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "completed_at": order.completed_at.isoformat() if order.completed_at else None,
        "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
        "dias_en_taller": days_in_shop,
        # Vehículo
        "vehiculo": {
            "placa": order.vehicle.plate if order.vehicle else None,
            "modelo": order.vehicle.model if order.vehicle else None,
            "marca": order.vehicle.brand if order.vehicle else None,
            "vin": order.vehicle.vin if order.vehicle else None,
        } if order.vehicle else None,
        # Cliente
        "cliente": {
            "nombre": order.client.name if order.client else None,
            "telefono": order.client.phone if order.client else None,
        } if order.client else None,
        # Técnico
        "tecnico": {
            "nombre": order.technician.name if order.technician else None,
            "telefono": order.technician.phone if order.technician else None,
        } if order.technician else None,
        # Centro
        "centro": {
            "nombre": order.tenant.name if order.tenant else None,
            "ciudad": order.tenant.ciudad if order.tenant else None,
        } if order.tenant else None,
        # Recepción (motivo de ingreso)
        "recepcion": reception_data,
        # Historial de estados
        "historial": history_list,
        # Diagnósticos / notas de trabajo
        "work_logs": [
            {
                "id": str(wl.id),
                "diagnosis": wl.diagnosis,
                "media_urls": wl.media_urls or [],
                "created_at": wl.created_at.isoformat() if wl.created_at else None,
            }
            for wl in (order.work_logs or [])
        ],
        # Repuestos
        "parts": [
            {
                "id": str(p.id),
                "reference": p.reference,
                "qty": p.qty,
                "part_type": p.part_type.value,
                "status": p.status.value,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in (order.parts or [])
        ],
    }


from app.schemas.order import OrderStatusUpdate as OrderStatusUpdateSchema

@router.put("/{order_id}/status", response_model=OrderRead)
async def update_order_status(
    order_id: uuid.UUID,
    status_update: OrderStatusUpdateSchema,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[CurrentUser] = Depends(get_optional_user),
    x_sonia_secret: Optional[str] = Header(None)
):
    """
    Actualiza el estado de una Orden de Servicio.
    Acepta JWT Bearer (frontend/admin) o X-Sonia-Secret (bot Sonia).
    Acepta opcionalmente diagnóstico y repuestos para registrar en hoja de vida.
    Genera auto-eventos en VehicleLifecycleEvent según tipo de servicio.
    """
    from app.models.order import OrderHistory, OrderWorkLog, OrderPart, OrderPartType, OrderPartStatus
    from app.config import settings

    is_bot_call = x_sonia_secret == settings.SONIA_BOT_SECRET
    if not is_bot_call and current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado.")

    # 1. Obtener la orden
    stmt = select(ServiceOrder).where(ServiceOrder.id == order_id)
    res = await db.execute(stmt)
    order = res.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Orden no encontrada")

    # Seguridad Multi-tenant (el bot actúa como superadmin — puede modificar cualquier tenant)
    if not is_bot_call and current_user and not current_user.is_superadmin and order.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="No tiene permiso para modificar esta orden")

    old_status = order.status
    new_status = status_update.status

    # 2. Validación de transición: external_work → in_progress no permitido directamente
    if old_status == ServiceStatus.external_work and new_status == ServiceStatus.in_progress:
        raise HTTPException(
            status_code=409,
            detail="Debe pasar por reprogramación primero (external_work → rescheduled → in_progress)"
        )

    # 3. Registrar en Historial
    history_entry = OrderHistory(
        order_id=order.id,
        from_status=old_status,
        to_status=new_status,
        changed_at=datetime.utcnow()
    )

    # 3.1 Calcular duración del estado anterior
    last_history_stmt = (
        select(OrderHistory)
        .where(OrderHistory.order_id == order.id)
        .order_by(OrderHistory.changed_at.desc())
        .limit(1)
    )
    last_h_res = await db.execute(last_history_stmt)
    last_h = last_h_res.scalar_one_or_none()
    if last_h:
        diff = datetime.utcnow() - last_h.changed_at
        last_h.duration_minutes = diff.total_seconds() / 60.0
        db.add(last_h)

    db.add(history_entry)
    await db.flush()  # Para obtener history_entry.id

    # 4. Actualizar la Orden
    order.status = new_status
    if status_update.technician_id:
        order.technician_id = status_update.technician_id

    if new_status == ServiceStatus.completed:
        order.completed_at = datetime.utcnow()
    elif new_status == ServiceStatus.delivered:
        order.delivered_at = datetime.utcnow()

    # 5. Registrar diagnóstico (OrderWorkLog) si se provee
    if status_update.diagnosis:
        work_log = OrderWorkLog(
            order_id=order.id,
            history_id=history_entry.id,
            diagnosis=status_update.diagnosis,
            media_urls=[],
            recorded_by_telegram_id=status_update.recorded_by_telegram_id,
        )
        db.add(work_log)

    # 6. Registrar repuestos (OrderPart) si se proveen
    if status_update.parts:
        for part_in in status_update.parts:
            new_part = OrderPart(
                order_id=order.id,
                reference=part_in.reference,
                qty=part_in.qty,
                part_type=part_in.part_type,
                status=OrderPartStatus.pending,
            )
            db.add(new_part)

    await db.commit()

    # 7. Auto-eventos en hoja de vida
    try:
        from app.models.vehicle_lifecycle import VehicleLifecycleEvent, LifecycleEventType

        lifecycle_event = None

        if new_status == ServiceStatus.completed:
            if order.service_type == ServiceType.warranty:
                lifecycle_event = VehicleLifecycleEvent(
                    vehicle_id=order.vehicle_id,
                    event_type=LifecycleEventType.GARANTIA,
                    summary=f"Garantía aplicada. Orden {str(order.id)[:8]}.",
                    details=status_update.diagnosis,
                    linked_order_id=order.id,
                    is_automatic="auto"
                )
            elif order.service_type == ServiceType.km_review:
                # Obtener km de la recepción
                reception_stmt = select(ServiceOrderReception).where(ServiceOrderReception.order_id == order.id)
                rec_res = await db.execute(reception_stmt)
                reception = rec_res.scalar_one_or_none()
                lifecycle_event = VehicleLifecycleEvent(
                    vehicle_id=order.vehicle_id,
                    event_type=LifecycleEventType.MANTENIMIENTO,
                    km_at_event=reception.mileage_km if reception else None,
                    summary=f"Mantenimiento por kilometraje realizado. Orden {str(order.id)[:8]}.",
                    details=status_update.diagnosis,
                    linked_order_id=order.id,
                    is_automatic="auto"
                )

        elif new_status == ServiceStatus.delivered:
            lifecycle_event = VehicleLifecycleEvent(
                vehicle_id=order.vehicle_id,
                event_type=LifecycleEventType.ENTREGA,
                summary=f"Motocicleta entregada al cliente. Orden {str(order.id)[:8]}.",
                linked_order_id=order.id,
                is_automatic="auto"
            )

        if lifecycle_event:
            db.add(lifecycle_event)
            await db.commit()

    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error auto-evento lifecycle en status update: {e}")

    # Recargar con relaciones para el retorno
    query = (
        select(ServiceOrder)
        .options(
            selectinload(ServiceOrder.reception),
            selectinload(ServiceOrder.vehicle),
            selectinload(ServiceOrder.work_logs),
            selectinload(ServiceOrder.parts),
        )
        .where(ServiceOrder.id == order.id)
    )
    res = await db.execute(query)
    full_order = res.scalar_one()
    return full_order


@router.post("/{order_id}/work-log", status_code=status.HTTP_201_CREATED)
async def add_work_log(
    order_id: uuid.UUID,
    work_log_in: WorkLogCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """Agrega un diagnóstico/nota de trabajo a una orden."""
    from app.models.order import OrderWorkLog

    stmt = select(ServiceOrder).where(ServiceOrder.id == order_id)
    res = await db.execute(stmt)
    order = res.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    if not current_user.is_superadmin and order.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Sin permiso")

    work_log = OrderWorkLog(
        order_id=order_id,
        diagnosis=work_log_in.diagnosis,
        media_urls=work_log_in.media_urls or [],
        recorded_by_telegram_id=work_log_in.recorded_by_telegram_id,
    )
    db.add(work_log)

    # También crear NOTA_TECNICA en hoja de vida
    try:
        from app.models.vehicle_lifecycle import VehicleLifecycleEvent, LifecycleEventType
        nota = VehicleLifecycleEvent(
            vehicle_id=order.vehicle_id,
            event_type=LifecycleEventType.NOTA_TECNICA,
            summary=work_log_in.diagnosis[:200],
            details=work_log_in.diagnosis,
            linked_order_id=order_id,
            created_by_telegram_id=work_log_in.recorded_by_telegram_id,
            is_automatic="auto"
        )
        db.add(nota)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error creando NOTA_TECNICA: {e}")

    await db.commit()
    await db.refresh(work_log)
    return {"id": str(work_log.id), "order_id": str(order_id), "diagnosis": work_log.diagnosis}


@router.post("/{order_id}/parts", status_code=status.HTTP_201_CREATED)
async def add_order_parts(
    order_id: uuid.UUID,
    parts_in: list[PartCreate],
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """Agrega repuestos requeridos a una orden."""
    from app.models.order import OrderPart, OrderPartStatus

    stmt = select(ServiceOrder).where(ServiceOrder.id == order_id)
    res = await db.execute(stmt)
    order = res.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    if not current_user.is_superadmin and order.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Sin permiso")

    created = []
    for part_in in parts_in:
        new_part = OrderPart(
            order_id=order_id,
            reference=part_in.reference,
            qty=part_in.qty,
            part_type=part_in.part_type,
            status=OrderPartStatus.pending,
        )
        db.add(new_part)
        created.append(new_part)

    await db.commit()
    return {"created": len(created), "order_id": str(order_id)}


@router.get("/active/technician/{technician_id}", response_model=list[OrderRead])
async def get_active_orders_for_tech(
    technician_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """Obtiene las órdenes activas anexadas a un técnico. (Omitiendo completadas/entregadas/canceladas)."""
    exclude_statuses = [ServiceStatus.completed, ServiceStatus.delivered, ServiceStatus.cancelled]
    stmt = (
        select(ServiceOrder)
        .options(
            selectinload(ServiceOrder.reception),
            selectinload(ServiceOrder.vehicle),
            selectinload(ServiceOrder.work_logs),
            selectinload(ServiceOrder.parts),
        )
        .where(ServiceOrder.technician_id == technician_id)
        .where(ServiceOrder.status.not_in(exclude_statuses))
    )
    res = await db.execute(stmt)
    orders = res.scalars().all()
    result = []
    for o in orders:
        read = OrderRead.model_validate(o)
        read.plate = o.vehicle.plate if o.vehicle else None
        result.append(read)
    return result


@router.get("/active/tenant/{tenant_id}", response_model=list[OrderRead])
async def get_active_orders_for_tenant(
    tenant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """Filtra todas las órdenes activas de un taller específico. (Para rol Admin)."""
    exclude_statuses = [ServiceStatus.completed, ServiceStatus.delivered, ServiceStatus.cancelled]
    stmt = (
        select(ServiceOrder)
        .options(selectinload(ServiceOrder.reception), selectinload(ServiceOrder.vehicle))
        .where(ServiceOrder.tenant_id == tenant_id)
        .where(ServiceOrder.status.not_in(exclude_statuses))
    )
    res = await db.execute(stmt)
    return res.scalars().all()

@router.get("/dashboard/admin")
async def get_admin_dashboard(db: AsyncSession = Depends(get_db)):
    """
    Retorna el total de motocicletas activas divididas por antigüedad:
    - 0 a 1 día
    - 1 a 3 días
    - 3 a 5 días
    - Más de 5 días
    """
    exclude_statuses = [ServiceStatus.completed, ServiceStatus.delivered, ServiceStatus.cancelled]
    
    stmt = (
        select(ServiceOrder)
        .where(ServiceOrder.status.not_in(exclude_statuses))
    )
    res = await db.execute(stmt)
    orders = res.scalars().all()
    
    now = datetime.utcnow()
    metrics = {
        "total_active": len(orders),
        "0_1_days": 0,
        "1_3_days": 0,
        "3_5_days": 0,
        "gt_5_days": 0
    }
    
    for o in orders:
        if not o.created_at: continue
        diff_days = (now - o.created_at).days
        
        if diff_days <= 1:
            metrics["0_1_days"] += 1
        elif diff_days <= 3:
            metrics["1_3_days"] += 1
        elif diff_days <= 5:
            metrics["3_5_days"] += 1
        else:
            metrics["gt_5_days"] += 1
            
    return metrics


@router.get("/analytics/kpis")
async def get_kpi_analytics(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Retorna los KPIs detallados. El tenant_id se extrae SIEMPRE del JWT:
    - superadmin: ve toda la red
    - otros roles: solo ven su propio taller
    """
    from sqlalchemy import func, case
    from app.models.order import OrderHistory
    from app.models.tenant import Tenant
    
    now = datetime.utcnow()
    
    # 1. Filtro por tenant extraído del JWT — nunca del query string
    # Si es superadmin: ve toda la red. Cualquier otro rol: solo su taller.
    tenant_id = None if current_user.is_superadmin else current_user.tenant_id
    
    base_stmt = select(ServiceOrder)
    if tenant_id:
        base_stmt = base_stmt.where(ServiceOrder.tenant_id == tenant_id)
    
    res = await db.execute(base_stmt)
    orders = res.scalars().all()
    
    # 2. Semáforo y Tiempo Promedio Total
    semaphore = {"green": 0, "yellow": 0, "red": 0}
    total_cycle_minutes = 0
    completed_cycles = 0
    
    for o in orders:
        if o.status not in [ServiceStatus.completed, ServiceStatus.delivered, ServiceStatus.cancelled]:
            diff_days = (now - o.created_at).days
            if diff_days <= 2: semaphore["green"] += 1
            elif diff_days <= 5: semaphore["yellow"] += 1
            else: semaphore["red"] += 1
        
        # Tiempo total solo para entregados
        if o.delivered_at and o.created_at:
            total_cycle_minutes += (o.delivered_at - o.created_at).total_seconds() / 60.0
            completed_cycles += 1
            
    avg_total_time = total_cycle_minutes / completed_cycles if completed_cycles > 0 else 0
    
    # 3. Cantidad por Estado y Tiempos por Estado
    # Usamos Group By en la base de datos para eficiencia
    count_by_status = {}
    for status in ServiceStatus:
        count_by_status[status.value] = 0
        
    for o in orders:
        if o.status not in [ServiceStatus.delivered, ServiceStatus.cancelled]:
            count_by_status[o.status.value] += 1
            
    # Tiempos promedio por estado desde OrderHistory
    history_stmt = select(
        OrderHistory.from_status,
        func.avg(OrderHistory.duration_minutes).label("avg_duration")
    ).where(OrderHistory.duration_minutes.isnot(None))
    
    if tenant_id:
        history_stmt = history_stmt.join(ServiceOrder).where(ServiceOrder.tenant_id == tenant_id)
        
    history_stmt = history_stmt.group_by(OrderHistory.from_status)
    h_res = await db.execute(history_stmt)
    
    avg_time_by_status = {row[0].value if row[0] else "start": float(row[1]) for row in h_res.all()}

    # 4. Gestión de Garantías (Top Centros por tiempo)
    # Filtramos órdenes de tipo garantía y calculamos promedio por taller
    warranty_stmt = (
        select(
            Tenant.name,
            func.avg(
                func.extract('epoch', ServiceOrder.delivered_at - ServiceOrder.created_at) / 60.0
            ).label("avg_minutes")
        )
        .join(ServiceOrder, Tenant.id == ServiceOrder.tenant_id)
        .where(ServiceOrder.service_type == ServiceType.warranty)
        .where(ServiceOrder.delivered_at.isnot(None))
        .group_by(Tenant.name)
        .order_by(func.avg(func.extract('epoch', ServiceOrder.delivered_at - ServiceOrder.created_at)).desc())
    )
    w_res = await db.execute(warranty_stmt)
    warranty_management = [{"tenant_name": row[0], "avg_minutes": float(row[1])} for row in w_res.all()]

    return {
        "semaphore": semaphore,
        "avg_total_time_minutes": avg_total_time,
        "count_by_status": count_by_status,
        "avg_time_by_status": avg_time_by_status,
        "warranty_management": warranty_management
    }


@router.get("/analytics/services")
async def get_services_analytics(
    service_type: Optional[ServiceType] = None,
    city: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Retorna la Tabla Maestra para la Página 2 del Dashboard.
    El tenant_id se extrae del JWT — superadmin ve toda la red,
    rol de taller solo ve sus propias órdenes.
    """
    from sqlalchemy import func, and_, select, desc
    from app.models.tenant import Tenant
    from app.models.vehicle import Vehicle
    from app.models.order import ServiceOrderReception
    from datetime import timedelta

    two_months_ago = datetime.utcnow() - timedelta(days=60)

    # 1. Query base con joins para obtener toda la info necesaria
    stmt = (
        select(
            ServiceOrder,
            Vehicle.plate,
            Tenant.name.label("tenant_name"),
            Tenant.ciudad.label("tenant_city"),
            ServiceOrderReception.mileage_km
        )
        .join(Vehicle, ServiceOrder.vehicle_id == Vehicle.id)
        .join(Tenant, ServiceOrder.tenant_id == Tenant.id)
        .outerjoin(ServiceOrderReception, ServiceOrder.id == ServiceOrderReception.order_id)
        .options(selectinload(ServiceOrder.reception))
    )

    # Filtro por tenant extraído del JWT
    tenant_id = None if current_user.is_superadmin else current_user.tenant_id
    
    # 2. Aplicar filtros dinámicos
    if tenant_id:
        stmt = stmt.where(ServiceOrder.tenant_id == tenant_id)
    if service_type:
        stmt = stmt.where(ServiceOrder.service_type == service_type)
    if city:
        stmt = stmt.where(Tenant.ciudad == city)

    stmt = stmt.order_by(desc(ServiceOrder.created_at))
    res = await db.execute(stmt)
    results = res.all()

    services_data = []

    for row in results:
        order = row[0]
        plate = row[1]
        tenant_name = row[2]
        city_name = row[3]
        mileage = row[4]

        # 3. Calcular métricas históricas reales por vehículo (PLACA)
        # Visitas totales
        total_visits_stmt = select(func.count(ServiceOrder.id)).join(Vehicle).where(Vehicle.plate == plate)
        total_visits_res = await db.execute(total_visits_stmt)
        total_visits = total_visits_res.scalar()

        # Visitas últimos 2 meses
        recent_visits_stmt = (
            select(func.count(ServiceOrder.id))
            .join(Vehicle)
            .where(and_(Vehicle.plate == plate, ServiceOrder.created_at >= two_months_ago))
        )
        recent_visits_res = await db.execute(recent_visits_stmt)
        recent_visits = recent_visits_res.scalar()

        # Garantías totales
        warranty_count_stmt = (
            select(func.count(ServiceOrder.id))
            .join(Vehicle)
            .where(and_(Vehicle.plate == plate, ServiceOrder.service_type == ServiceType.warranty))
        )
        warranty_count_res = await db.execute(warranty_count_stmt)
        warranty_count = warranty_count_res.scalar()

        # Calcular tiempo en taller
        end_time = order.delivered_at or datetime.utcnow()
        time_in_taller_days = (end_time - order.created_at).days

        services_data.append({
            "order_id": str(order.id),
            "placa": plate,
            "estado": order.status.value,
            "tiempo_taller_dias": time_in_taller_days,
            "kilometraje": float(mileage) if mileage else 0,
            "tipo_trabajo": order.service_type.value,
            "ciudad": city_name,
            "v_totales": total_visits,
            "v_2meses": recent_visits,
            "g_totales": warranty_count,
            "centro_actual": tenant_name,
            "pdf_url": order.reception.reception_pdf_url if order.reception else None
        })

    return services_data


# ─── OTP Endpoints ────────────────────────────────────────────────────────────

import random
import string
from datetime import timedelta

OTP_EXPIRE_MINUTES = 10
OTP_MAX_ATTEMPTS   = 3
OTP_MAX_RESENDS    = 3


@router.post("/{order_id}/otp/send", status_code=status.HTTP_200_OK)
async def send_otp(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Genera y envía un OTP SMS al teléfono del cliente.
    Solo disponible para órdenes en estado pending_signature.
    Máximo 3 reenvíos por orden.
    """
    from app.models.order import OrderOTP
    from app.services.sms_service import send_otp_sms
    from sqlalchemy import func

    stmt = (
        select(ServiceOrder)
        .options(selectinload(ServiceOrder.client))
        .where(ServiceOrder.id == order_id)
    )
    res = await db.execute(stmt)
    order = res.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    if not current_user.is_superadmin and order.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Sin permiso")
    if order.status != ServiceStatus.pending_signature:
        raise HTTPException(status_code=409, detail="La orden no está pendiente de firma")

    phone = order.client.phone if order.client else None
    if not phone:
        raise HTTPException(status_code=422, detail="El cliente no tiene teléfono registrado")

    # Verificar límite de reenvíos (contar OTPs ya generados para esta orden)
    count_stmt = select(func.count()).where(OrderOTP.order_id == order_id)
    count_res = await db.execute(count_stmt)
    total_sent = count_res.scalar()
    if total_sent >= OTP_MAX_RESENDS:
        raise HTTPException(status_code=429, detail="Se alcanzó el límite de reenvíos para esta orden")

    # Invalidar OTPs anteriores marcándolos como usados
    prev_stmt = (
        select(OrderOTP)
        .where(OrderOTP.order_id == order_id)
        .where(OrderOTP.used_at.is_(None))
    )
    prev_res = await db.execute(prev_stmt)
    for prev in prev_res.scalars().all():
        prev.used_at = datetime.utcnow()
        db.add(prev)

    # Generar nuevo código
    code = ''.join(random.choices(string.digits, k=6))
    now  = datetime.utcnow()
    otp  = OrderOTP(
        order_id=order_id,
        phone=phone,
        code=code,
        created_at=now,
        expires_at=now + timedelta(minutes=OTP_EXPIRE_MINUTES),
    )
    db.add(otp)
    await db.commit()

    await send_otp_sms(phone, code)

    masked = f"***{phone[-4:]}" if len(phone) >= 4 else "****"
    return {"message": f"OTP enviado a {masked}", "expires_in_minutes": OTP_EXPIRE_MINUTES}


@router.get("/pending-otp", status_code=status.HTTP_200_OK)
async def get_pending_otp_orders(
    db: AsyncSession = Depends(get_db),
    current_user: Optional[CurrentUser] = Depends(get_optional_user),
    x_sonia_secret: Optional[str] = Header(None),
):
    """Lista todas las órdenes pendientes de firma OTP. Acepta JWT o X-Sonia-Secret."""
    from app.config import settings
    is_bot_call = x_sonia_secret == settings.SONIA_BOT_SECRET
    if not is_bot_call and current_user is None:
        raise HTTPException(status_code=401, detail="No autenticado")

    stmt = (
        select(ServiceOrder)
        .options(selectinload(ServiceOrder.vehicle), selectinload(ServiceOrder.client))
        .where(ServiceOrder.status == ServiceStatus.pending_signature)
    )
    if not is_bot_call and current_user and not current_user.is_superadmin:
        stmt = stmt.where(ServiceOrder.tenant_id == current_user.tenant_id)

    res = await db.execute(stmt)
    orders = res.scalars().all()

    return [
        {
            "order_id": str(o.id),
            "placa": o.vehicle.plate if o.vehicle else "N/D",
            "cliente": o.client.name if o.client else "N/D",
            "created_at": o.created_at.isoformat() if o.created_at else None,
        }
        for o in orders
    ]


@router.get("/pending-otp/plate/{plate}", status_code=status.HTTP_200_OK)
async def get_pending_otp_by_plate(
    plate: str,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[CurrentUser] = Depends(get_optional_user),
    x_sonia_secret: Optional[str] = Header(None),
):
    """Retorna la orden pending_signature para una placa específica."""
    from app.config import settings
    from app.models.vehicle import Vehicle
    is_bot_call = x_sonia_secret == settings.SONIA_BOT_SECRET
    if not is_bot_call and current_user is None:
        raise HTTPException(status_code=401, detail="No autenticado")

    stmt = (
        select(ServiceOrder)
        .join(Vehicle, ServiceOrder.vehicle_id == Vehicle.id)
        .where(Vehicle.plate == plate.upper())
        .where(ServiceOrder.status == ServiceStatus.pending_signature)
        .order_by(ServiceOrder.created_at.desc())
        .limit(1)
    )
    res = await db.execute(stmt)
    order = res.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=404, detail="No hay orden pendiente de firma para esta placa")

    return {"order_id": str(order.id), "placa": plate.upper()}


@router.post("/{order_id}/otp/verify", status_code=status.HTTP_200_OK)
async def verify_otp(
    order_id: uuid.UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[CurrentUser] = Depends(get_optional_user),
    x_sonia_secret: Optional[str] = Header(None),
):
    """
    Valida el OTP ingresado por el asesor.
    Si es correcto: orden pasa a received, recepción queda marcada con accepted_at,
    y el PDF es regenerado con el sello de aceptación.
    """
    from app.models.order import OrderOTP, OrderHistory

    from app.config import settings
    is_bot_call = x_sonia_secret == settings.SONIA_BOT_SECRET
    if not is_bot_call and current_user is None:
        raise HTTPException(status_code=401, detail="No autenticado")

    code_input = str(body.get("code", "")).strip()
    if not code_input:
        raise HTTPException(status_code=422, detail="Debe ingresar el código OTP")

    stmt = (
        select(ServiceOrder)
        .options(
            selectinload(ServiceOrder.reception),
            selectinload(ServiceOrder.client),
            selectinload(ServiceOrder.vehicle),
        )
        .where(ServiceOrder.id == order_id)
    )
    res = await db.execute(stmt)
    order = res.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")
    if not is_bot_call and current_user and not current_user.is_superadmin and order.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Sin permiso")
    if order.status != ServiceStatus.pending_signature:
        raise HTTPException(status_code=409, detail="La orden no está pendiente de firma")

    # Buscar OTP activo (no usado, no expirado)
    now = datetime.utcnow()
    otp_stmt = (
        select(OrderOTP)
        .where(OrderOTP.order_id == order_id)
        .where(OrderOTP.used_at.is_(None))
        .where(OrderOTP.expires_at > now)
        .order_by(OrderOTP.created_at.desc())
        .limit(1)
    )
    otp_res = await db.execute(otp_stmt)
    otp = otp_res.scalar_one_or_none()

    if not otp:
        raise HTTPException(status_code=404, detail="No hay un OTP activo para esta orden. Solicitá uno nuevo.")

    # Registrar intento
    otp.attempts += 1
    db.add(otp)

    if otp.attempts > OTP_MAX_ATTEMPTS:
        otp.used_at = now  # Invalidar
        await db.commit()
        raise HTTPException(status_code=429, detail="Se superó el máximo de intentos. Solicitá un nuevo OTP.")

    if otp.code != code_input:
        await db.commit()
        remaining = OTP_MAX_ATTEMPTS - otp.attempts
        raise HTTPException(
            status_code=400,
            detail=f"Código incorrecto. Intentos restantes: {remaining}"
        )

    # OTP correcto — invalidar y registrar aceptación
    otp.used_at = now
    db.add(otp)

    masked_phone = f"***{otp.phone[-4:]}" if len(otp.phone) >= 4 else "****"

    reception = order.reception
    if reception:
        reception.accepted_at = now
        reception.accepted_phone = masked_phone
        db.add(reception)

    # Transición: pending_signature → received
    history_entry = OrderHistory(
        order_id=order.id,
        from_status=ServiceStatus.pending_signature,
        to_status=ServiceStatus.received,
        changed_at=now,
        comments="Acta aceptada por OTP",
    )
    db.add(history_entry)
    order.status = ServiceStatus.received
    db.add(order)
    await db.commit()

    # Regenerar PDF con sello de aceptación
    try:
        vehicle = order.vehicle
        client  = order.client
        order_data = {
            "id": str(order.id),
            "service_type": order.service_type.value,
            "accepted_at": now.strftime("%Y-%m-%d %H:%M"),
            "accepted_phone": masked_phone,
        }
        reception_data = {
            "mileage_km": float(reception.mileage_km) if reception else 0,
            "gas_level": reception.gas_level if reception else "",
            "customer_notes": reception.customer_notes if reception else "",
            "warranty_warnings": reception.warranty_warnings if reception else "",
        }
        vehicle_data = {
            "model": vehicle.model if vehicle else "Desconocido",
            "plate": vehicle.plate if vehicle else "N/A",
            "vin": vehicle.vin if vehicle else "N/A",
        }
        client_data = {
            "full_name": client.name if client else "N/A",
            "identification": client.telegram_id if client else "N/A",
        }
        new_pdf_url = await generate_and_upload_reception_pdf(
            order_data, reception_data, vehicle_data, client_data
        )
        if new_pdf_url and reception:
            reception.reception_pdf_url = new_pdf_url
            db.add(reception)
            await db.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error regenerando PDF tras OTP: {e}")

    return {
        "message": "Acta aceptada correctamente",
        "accepted_at": now.isoformat(),
        "accepted_phone": masked_phone,
        "new_status": "received",
    }


@router.post("/{order_id}/otp/resend", status_code=status.HTTP_200_OK)
async def resend_otp(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[CurrentUser] = Depends(get_optional_user),
    x_sonia_secret: Optional[str] = Header(None),
):
    """
    Reenvía el OTP. Acepta JWT (asesor desde Kanban) o X-Sonia-Secret (bot Sonia).
    Delega internamente al endpoint send_otp.
    """
    from app.config import settings
    is_bot_call = x_sonia_secret == settings.SONIA_BOT_SECRET
    if not is_bot_call and current_user is None:
        raise HTTPException(status_code=401, detail="No autenticado")

    if current_user is None:
        # Llamada desde Sonia — construir usuario mock con permisos de superadmin
        class _BotUser:
            is_superadmin = True
            tenant_id = None
        current_user = _BotUser()

    return await send_otp(order_id, db, current_user)
