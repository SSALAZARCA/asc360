import uuid
from sqlalchemy import Column, String, Integer, Numeric, Date, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.database import Base

class VinMaster(Base):
    __tablename__ = "vin_master"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vin = Column(String(50), unique=True, nullable=False)
    engine_number = Column(String(50), nullable=True)
    model_code = Column(String(50), nullable=False)
    model_name = Column(String(100), nullable=False)
    
    year = Column(Integer, nullable=True)
    color = Column(String(50))
    assembly_date = Column(Date)
    
    # --- Parámetros de Garantía Individual (Desde Packing List) ---
    garantia_motor_km = Column(Integer, default=50000, comment="Kilómetros de cobertura para el motor")
    garantia_motor_meses = Column(Integer, default=60, comment="Meses de cobertura para el motor")
    garantia_general_km = Column(Integer, default=3000, comment="Kilómetros de cobertura general")
    garantia_general_meses = Column(Integer, default=36, comment="Meses de cobertura general")
    
    # Parámetros de garantía
    warranty_months = Column(Integer, default=12)
    warranty_km = Column(Integer, default=12000)
    
    # [1000, 5000, 10000]
    km_reviews = Column(JSONB, default=[])
    # Listado de índices cronológicos de revisiones que son pagadas por la marca (mantenimientos gratuitos para cliente)
    km_reviews_free = Column(JSONB, default=[1, 2, 4])
    
    pdi_value = Column(Numeric(10, 2), default=0.0)
    
    # Valores a pagar al centro de servicio por concepto de mano de obra de rutinas preventivas
    review_values = Column(JSONB, default={"1": 25000.0, "2": 25000.0, "4": 25000.0})
    
    warranty_hour_rate = Column(Numeric(10, 2), default=0.0)
