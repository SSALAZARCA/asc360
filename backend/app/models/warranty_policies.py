from sqlalchemy import Column, Integer, String, Enum, Boolean, Date, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
import uuid
import enum
from app.database import Base

class WarrantyTypeEnum(str, enum.Enum):
    MOTOR = "motor"
    GENERAL = "general"
    LIMITED = "limited"

class VehicleLimitedWarranty(Base):
    """
    Lista de componentes de las motos que tienen garantías muy reducidas (Ej: Filtros 30 días, Cableado 180 días).
    Estos registros son transversales a menudo aplican por modelo genérico.
    """
    __tablename__ = "vehicle_limited_warranties"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_code = Column(String(50), nullable=True, comment="A qué modelo aplica. NULL o 'ALL' para referirse a la política universal.")
    component_name = Column(String(100), nullable=False)
    covered_km = Column(Integer, nullable=False, comment="Ej: 1000")
    covered_days = Column(Integer, nullable=False, comment="Ej: 30")
    exclusion_notes = Column(String, nullable=True)

class MandatoryMaintenanceSchedule(Base):
    """
    El listado general de a qué kilómetros tiene que traer un vehículo el cliente 
    para conservar la garantía (Ej: Mantenimiento 1: 500, Mantenimiento 2: 3000).
    """
    __tablename__ = "mandatory_maintenance_schedules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_code = Column(String(50), nullable=True, comment="A qué modelo aplica. NULL o 'ALL' para aplicar a todos")
    maintenance_number = Column(Integer, nullable=False, comment="El índice cronológico. 1, 2, 3...")
    km_target = Column(Integer, nullable=False, comment="Kilometraje esperado para el mantenimiento, Ej: 500")
    tolerance_pre_km = Column(Integer, default=100, comment="Cuántos KM ANTES puede presentarse (Ej 400)")
    tolerance_post_km = Column(Integer, default=200, comment="Cuántos KM DESPUÉS puede presentarse (Ej 700)")
    is_free_labor = Column(Boolean, default=False, comment="True para la revisión de los 500, etc.")
