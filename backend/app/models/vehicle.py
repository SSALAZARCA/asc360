import uuid
from sqlalchemy import Column, String, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base

class Vehicle(Base):
    """
    NOTE (`sdd/vehicle-tenant-checkin-release`): `tenant_id` is intentionally
    NOT mapped here. A vehicle's tenant association is a temporary, derived
    claim scoped to its currently open `ServiceOrder` -- never permanent
    ownership -- so it is computed on read (see
    `app/repositories/vehicle_repository.py`'s `visible_to_tenant`/
    `get_open_claim`), not stored on this model. The physical
    `vehicles.tenant_id` column still exists in Postgres (now nullable,
    see migration `c6d7e8f9a0b1`) for rollback safety; it is scheduled for
    a physical `DROP COLUMN` in a later release once one deploy cycle has
    passed clean. Any code that still tries to read/write
    `Vehicle.tenant_id` or `Vehicle.tenant` will fail loudly
    (AttributeError/TypeError) rather than silently reading/writing a
    stale value -- that fail-loud behavior is deliberate.
    """
    __tablename__ = "vehicles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    plate = Column(String(20), unique=True, nullable=False)
    vin = Column(String(50), nullable=True) # Puede conectarse después con VIN_MASTER
    brand = Column(String(100), nullable=False)
    model = Column(String(100), nullable=False)
    year = Column(Integer, nullable=True)
    color = Column(String(50), nullable=True)
    mileage = Column(Integer, default=0)

    service_orders = relationship("ServiceOrder", back_populates="vehicle", cascade="all, delete-orphan")
    lifecycle_events = relationship("VehicleLifecycleEvent", back_populates="vehicle", cascade="all, delete-orphan", order_by="VehicleLifecycleEvent.event_date")
