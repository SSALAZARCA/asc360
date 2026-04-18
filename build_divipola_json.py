"""
Script de preprocesamiento: lee DIVIPOLA_Municipios.xlsx y genera divipola.json
con municipios normalizados (sin tildes, en minúsculas) para búsqueda fuzzy rápida.

Uso:
    python build_divipola_json.py
"""
import json
import unicodedata
import pandas as pd
from pathlib import Path

EXCEL_PATH = Path(__file__).parent / "DIVIPOLA_Municipios.xlsx"
OUTPUT_PATH = Path(__file__).parent / "backend" / "app" / "data" / "divipola.json"

def normalize(text: str) -> str:
    """Elimina tildes y pasa a minúsculas para comparación flexible."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(text).strip())
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()

def build_json():
    print("📖 Leyendo DIVIPOLA...")
    df = pd.read_excel(EXCEL_PATH, dtype=str)
    
    # Columnas importantes
    col_dpto = "Nombre Departamento"
    col_mun  = "Municipio"
    
    # Verificar columnas
    if col_dpto not in df.columns or col_mun not in df.columns:
        print(f"❌ Columnas no encontradas. Disponibles: {list(df.columns)}")
        return
    
    # Construir estructura: {municipio_normalizado: {municipio_oficial, dpto_oficial, dpto_normalizado}}
    municipios = []
    for _, row in df.iterrows():
        dpto = str(row[col_dpto]).strip()
        mun  = str(row[col_mun]).strip()
        if dpto and mun and dpto != "nan" and mun != "nan":
            municipios.append({
                "municipio": mun,
                "municipio_norm": normalize(mun),
                "departamento": dpto,
                "departamento_norm": normalize(dpto),
            })
    
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(municipios, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Generado: {OUTPUT_PATH}")
    print(f"   Total municipios: {len(municipios)}")
    print(f"   Departamentos únicos: {len(set(m['departamento'] for m in municipios))}")

if __name__ == "__main__":
    build_json()
