import uuid
import enum
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, Date, Text, Numeric,
    ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.database import Base


# ---------------------------------------------------------------------------
# Shipment Orders — una fila por PI_NUMBER + MODEL
# ---------------------------------------------------------------------------
class ShipmentOrder(Base):
    __tablename__ = "shipment_orders"
    __table_args__ = (
        UniqueConstraint("pi_number", "model", name="uq_shipment_pi_model"),
        Index("ix_shipment_cycle", "cycle"),
        Index("ix_shipment_is_spare", "is_spare_part"),
        Index("ix_shipment_status", "computed_status"),
        Index("ix_shipment_parent_pi", "parent_pi_number"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cycle = Column(Integer, nullable=True)
    pi_number = Column(String(100), nullable=False)
    invoice_number = Column(String(100), nullable=True)
    model = Column(String(255), nullable=False)
    model_year = Column(Integer, nullable=True)

    # QTY como string porque puede ser "1 LOT"; qty_numeric es el valor numérico si aplica
    qty = Column(String(50), nullable=True)
    qty_numeric = Column(Integer, nullable=True)
    total_units = Column(Integer, nullable=True)
    containers = Column(Integer, nullable=True)

    # Fechas duales: DateTime para cálculos, _raw para valores como "PENDING" / "READY"
    etr = Column(DateTime, nullable=True)
    etr_raw = Column(String(50), nullable=True)
    etl = Column(DateTime, nullable=True)
    etl_raw = Column(String(50), nullable=True)
    etd = Column(DateTime, nullable=True)
    etd_raw = Column(String(50), nullable=True)
    eta = Column(DateTime, nullable=True)
    eta_raw = Column(String(50), nullable=True)

    departure_port = Column(String(100), nullable=True)
    bl_container = Column(String(255), nullable=True)
    vessel = Column(String(255), nullable=True)
    digital_docs_status = Column(String(50), nullable=True, default="PENDING")
    original_docs_status = Column(String(50), nullable=True, default="PENDING")
    remarks = Column(Text, nullable=True)

    is_spare_part = Column(Boolean, default=False, nullable=False)
    # Para SP: "E0000573-SP-1" → parent_pi_number = "E0000573"
    parent_pi_number = Column(String(100), nullable=True)

    # Estado materializado: recalculado en cada importación
    computed_status = Column(String(50), nullable=True, default="en_preparacion")
    order_date = Column(Date, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relaciones
    spare_part_lots = relationship("SparePartLot", back_populates="shipment_order", cascade="all, delete-orphan")
    moto_units = relationship("ShipmentMotoUnit", back_populates="shipment_order", cascade="all, delete-orphan")
    attachments = relationship("ImportAttachment", back_populates="shipment_order", cascade="all, delete-orphan")
    audit_logs = relationship("ImportAuditLog", back_populates="shipment_order")


# ---------------------------------------------------------------------------
# Shipment Moto Units — VINs individuales por pedido
# ---------------------------------------------------------------------------
class ShipmentMotoUnit(Base):
    __tablename__ = "shipment_moto_units"
    __table_args__ = (
        Index("ix_moto_unit_vin", "vin_number"),
        Index("ix_moto_unit_order", "shipment_order_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    shipment_order_id = Column(UUID(as_uuid=True), ForeignKey("shipment_orders.id"), nullable=False)

    item_no = Column(Integer, nullable=True)           # Número de línea en el packing list
    vin_number = Column(String(100), nullable=True)    # Número de chasis (VIN)
    engine_number = Column(String(100), nullable=True)
    color = Column(String(100), nullable=True)
    model = Column(String(255), nullable=True)          # Modelo propio de la unidad (sobreescribe el del pedido)
    model_year = Column(Integer, nullable=True)        # Año modelo de la moto
    container_no = Column(String(100), nullable=True)
    seal_no = Column(String(100), nullable=True)
    source_pi = Column(String(50), nullable=True)      # PI del que proviene este VIN

    # Datos de aduana (DIM)
    no_acep = Column(String(100), nullable=True)
    f_acep = Column(Date, nullable=True)
    no_lev = Column(String(100), nullable=True)
    f_lev = Column(Date, nullable=True)

    # Control de certificado
    certificado_generado = Column(Boolean, nullable=False, default=False)
    certificado_fecha = Column(DateTime, nullable=True)

    # Seguimiento: empadronamiento físico enviado al distribuidor
    empadronamiento_fisico_enviado = Column(Boolean, nullable=False, default=False)
    empadronamiento_fisico_fecha = Column(DateTime, nullable=True)

    # DIM PDF original subido a MinIO
    dim_pdf_object_name = Column(String(500), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    shipment_order = relationship("ShipmentOrder", back_populates="moto_units")


# ---------------------------------------------------------------------------
# Spare Part Lots — lotes de repuestos vinculados a un pedido
# ---------------------------------------------------------------------------
class SparePartLot(Base):
    __tablename__ = "spare_part_lots"
    __table_args__ = (
        Index("ix_spl_shipment_order", "shipment_order_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    shipment_order_id = Column(UUID(as_uuid=True), ForeignKey("shipment_orders.id"), nullable=False)
    lot_identifier = Column(String(100), nullable=False, unique=True)  # PI_NUMBER del SP, ej: E0000573-SP

    detail_loaded = Column(Boolean, default=False, nullable=False)
    packing_list_received = Column(Boolean, default=False, nullable=False)

    # Totales declarados del invoice
    total_declared_value = Column(Numeric(14, 2), nullable=True)
    currency = Column(String(10), nullable=True, default="USD")

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relaciones
    shipment_order = relationship("ShipmentOrder", back_populates="spare_part_lots")
    items = relationship("SparePartItem", back_populates="lot", cascade="all, delete-orphan")
    packing_lists = relationship("PackingList", back_populates="lot", cascade="all, delete-orphan")
    reconciliation_results = relationship("ReconciliationResult", back_populates="lot")
    attachments = relationship("ImportAttachment", back_populates="lot")


# ---------------------------------------------------------------------------
# Spare Part Items — items individuales de un lote
# ---------------------------------------------------------------------------
class SparePartItem(Base):
    __tablename__ = "spare_part_items"
    __table_args__ = (
        Index("ix_spi_lot", "lot_id"),
        Index("ix_spi_part_number", "part_number"),
        Index("ix_spi_status", "status"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lot_id = Column(UUID(as_uuid=True), ForeignKey("spare_part_lots.id"), nullable=False)

    # part_number siempre normalizado: strip().upper().replace(" ", "")
    part_number = Column(String(100), nullable=False)
    description = Column(String(500), nullable=True)        # Descripción en inglés
    description_es = Column(String(500), nullable=True)     # Descripción en español
    model_applicable = Column(String(255), nullable=True)   # Modelo de moto al que aplica

    # Cantidades (del packing list)
    qty_cartons = Column(Integer, nullable=True)
    qty_ordered = Column(Integer, nullable=False, default=0)
    qty_received = Column(Integer, nullable=False, default=0)
    qty_pending = Column(Integer, nullable=True)  # Calculado: qty_ordered - qty_received

    # Datos físicos (del packing list)
    net_weight_kg = Column(Numeric(10, 2), nullable=True)
    gross_weight_kg = Column(Numeric(10, 2), nullable=True)
    cbm = Column(Numeric(10, 4), nullable=True)

    # Precio (del invoice)
    unit_price = Column(Numeric(12, 2), nullable=True)
    amount = Column(Numeric(12, 2), nullable=True)  # unit_price × qty_ordered

    status = Column(String(50), nullable=False, default="PENDING")  # PENDING/PARTIAL/RECEIVED/BACKORDER
    backorder_pi = Column(String(100), nullable=True)   # PI futuro donde se espera si está en backorder
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relaciones
    lot = relationship("SparePartLot", back_populates="items")
    backorders = relationship("Backorder", back_populates="spare_part_item")
    reconciliation_results = relationship("ReconciliationResult", back_populates="spare_part_item")


# ---------------------------------------------------------------------------
# Packing Lists — metadato de archivos subidos
# ---------------------------------------------------------------------------
class PackingList(Base):
    __tablename__ = "packing_lists"
    __table_args__ = (
        Index("ix_pl_lot", "lot_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lot_id = Column(UUID(as_uuid=True), ForeignKey("spare_part_lots.id"), nullable=False)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    file_name = Column(String(500), nullable=False)
    minio_object_name = Column(String(1000), nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    processed = Column(Boolean, default=False, nullable=False)

    # Relaciones
    lot = relationship("SparePartLot", back_populates="packing_lists")
    items = relationship("PackingListItem", back_populates="packing_list", cascade="all, delete-orphan")
    reconciliation_results = relationship("ReconciliationResult", back_populates="packing_list")


# ---------------------------------------------------------------------------
# Packing List Items — items individuales del packing list subido
# ---------------------------------------------------------------------------
class PackingListItem(Base):
    __tablename__ = "packing_list_items"
    __table_args__ = (
        Index("ix_pli_packing_list", "packing_list_id"),
        Index("ix_pli_part_number", "part_number"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    packing_list_id = Column(UUID(as_uuid=True), ForeignKey("packing_lists.id"), nullable=False)

    # part_number siempre normalizado
    part_number = Column(String(100), nullable=False)
    description = Column(String(500), nullable=True)
    model = Column(String(255), nullable=True)
    qty = Column(Integer, nullable=False, default=0)
    unit_price = Column(Numeric(12, 2), nullable=True)
    notes = Column(Text, nullable=True)

    packing_list = relationship("PackingList", back_populates="items")


# ---------------------------------------------------------------------------
# Reconciliation Results — resultado del cruce packing list vs pedido
# ---------------------------------------------------------------------------
class ReconciliationResult(Base):
    __tablename__ = "reconciliation_results"
    __table_args__ = (
        Index("ix_rr_lot", "lot_id"),
        Index("ix_rr_packing_list", "packing_list_id"),
        Index("ix_rr_result", "result"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lot_id = Column(UUID(as_uuid=True), ForeignKey("spare_part_lots.id"), nullable=False)
    packing_list_id = Column(UUID(as_uuid=True), ForeignKey("packing_lists.id"), nullable=False)
    spare_part_item_id = Column(UUID(as_uuid=True), ForeignKey("spare_part_items.id"), nullable=True)  # NULL para EXTRA

    part_number = Column(String(100), nullable=False)  # Desnormalizado para consulta rápida
    qty_ordered = Column(Integer, nullable=True)
    qty_in_packing = Column(Integer, nullable=True)
    result = Column(String(20), nullable=False)  # COMPLETE / PARTIAL / MISSING / EXTRA

    confirmed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    confirmed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relaciones
    lot = relationship("SparePartLot", back_populates="reconciliation_results")
    packing_list = relationship("PackingList", back_populates="reconciliation_results")
    spare_part_item = relationship("SparePartItem", back_populates="reconciliation_results")


# ---------------------------------------------------------------------------
# Backorders — items pendientes con trazabilidad entre ciclos
# ---------------------------------------------------------------------------
class Backorder(Base):
    __tablename__ = "backorders"
    __table_args__ = (
        Index("ix_bo_part_number", "part_number"),
        Index("ix_bo_status", "resolved"),
        Index("ix_bo_origin_pi", "origin_pi"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    spare_part_item_id = Column(UUID(as_uuid=True), ForeignKey("spare_part_items.id"), nullable=False)

    # Desnormalizado para consultas rápidas sin joins
    part_number = Column(String(100), nullable=False)
    origin_pi = Column(String(100), nullable=False)      # PI donde faltó el ítem
    expected_in_pi = Column(String(100), nullable=True)  # PI futuro donde se espera

    qty_pending = Column(Integer, nullable=False)
    resolved = Column(Boolean, default=False, nullable=False)
    resolved_at = Column(DateTime, nullable=True)

    # Historial de movimientos: [{date, event, qty, pi}]
    history = Column(JSONB, nullable=True, default=list)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    spare_part_item = relationship("SparePartItem", back_populates="backorders")


# ---------------------------------------------------------------------------
# Import Attachments — archivos adjuntos (BL, facturas, etc.)
# ---------------------------------------------------------------------------
class ImportAttachment(Base):
    __tablename__ = "import_attachments"
    __table_args__ = (
        Index("ix_ia_shipment_order", "shipment_order_id"),
        Index("ix_ia_lot", "lot_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    shipment_order_id = Column(UUID(as_uuid=True), ForeignKey("shipment_orders.id"), nullable=True)
    lot_id = Column(UUID(as_uuid=True), ForeignKey("spare_part_lots.id"), nullable=True)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    file_name = Column(String(500), nullable=False)
    # Categoría: PACKING_LIST / BL / COMMERCIAL_INVOICE / CERT_ORIGIN / OTHER
    file_type = Column(String(50), nullable=False, default="OTHER")
    minio_object_name = Column(String(1000), nullable=False)
    content_type = Column(String(100), nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    shipment_order = relationship("ShipmentOrder", back_populates="attachments")
    lot = relationship("SparePartLot", back_populates="attachments")


# ---------------------------------------------------------------------------
# Import Audit Log — registro inmutable de acciones
# ---------------------------------------------------------------------------
class ImportAuditLog(Base):
    __tablename__ = "import_audit_log"
    __table_args__ = (
        Index("ix_ial_entity", "entity_type", "entity_id"),
        Index("ix_ial_created_at", "created_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    shipment_order_id = Column(UUID(as_uuid=True), ForeignKey("shipment_orders.id"), nullable=True)

    actor_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    actor_role = Column(String(50), nullable=True)
    action = Column(String(100), nullable=False)       # IMPORT_EXCEL / UPDATE_STATUS / etc.
    entity_type = Column(String(50), nullable=True)    # ShipmentOrder / SparePartLot / etc.
    entity_id = Column(String(100), nullable=True)

    # Snapshot del cambio: {"field": {"old": X, "new": Y}} o resumen de la importación
    payload = Column(JSONB, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    shipment_order = relationship("ShipmentOrder", back_populates="audit_logs")


# ---------------------------------------------------------------------------
# Vehicle Models — especificaciones técnicas por modelo de motocicleta
# ---------------------------------------------------------------------------
class VehicleModel(Base):
    __tablename__ = "vehicle_models"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_name = Column(String(255), nullable=False, unique=True)
    brand = Column(String(100), nullable=False, default="UM")
    cilindrada = Column(String(100), nullable=True)
    potencia = Column(String(100), nullable=True)
    peso = Column(String(100), nullable=True)
    vueltas_aire = Column(String(100), nullable=True)
    posicion_cortina = Column(String(100), nullable=True)
    sistemas_control = Column(String(500), nullable=True)
    fuel_system = Column(String(50), nullable=True, default="CARBURADOR")
    largo_total = Column(String(50), nullable=True)
    ancho_total = Column(String(50), nullable=True)
    altura_total = Column(String(50), nullable=True)
    altura_silla = Column(String(50), nullable=True)
    distancia_suelo = Column(String(50), nullable=True)
    distancia_ejes = Column(String(50), nullable=True)
    tanque_combustible = Column(String(50), nullable=True)
    relacion_compresion = Column(String(50), nullable=True)
    llanta_delantera = Column(String(100), nullable=True)
    llanta_trasera = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
