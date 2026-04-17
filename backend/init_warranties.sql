-- Migración manual de BBDD para Garantías (Saltando Alembic)

-- 1. Agregar columnas a vin_master (si no existen)
ALTER TABLE vin_master
ADD COLUMN IF NOT EXISTS garantia_motor_km INTEGER DEFAULT 50000,
ADD COLUMN IF NOT EXISTS garantia_motor_meses INTEGER DEFAULT 60,
ADD COLUMN IF NOT EXISTS garantia_general_km INTEGER DEFAULT 3000,
ADD COLUMN IF NOT EXISTS garantia_general_meses INTEGER DEFAULT 36;

COMMENT ON COLUMN vin_master.garantia_motor_km IS 'Kilómetros de cobertura para el motor';
COMMENT ON COLUMN vin_master.garantia_motor_meses IS 'Meses de cobertura para el motor';
COMMENT ON COLUMN vin_master.garantia_general_km IS 'Kilómetros de cobertura general';
COMMENT ON COLUMN vin_master.garantia_general_meses IS 'Meses de cobertura general';

-- 2. Crear tabla vehicle_limited_warranties
CREATE TABLE IF NOT EXISTS vehicle_limited_warranties (
    id UUID PRIMARY KEY,
    model_code VARCHAR(50),
    component_name VARCHAR(100) NOT NULL,
    covered_km INTEGER NOT NULL,
    covered_days INTEGER NOT NULL,
    exclusion_notes VARCHAR
);

COMMENT ON COLUMN vehicle_limited_warranties.model_code IS 'A qué modelo aplica. NULL o ALL para referirse a la política universal.';
COMMENT ON COLUMN vehicle_limited_warranties.covered_km IS 'Ej: 1000';
COMMENT ON COLUMN vehicle_limited_warranties.covered_days IS 'Ej: 30';

-- 3. Crear tabla mandatory_maintenance_schedules
CREATE TABLE IF NOT EXISTS mandatory_maintenance_schedules (
    id UUID PRIMARY KEY,
    model_code VARCHAR(50),
    maintenance_number INTEGER NOT NULL,
    km_target INTEGER NOT NULL,
    tolerance_pre_km INTEGER DEFAULT 100,
    tolerance_post_km INTEGER DEFAULT 200,
    is_free_labor BOOLEAN DEFAULT FALSE
);

COMMENT ON COLUMN mandatory_maintenance_schedules.model_code IS 'A qué modelo aplica. NULL o ALL para aplicar a todos';
COMMENT ON COLUMN mandatory_maintenance_schedules.maintenance_number IS 'El índice cronológico. 1, 2, 3...';
COMMENT ON COLUMN mandatory_maintenance_schedules.km_target IS 'Kilometraje esperado para la revisión, Ej: 500';
COMMENT ON COLUMN mandatory_maintenance_schedules.tolerance_pre_km IS 'Cuántos KM ANTES puede presentarse (Ej 400)';
COMMENT ON COLUMN mandatory_maintenance_schedules.tolerance_post_km IS 'Cuántos KM DESPUÉS puede presentarse (Ej 700)';
COMMENT ON COLUMN mandatory_maintenance_schedules.is_free_labor IS 'True para la revisión de los 500, etc.';
