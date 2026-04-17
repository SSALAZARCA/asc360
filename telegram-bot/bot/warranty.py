import os
import httpx
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000/api/v1")

async def get_review_schedules() -> List[Dict]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            res = await client.get(f"{BACKEND_URL}/warranty-policies/mandatory-maintenances")
            if res.status_code == 200:
                return res.json()
        except Exception as e:
            logger.error(f"Error HTTP fetching review schedules: {e}")
    return []

async def get_limited_warranties() -> List[Dict]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            res = await client.get(f"{BACKEND_URL}/warranty-policies/limited-warranties")
            if res.status_code == 200:
                return res.json()
        except Exception as e:
            logger.error(f"Error HTTP fetching limited warranties: {e}")
    return []

def evaluate_maintenance_compliance(current_km: float, schedules: List[Dict]) -> str:
    """
    Evalúa si el cliente está asistiendo dentro de las tolerancias legales de mantenimiento.
    Genera un 'Soft Warning' explícito si se salió del rango.
    """
    if not schedules:
        return ""
        
    schedules = sorted(schedules, key=lambda x: x['km_target'])
    warnings = []
    
    # Encontrar la revisión aplicable más cercana (ej. 500, 3000, 5000)
    for sched in schedules:
        target = sched['km_target']
        tol_pre = sched['tolerance_pre_km']
        tol_post = sched['tolerance_post_km']
        
        min_km = target - tol_pre
        max_km = target + tol_post
        
        # Si está cerca de este target, evaluamos status
        if current_km <= target + (tol_post * 2) or current_km >= target - (tol_pre * 2):
            if current_km < min_km:
                warnings.append(f"⚠️ El vehículo ({current_km}km) ha asistido prematuramente a la revisión de {target}km.")
            elif current_km > max_km:
                warnings.append(f"⚠️ El vehículo ({current_km}km) ha excedido el periodo de gracia (+{tol_post}km) para la revisión de {target}km.")
            else:
                return f"✅ Revisión en rango óptimo para los {target}km."
            break # Evaluamos únicamente la revisión actual cercana
            
    return "\n".join(warnings) if warnings else ""

async def generate_soft_warnings(current_km: float, vehicle_data: dict, motives: List[str]) -> str:
    schedules = await get_review_schedules()
    # Para el MVP evaluaremos los limitados como un feature adicional futuro en texto.
    
    warnings_text = ""
    # Evaluamos mantenimientos
    maintenance_status = evaluate_maintenance_compliance(current_km, schedules)
    if maintenance_status:
        warnings_text += maintenance_status + "\n"
        
    # Extra: Si vehicle_data tiene fechas de vencimiento de la Garantía Motor / General, acá las comparamos.
    if vehicle_data:
        garantia_motor = vehicle_data.get('garantia_motor_km')
        garantia_general = vehicle_data.get('garantia_general_km')
        if garantia_motor and current_km > garantia_motor:
            warnings_text += f"\n⚠️ Garantía de Motor Expirada por Kilometraje (Límite: {garantia_motor}km)."
        if garantia_general and current_km > garantia_general:
            warnings_text += f"\n⚠️ Garantía General Expirada por Kilometraje (Límite: {garantia_general}km)."
            
    return warnings_text.strip()
