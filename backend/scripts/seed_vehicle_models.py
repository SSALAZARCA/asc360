"""
seed_vehicle_models.py
======================
Puebla la tabla vehicle_models leyendo todos los archivos "Specs *.xlsx"
encontrados en SPECS_PATH.

Lógica portada verbatim de cargar_base_datos_specs() del script original
generador_dim_automatico.py (Empadronamientos).

Uso:
    cd backend
    python scripts/seed_vehicle_models.py

Variables de entorno opcionales:
    SPECS_PATH   — ruta a la carpeta con los Excels de specs
                   (default: C:\\proyectos IA\\UM Colombia\\Empadronamientos\\specs)
"""

import asyncio
import glob
import os
import re
import sys
import openpyxl

# Permite importar los módulos de la aplicación
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy.exc import IntegrityError

from app.database import async_session_maker
from app.models.imports import VehicleModel  # noqa: F401 — needed for Base metadata

SPECS_PATH = os.environ.get(
    "SPECS_PATH",
    r"C:\proyectos IA\UM Colombia\Empadronamientos\specs",
)


def cargar_base_datos_specs(specs_path: str) -> dict:
    """
    Portado verbatim de cargar_base_datos_specs() de generador_dim_automatico.py.
    Lee todos los "Specs *.xlsx" del directorio indicado y extrae specs técnicas
    por modelo.

    Retorna:
        dict { model_name_clean (str): spec_data (dict) }

        spec_data keys: CILINDRADA, POTENCIA, PESO, SISTEMA, VUELTAS, CORTINA
    """
    specs_db = {}
    print("Cargando base de datos de especificaciones (Excels)...")

    excel_files = glob.glob(os.path.join(specs_path, "Specs *.xlsx"))

    if not excel_files:
        print(f"  [AVISO] No se encontraron archivos 'Specs *.xlsx' en: {specs_path}")
        return specs_db

    for f in excel_files:
        try:
            fname = os.path.basename(f)
            key = fname.replace("Specs", "").replace(".xlsx", "").strip().upper()
            key_clean = re.sub(r"[^A-Z0-9]", "", key)

            wb = openpyxl.load_workbook(f, data_only=True)
            ws = wb.active

            # Inicializar vacío
            spec_data = {
                "CILINDRADA": "",
                "POTENCIA": "",
                "PESO": "",
                "SISTEMA": "",
                "VUELTAS": "",
                "CORTINA": "",
            }

            keywords_map = {
                "CILINDRADA": "CILINDRADA",
                "DISPLACEMENT": "CILINDRADA",
                "CC": "CILINDRADA",
                "DESPLAZAMIENTO": "CILINDRADA",
                "POTENCIA": "POTENCIA",
                "POWER": "POTENCIA",
                "MAX POWER": "POTENCIA",
                "MAXIMA POTENCIA": "POTENCIA",
                "PESO": "PESO",
                "WEIGHT": "PESO",
                "NET WEIGHT": "PESO",
                "MASA": "PESO",
                "SISTEMA": "SISTEMA",
                "ALIMENTACION": "SISTEMA",
                "FUEL SYSTEM": "SISTEMA",
                "COMBUSTIBLE": "SISTEMA",
                "VUELTAS": "VUELTAS",
                "AIR SCREW": "VUELTAS",
                "TORNILLO": "VUELTAS",
                "VUELTAS DE AIRE": "VUELTAS",
                "CORTINA": "CORTINA",
                "POSICION CORTINA": "CORTINA",
                "AGUJA": "CORTINA",
                "NEEDLE": "CORTINA",
                "CLIP": "CORTINA",
            }

            rows = list(ws.iter_rows(values_only=True))
            for row in rows:
                row_list = list(row)
                for c_idx, cell in enumerate(row_list):
                    if cell is None:
                        continue
                    val_str = str(cell).upper().strip()
                    found_key = None
                    for kw, target in keywords_map.items():
                        if kw == val_str or (len(kw) >= 4 and kw in val_str):
                            found_key = target
                            break

                    if found_key:
                        found_val = None
                        for offset in range(1, 4):
                            if c_idx + offset < len(row_list):
                                cell_val = row_list[c_idx + offset]
                                if cell_val is not None:
                                    v_str = str(cell_val).strip()
                                    if v_str and v_str.upper() not in [":", "=", "-", "N/A"]:
                                        found_val = v_str
                                        break

                        if found_val and not spec_data[found_key]:
                            spec_data[found_key] = found_val

            # Post-procesamiento: defaults para campos obligatorios
            if not spec_data["CILINDRADA"]:
                spec_data["CILINDRADA"] = "N/A"
            if not spec_data["POTENCIA"]:
                spec_data["POTENCIA"] = "N/A"
            if not spec_data["PESO"]:
                spec_data["PESO"] = "N/A"

            # El nombre legible del modelo (antes de clean) se guarda aparte
            # para poder insertarlo como model_name en la DB
            specs_db[key_clean] = {"_raw_name": key, **spec_data}

            print(
                f"  Loaded: {key} -> "
                f"CIL:{spec_data['CILINDRADA']}, "
                f"POT:{spec_data['POTENCIA']}, "
                f"PESO:{spec_data['PESO']}"
            )

        except Exception as e:
            print(f"  Error leyendo {f}: {e}")

    return specs_db


async def seed():
    specs_db = cargar_base_datos_specs(SPECS_PATH)

    if not specs_db:
        print("Nada para insertar.")
        return

    inserted = 0
    skipped = 0

    for key_clean, spec_data in specs_db.items():
        raw_name = spec_data.get("_raw_name", key_clean)

        # Determinar fuel_system a partir de SISTEMA
        sistema = spec_data.get("SISTEMA", "").upper()
        if "INYEC" in sistema or "EFI" in sistema or "INJECTION" in sistema:
            fuel_system = "INYECCION"
        elif sistema:
            fuel_system = sistema
        else:
            fuel_system = "CARBURADOR"

        async with async_session_maker() as session:
            record = VehicleModel(
                model_name=raw_name,
                brand="UM",
                cilindrada=spec_data.get("CILINDRADA") or None,
                potencia=spec_data.get("POTENCIA") or None,
                peso=spec_data.get("PESO") or None,
                vueltas_aire=spec_data.get("VUELTAS") or None,
                posicion_cortina=spec_data.get("CORTINA") or None,
                sistemas_control=None,
                fuel_system=fuel_system,
            )
            session.add(record)
            try:
                await session.commit()
                inserted += 1
            except IntegrityError:
                await session.rollback()
                print(f"  [SKIP] Ya existe: {raw_name}")
                skipped += 1

    print(f"\nResultado: {inserted} insertados, {skipped} saltados.")


if __name__ == "__main__":
    asyncio.run(seed())
