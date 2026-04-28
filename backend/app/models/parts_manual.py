import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Numeric, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.database import Base


class PartsReference(Base):
    """Catálogo único de partes — cada factory_part_number aparece una sola vez."""
    __tablename__ = "parts_references"

    factory_part_number   = Column(String(100), primary_key=True)
    um_part_number        = Column(String(100), nullable=False, index=True)
    description           = Column(String(255), nullable=False)
    unit                  = Column(String(20),  nullable=True)
    prev_codes            = Column(JSONB, nullable=False, server_default='[]')
    description_es_manual = Column(String(500), nullable=True)

    # Costo FOB promedio ponderado — recalculado en cada carga de pedido
    avg_fob_cost      = Column(Numeric(12, 4), nullable=True)
    total_fob_qty     = Column(Integer, nullable=True)
    last_cost_updated = Column(DateTime, nullable=True)

    items = relationship("PartsManualItem", back_populates="reference")
    cost_history = relationship("PartCostHistory", back_populates="reference", cascade="all, delete-orphan")


class PartsManualSection(Base):
    __tablename__ = "parts_manual_sections"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_code   = Column(String(100), nullable=False, index=True)
    section_code = Column(String(20),  nullable=False)
    section_name = Column(String(255), nullable=False)
    diagram_url  = Column(String(500), nullable=True)
    created_at   = Column(DateTime, default=datetime.utcnow)

    items = relationship("PartsManualItem", back_populates="section", cascade="all, delete-orphan")


class PartsManualItem(Base):
    __tablename__ = "parts_manual_items"

    id                  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    section_id          = Column(UUID(as_uuid=True), ForeignKey("parts_manual_sections.id"), nullable=False)
    order_num           = Column(String(20), nullable=False)
    factory_part_number = Column(String(100), ForeignKey("parts_references.factory_part_number"), nullable=False)

    section   = relationship("PartsManualSection", back_populates="items")
    reference = relationship("PartsReference", back_populates="items")


class VehicleCatalogMap(Base):
    """Mapea vehicle.model → catalog_model_code."""
    __tablename__ = "vehicle_catalog_map"

    vehicle_model_pattern = Column(String(200), primary_key=True)
    catalog_model_code    = Column(String(100), nullable=False, index=True)


class PartCostHistory(Base):
    """Auditoría inmutable de cada actualización de costo FOB por lote."""
    __tablename__ = "part_cost_history"

    id                  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    factory_part_number = Column(String(100), ForeignKey("parts_references.factory_part_number", ondelete="CASCADE"), nullable=False, index=True)
    lot_identifier      = Column(String(100), nullable=False)
    part_number_used    = Column(String(100), nullable=False)
    unit_price          = Column(Numeric(12, 4), nullable=False)
    qty                 = Column(Integer, nullable=False)
    recorded_at         = Column(DateTime, nullable=False, default=datetime.utcnow)

    reference = relationship("PartsReference", back_populates="cost_history")


class PartsCodeReviewTask(Base):
    """Tarea de verificación cuando un nuevo pedido trae un código diferente para la misma parte."""
    __tablename__ = "parts_code_review_tasks"

    id                   = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    existing_code        = Column(String(100), nullable=False, index=True)
    candidate_code       = Column(String(100), nullable=False, index=True)
    existing_description = Column(String(500), nullable=True)
    candidate_description = Column(String(500), nullable=True)
    similarity_score     = Column(Numeric(5, 4), nullable=True)
    status               = Column(String(20), nullable=False, default="pending", index=True)
    created_at           = Column(DateTime, default=datetime.utcnow)
    resolved_at          = Column(DateTime, nullable=True)
    resolved_by          = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
