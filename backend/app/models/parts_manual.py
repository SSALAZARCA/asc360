import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class PartsManualSection(Base):
    __tablename__ = "parts_manual_sections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_code = Column(String(100), nullable=False, index=True)
    section_code = Column(String(20), nullable=False)
    section_name = Column(String(255), nullable=False)
    diagram_url = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    items = relationship("PartsManualItem", back_populates="section", cascade="all, delete-orphan")


class PartsManualItem(Base):
    __tablename__ = "parts_manual_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    section_id = Column(UUID(as_uuid=True), ForeignKey("parts_manual_sections.id"), nullable=False)

    order_num = Column(String(20), nullable=False)
    factory_part_number = Column(String(100), nullable=False, index=True)
    um_part_number = Column(String(100), nullable=False, index=True)
    description = Column(String(255), nullable=False)
    unit = Column(String(20), nullable=True)
    qty = Column(Integer, nullable=True)

    section = relationship("PartsManualSection", back_populates="items")


class VehicleCatalogMap(Base):
    """Mapea el campo vehicle.model a un catalog model_code."""
    __tablename__ = "vehicle_catalog_map"

    vehicle_model_pattern = Column(String(200), primary_key=True)
    catalog_model_code = Column(String(100), nullable=False, index=True)
