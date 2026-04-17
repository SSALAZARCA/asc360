import uuid
from sqlalchemy import Column, String, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base

class Vehicle(Base):
    __tablename__ = "vehicles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    
    plate = Column(String(20), unique=True, nullable=False)
    vin = Column(String(50), nullable=True) # Puede conectarse después con VIN_MASTER
    brand = Column(String(100), nullable=False)
    model = Column(String(100), nullable=False)
    year = Column(Integer, nullable=True)
    color = Column(String(50), nullable=True)
    mileage = Column(Integer, default=0)

    tenant = relationship("Tenant", back_populates="vehicles")
    service_orders = relationship("ServiceOrder", back_populates="vehicle", cascade="all, delete-orphan")
    lifecycle_events = relationship("VehicleLifecycleEvent", back_populates="vehicle", cascade="all, delete-orphan", order_by="VehicleLifecycleEvent.event_date")
