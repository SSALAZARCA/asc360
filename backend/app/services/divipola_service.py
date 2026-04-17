"""
Servicio de validación de municipios y departamentos de Colombia según DIVIPOLA.
Lee el JSON estático generado por build_divipola_json.py y expone:
  - validate_ciudad_dpto(ciudad, dpto) -> (ciudad_oficial, dpto_oficial) | raise ValueError
"""
import json
import unicodedata
from pathlib import Path
from functools import lru_cache

DATA_FILE = Path(__file__).parent.parent / "data" / "divipola.json"


def normalize(text: str) -> str:
    """Elimina tildes y convierte a minúsculas para comparación flexible."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(text).strip())
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


@lru_cache(maxsize=1)
def _load_divipola():
    """Carga el JSON DIVIPOLA en memoria (cacheado)."""
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)


def validate_ciudad_dpto(ciudad: str, departamento: str) -> dict:
    """
    Valida que ciudad y departamento existan en el DIVIPOLA.
    Soporta entrada sin tildes (ej: 'Medellin', 'Antioquia').
    
    Returns:
        {"municipio": "MEDELLÍN", "departamento": "ANTIOQUIA"}
    
    Raises:
        ValueError si ciudad o departamento no se encuentran.
    """
    municipios = _load_divipola()
    ciu_norm = normalize(ciudad)
    dpto_norm = normalize(departamento)
    
    # Buscar municipio coincidente
    matches = [
        m for m in municipios
        if m["municipio_norm"] == ciu_norm
    ]
    
    if not matches:
        # Búsqueda parcial (contiene)
        matches = [m for m in municipios if ciu_norm in m["municipio_norm"]]
    
    if not matches:
        raise ValueError(f"Ciudad '{ciudad}' no encontrada en el DIVIPOLA de Colombia.")
    
    # Si hay múltiples coincidencias, filtrar also por departamento
    if len(matches) > 1 and dpto_norm:
        filtered = [m for m in matches if m["departamento_norm"] == dpto_norm]
        if filtered:
            matches = filtered
    
    # Verificar que el departamento coincida
    match = matches[0]
    if dpto_norm and match["departamento_norm"] != dpto_norm:
        raise ValueError(
            f"El municipio '{ciudad}' existe pero no pertenece al departamento '{departamento}'. "
            f"Pertenece a: {match['departamento']}."
        )
    
    return {
        "municipio": match["municipio"],
        "departamento": match["departamento"]
    }


def search_municipios(q: str, limit: int = 8) -> list:
    """
    Búsqueda de municipios por texto parcial (sin tildes).
    Retorna lista de {municipio, departamento}.
    """
    municipios = _load_divipola()
    q_norm = normalize(q)
    
    results = [
        {"municipio": m["municipio"], "departamento": m["departamento"]}
        for m in municipios
        if q_norm in m["municipio_norm"] or q_norm in m["departamento_norm"]
    ]
    return results[:limit]
