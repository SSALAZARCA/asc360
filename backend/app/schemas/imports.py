import uuid
from datetime import datetime, date
from typing import Optional, List, Any
from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Moto Units
# ---------------------------------------------------------------------------
class MotoUnitUpdate(BaseModel):
    model: Optional[str] = None
    vin_number: Optional[str] = None
    engine_number: Optional[str] = None
    color: Optional[str] = None
    model_year: Optional[int] = None
    empadronamiento_fisico_enviado: Optional[bool] = None
    empadronamiento_fisico_distribuidor_id: Optional[uuid.UUID] = None


class MotoUnitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    shipment_order_id: uuid.UUID
    item_no: Optional[int] = None
    vin_number: Optional[str] = None
    engine_number: Optional[str] = None
    color: Optional[str] = None
    model_year: Optional[int] = None
    container_no: Optional[str] = None
    seal_no: Optional[str] = None
    source_pi: Optional[str] = None
    # Datos de aduana (DIM)
    no_acep: Optional[str] = None
    f_acep: Optional[date] = None
    no_lev: Optional[str] = None
    f_lev: Optional[date] = None
    # Control de certificado
    certificado_generado: bool = False
    certificado_fecha: Optional[datetime] = None
    # Seguimiento: empadronamiento físico enviado al distribuidor
    empadronamiento_fisico_enviado: bool = False
    empadronamiento_fisico_fecha: Optional[datetime] = None
    empadronamiento_fisico_distribuidor_id: Optional[uuid.UUID] = None
    empadronamiento_fisico_distribuidor_nombre: Optional[str] = None
    # DIM PDF
    dim_pdf_object_name: Optional[str] = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Vehicle Models
# ---------------------------------------------------------------------------
class VehicleModelCreate(BaseModel):
    modelo: str
    marca: str = "UM"
    cilindrada: Optional[str] = None
    potencia: Optional[str] = None
    peso: Optional[str] = None
    vueltas_aire: Optional[str] = None
    posicion_cortina: Optional[str] = None
    sistemas_control: Optional[str] = None
    combustible: Optional[str] = "CARBURADOR"
    largo_total: Optional[str] = None
    ancho_total: Optional[str] = None
    altura_total: Optional[str] = None
    altura_silla: Optional[str] = None
    distancia_suelo: Optional[str] = None
    distancia_ejes: Optional[str] = None
    tanque_combustible: Optional[str] = None
    relacion_compresion: Optional[str] = None
    llanta_delantera: Optional[str] = None
    llanta_trasera: Optional[str] = None


class VehicleModelUpdate(BaseModel):
    modelo: Optional[str] = None
    marca: Optional[str] = None
    cilindrada: Optional[str] = None
    potencia: Optional[str] = None
    peso: Optional[str] = None
    vueltas_aire: Optional[str] = None
    posicion_cortina: Optional[str] = None
    sistemas_control: Optional[str] = None
    combustible: Optional[str] = None
    largo_total: Optional[str] = None
    ancho_total: Optional[str] = None
    altura_total: Optional[str] = None
    altura_silla: Optional[str] = None
    distancia_suelo: Optional[str] = None
    distancia_ejes: Optional[str] = None
    tanque_combustible: Optional[str] = None
    relacion_compresion: Optional[str] = None
    llanta_delantera: Optional[str] = None
    llanta_trasera: Optional[str] = None


class VehicleModelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    modelo: str = Field(alias="model_name")
    marca: str = Field(alias="brand")
    cilindrada: Optional[str] = None
    potencia: Optional[str] = None
    peso: Optional[str] = None
    vueltas_aire: Optional[str] = None
    posicion_cortina: Optional[str] = None
    sistemas_control: Optional[str] = None
    combustible: Optional[str] = Field(None, alias="fuel_system")
    largo_total: Optional[str] = None
    ancho_total: Optional[str] = None
    altura_total: Optional[str] = None
    altura_silla: Optional[str] = None
    distancia_suelo: Optional[str] = None
    distancia_ejes: Optional[str] = None
    tanque_combustible: Optional[str] = None
    relacion_compresion: Optional[str] = None
    llanta_delantera: Optional[str] = None
    llanta_trasera: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Shipment Orders
# ---------------------------------------------------------------------------
class ShipmentOrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    cycle: Optional[int] = None
    pi_number: str
    invoice_number: Optional[str] = None
    model: Optional[str] = None
    model_year: Optional[int] = None
    qty: Optional[str] = None
    qty_numeric: Optional[int] = None
    total_units: Optional[int] = None
    containers: Optional[int] = None

    etr: Optional[datetime] = None
    etr_raw: Optional[str] = None
    etl: Optional[datetime] = None
    etl_raw: Optional[str] = None
    etd: Optional[datetime] = None
    etd_raw: Optional[str] = None
    eta: Optional[datetime] = None
    eta_raw: Optional[str] = None

    departure_port: Optional[str] = None
    bl_container: Optional[str] = None
    vessel: Optional[str] = None
    digital_docs_status: Optional[str] = None
    original_docs_status: Optional[str] = None
    remarks: Optional[str] = None

    is_spare_part: bool = False
    parent_pi_number: Optional[str] = None
    computed_status: Optional[str] = None
    order_date: Optional[str] = None

    created_at: datetime
    updated_at: Optional[datetime] = None

    # Relaciones (opcionales, solo en detalle)
    spare_part_lots: List["SparePartLotRead"] = []
    moto_units: List[MotoUnitRead] = []


class ShipmentOrderCreate(BaseModel):
    cycle: Optional[int] = None
    order_date: Optional[str] = None
    pi_number: str
    invoice_number: Optional[str] = None
    model: Optional[str] = None
    model_year: Optional[int] = None
    qty: Optional[str] = None
    containers: Optional[int] = None
    departure_port: Optional[str] = None
    bl_container: Optional[str] = None
    vessel: Optional[str] = None
    etr_raw: Optional[str] = None
    etl_raw: Optional[str] = None
    etd_raw: Optional[str] = None
    eta_raw: Optional[str] = None
    digital_docs_status: Optional[str] = "PENDING"
    original_docs_status: Optional[str] = "PENDING"
    remarks: Optional[str] = None


class ShipmentOrderUpdate(BaseModel):
    cycle: Optional[int] = None
    pi_number: Optional[str] = None
    invoice_number: Optional[str] = None
    model: Optional[str] = None
    model_year: Optional[int] = None
    order_date: Optional[str] = None
    qty: Optional[str] = None
    containers: Optional[int] = None
    departure_port: Optional[str] = None
    bl_container: Optional[str] = None
    vessel: Optional[str] = None
    digital_docs_status: Optional[str] = None
    original_docs_status: Optional[str] = None
    remarks: Optional[str] = None
    computed_status: Optional[str] = None
    etr: Optional[datetime] = None
    etr_raw: Optional[str] = None
    etl: Optional[datetime] = None
    etl_raw: Optional[str] = None
    etd: Optional[datetime] = None
    etd_raw: Optional[str] = None
    eta: Optional[datetime] = None
    eta_raw: Optional[str] = None


class ShipmentOrderListResponse(BaseModel):
    items: List[ShipmentOrderRead]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Spare Part Lots
# ---------------------------------------------------------------------------
class SparePartLotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    shipment_order_id: uuid.UUID
    lot_identifier: str
    detail_loaded: bool
    packing_list_received: bool
    total_declared_value: Optional[float] = None
    currency: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    # Calculados en el endpoint
    items_count: int = 0
    pct_received: float = 0.0


# ---------------------------------------------------------------------------
# Spare Part Items
# ---------------------------------------------------------------------------
class SparePartItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lot_id: uuid.UUID
    part_number: str
    description: Optional[str] = None
    description_es: Optional[str] = None
    model_applicable: Optional[str] = None
    qty_cartons: Optional[int] = None
    qty_ordered: int
    qty_received: int
    qty_pending: Optional[int] = None
    qty_physical: Optional[int] = None
    net_weight_kg: Optional[float] = None
    gross_weight_kg: Optional[float] = None
    cbm: Optional[float] = None
    unit_price: Optional[float] = None
    amount: Optional[float] = None
    status: str
    backorder_pi: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class SparePartItemUpdate(BaseModel):
    part_number: Optional[str] = None
    description: Optional[str] = None
    description_es: Optional[str] = None
    model_applicable: Optional[str] = None
    qty_ordered: Optional[int] = None
    qty_received: Optional[int] = None
    qty_physical: Optional[int] = None
    unit_price: Optional[float] = None
    amount: Optional[float] = None
    status: Optional[str] = None
    backorder_pi: Optional[str] = None
    notes: Optional[str] = None


class ReconciliationResultUpdate(BaseModel):
    part_number: Optional[str] = None
    description_es: Optional[str] = None
    model_applicable: Optional[str] = None
    qty_in_packing: Optional[int] = None
    qty_physical: Optional[int] = None


# ---------------------------------------------------------------------------
# Import Attachments
# ---------------------------------------------------------------------------
class ImportAttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    shipment_order_id: Optional[uuid.UUID] = None
    lot_id: Optional[uuid.UUID] = None
    file_name: str
    file_type: str
    content_type: Optional[str] = None
    uploaded_at: datetime

    # Generada en el endpoint, no viene de la DB
    presigned_url: Optional[str] = None


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------
class ReconciliationResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lot_id: uuid.UUID
    packing_list_id: uuid.UUID
    spare_part_item_id: Optional[uuid.UUID] = None
    part_number: str
    description_es: Optional[str] = None
    model_applicable: Optional[str] = None
    qty_ordered: Optional[int] = None
    qty_in_packing: Optional[int] = None
    qty_physical: Optional[int] = None
    result: str
    confirmed_by: Optional[uuid.UUID] = None
    confirmed_at: Optional[datetime] = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Backorders
# ---------------------------------------------------------------------------
class BackorderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    spare_part_item_id: uuid.UUID
    part_number: str
    description_es: Optional[str] = None
    model_applicable: Optional[str] = None
    origin_pi: str
    expected_in_pi: Optional[str] = None
    qty_pending: int
    resolved: bool
    resolved_at: Optional[datetime] = None
    source: str = 'reconciliation'
    already_charged: bool = False
    history: Optional[Any] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    # Datos del SparePartItem — fuente de verdad para cálculos de cantidad
    sp_qty_ordered: Optional[int] = None
    sp_qty_received: Optional[int] = None
    sp_qty_physical: Optional[int] = None
    sp_qty_pending: Optional[int] = None


class BackorderUpdate(BaseModel):
    expected_in_pi: Optional[str] = None
    qty_pending: Optional[int] = None
    resolved: Optional[bool] = None


class BackorderBulkUpdatePI(BaseModel):
    ids: list[uuid.UUID]
    expected_in_pi: Optional[str] = None


class BackorderBulkRollbackRequest(BaseModel):
    pi_nuevo: str


# ---------------------------------------------------------------------------
# Physical Inspection Upload
# ---------------------------------------------------------------------------
class PhysicalInspectionApplyEntry(BaseModel):
    item_id: uuid.UUID
    qty_physical: int


class PhysicalInspectionApplyPayload(BaseModel):
    items: list[PhysicalInspectionApplyEntry]


# ---------------------------------------------------------------------------
# Import Audit Log
# ---------------------------------------------------------------------------
class ImportAuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_id: Optional[uuid.UUID] = None
    actor_role: Optional[str] = None
    action: str
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    payload: Optional[Any] = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Resultados de importación Excel
# ---------------------------------------------------------------------------
class ImportExcelResult(BaseModel):
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    errors: List[dict] = []


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
class ImportDashboardSummary(BaseModel):
    # Conteos por estado
    total_active: int = 0
    en_preparacion: int = 0
    listo_fabrica: int = 0
    en_transito: int = 0
    en_destino: int = 0
    completado: int = 0
    backorder: int = 0

    # Tipo
    moto_orders: int = 0
    sp_orders: int = 0

    # Documentación
    pending_docs_digital: int = 0
    pending_docs_original: int = 0

    # Backorders
    active_backorders: int = 0
    total_backorder_units: int = 0

    # Valor
    total_declared_value_usd: float = 0.0

    # Series
    by_cycle: List[dict] = []
    upcoming_etas: List[dict] = []
