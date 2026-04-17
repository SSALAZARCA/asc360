import uuid
import enum
from sqlalchemy import Column, String, Integer, Enum, ForeignKey, Numeric, DateTime, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime

from app.database import Base

class PartCatalog(Base):
    __tablename__ = "part_catalog"

    part_code = Column(String(100), primary_key=True)
    description = Column(String(255), nullable=False)
    public_price = Column(Numeric(12, 2), nullable=False)
    is_wear_part = Column(Boolean, default=False)
    
    # Podría agregar stock base o categoría

class PartsOrderStatus(enum.Enum):
    draft = "draft"
    pending_approval = "pending_approval"
    approved = "approved"
    rejected = "rejected"
    sent_to_softway = "sent_to_softway"

class PartsOrder(Base):
    __tablename__ = "parts_orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False) # Repuestero
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    status = Column(Enum(PartsOrderStatus), default=PartsOrderStatus.draft, nullable=False)
    total_amount = Column(Numeric(15, 2), default=0.0)
    softway_ref = Column(String(100), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    submitted_at = Column(DateTime, nullable=True)

    tenant = relationship("Tenant", back_populates="parts_orders")
    creator = relationship("User", back_populates="created_parts_orders")
    items = relationship("PartsOrderItem", back_populates="order", cascade="all, delete-orphan")

class PartsOrderItem(Base):
    __tablename__ = "parts_order_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parts_order_id = Column(UUID(as_uuid=True), ForeignKey("parts_orders.id"), nullable=False)
    part_code = Column(String(100), ForeignKey("part_catalog.part_code"), nullable=False)
    
    quantity = Column(Integer, nullable=False, default=1)
    unit_price = Column(Numeric(12, 2), nullable=False)
    subtotal = Column(Numeric(12, 2), nullable=False)

    order = relationship("PartsOrder", back_populates="items")
    catalog_item = relationship("PartCatalog")

class PurchaseOrderStatus(enum.Enum):
    draft = "draft"
    sent_to_supplier = "sent_to_supplier"
    in_production = "in_production"
    ready_factory = "ready_factory"
    at_port = "at_port"
    in_transit = "in_transit"
    at_customs = "at_customs"
    received = "received"
    partial_received = "partial_received"

class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_number = Column(String(100), unique=True, nullable=False)
    status = Column(Enum(PurchaseOrderStatus), default=PurchaseOrderStatus.draft, nullable=False)
    
    requested_date = Column(DateTime, default=datetime.utcnow)
    estimated_arrival = Column(DateTime, nullable=True)
    supplier_name = Column(String(255), nullable=True)
    container_number = Column(String(100), nullable=True)
    
    tracking_data = Column(JSONB, default=[]) # Historico "timeline"

    items = relationship("PurchaseOrderItem", back_populates="order", cascade="all, delete-orphan")

class PurchaseOrderItemStatus(enum.Enum):
    pending = "pending"
    received = "received"
    backorder = "backorder"

class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    purchase_order_id = Column(UUID(as_uuid=True), ForeignKey("purchase_orders.id"), nullable=False)
    part_code = Column(String(100), ForeignKey("part_catalog.part_code"), nullable=False)
    
    requested_quantity = Column(Integer, nullable=False)
    received_quantity = Column(Integer, default=0)
    unit_cost = Column(Numeric(12, 2), nullable=True)
    status = Column(Enum(PurchaseOrderItemStatus), default=PurchaseOrderItemStatus.pending)

    order = relationship("PurchaseOrder", back_populates="items")
    catalog_item = relationship("PartCatalog")
