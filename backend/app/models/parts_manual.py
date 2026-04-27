import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.database import Base


class PartsReference(Base):
    """Catálogo único de partes — cada factory_part_number aparece una sola vez."""
    __tablename__ = "parts_references"

    factory_part_number = Column(String(100), primary_key=True)
    um_part_number      = Column(String(100), nullable=False, index=True)
    description         = Column(String(255), nullable=False)
    unit                = Column(String(20),  nullable=True)
    prev_codes          = Column(JSONB, nullable=False, server_default='[]')

    items = relationship("PartsManualItem", back_populates="reference")


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
