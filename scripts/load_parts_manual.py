#!/usr/bin/env python3
"""
Carga el manual de partes desde PDFs a PostgreSQL + MinIO.

Uso (dentro del contenedor backend, o localmente con las env vars configuradas):
    python scripts/load_parts_manual.py \
        --pdf-dir "Renegade 200 Sport" \
        --model-code "renegade_200_sport" \
        --vehicle-model "Renegade Sport 200S"

Variables de entorno requeridas:
    DATABASE_URL        ej: postgresql+asyncpg://user:pass@host:5432/db
    MINIO_ENDPOINT      ej: minio:9000
    MINIO_ACCESS_KEY
    MINIO_SECRET_KEY
    MINIO_SECURE        "true" | "false"  (default: false)
"""

import argparse
import asyncio
import io
import json
import os
import re
import sys
import uuid
from pathlib import Path

try:
    import asyncpg
    import fitz          # PyMuPDF
    import pdfplumber
    from minio import Minio
except ImportError as e:
    print(f"❌ Dependencia faltante: {e}")
    print("   Instalá: pip install asyncpg PyMuPDF pdfplumber minio")
    sys.exit(1)

BUCKET_DEFAULT = "parts-manuals"


# ---------------------------------------------------------------------------
# Renderizado de imagen
# ---------------------------------------------------------------------------

def render_page_png(pdf_path: Path, dpi: int = 150) -> bytes:
    doc = fitz.open(str(pdf_path))
    page = doc[0]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)
    return pix.tobytes("png")


# ---------------------------------------------------------------------------
# MinIO
# ---------------------------------------------------------------------------

def _minio_url(client: Minio, bucket: str, object_name: str) -> str:
    base = client._base_url
    scheme = "https" if getattr(base, "is_https", False) else "http"
    host = getattr(base, "host", str(base))
    port = getattr(base, "port", None)
    if port and port not in (80, 443):
        return f"{scheme}://{host}:{port}/{bucket}/{object_name}"
    return f"{scheme}://{host}/{bucket}/{object_name}"


def upload_png(client: Minio, bucket: str, object_name: str, png_bytes: bytes) -> str:
    client.put_object(
        bucket_name=bucket,
        object_name=object_name,
        data=io.BytesIO(png_bytes),
        length=len(png_bytes),
        content_type="image/png",
    )
    return _minio_url(client, bucket, object_name)


def ensure_bucket_public(client: Minio, bucket: str) -> None:
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
    policy = json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": "*",
            "Action": "s3:GetObject",
            "Resource": f"arn:aws:s3:::{bucket}/*",
        }]
    })
    client.set_bucket_policy(bucket, policy)


# ---------------------------------------------------------------------------
# Parseo de tabla de repuestos
# ---------------------------------------------------------------------------

HEADER_KEYWORDS = {
    "order_num":   ["page", "no.", "no ", "item", "pos"],
    "factory":     ["factory", "part no", "part num"],
    "um":          ["um part", "um no"],
    "description": ["description", "descrip"],
    "unit":        ["unit"],
}


def _detect_col(header_row: list, keywords: list) -> int:
    for i, cell in enumerate(header_row):
        if cell is None:
            continue
        cell_lower = str(cell).lower().strip()
        for kw in keywords:
            if kw in cell_lower:
                return i
    return -1


def parse_parts_table(pdf_path: Path) -> list[dict]:
    parts = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                if not table or len(table) < 2:
                    continue

                header_idx = -1
                col_map: dict[str, int] = {}

                for row_i, row in enumerate(table):
                    if not row:
                        continue
                    row_lower = [str(c).lower() if c else "" for c in row]
                    hits = 0
                    for kw_list in HEADER_KEYWORDS.values():
                        for kw in kw_list:
                            if any(kw in cell for cell in row_lower):
                                hits += 1
                                break
                    if hits >= 3:
                        header_idx = row_i
                        for field, kws in HEADER_KEYWORDS.items():
                            col_map[field] = _detect_col(row, kws)
                        break

                if header_idx < 0 or not col_map:
                    continue

                for row in table[header_idx + 1:]:
                    if not row:
                        continue

                    def get(field: str) -> str | None:
                        idx = col_map.get(field, -1)
                        if idx < 0 or idx >= len(row):
                            return None
                        v = row[idx]
                        return str(v).strip() if v is not None else None

                    order_num = get("order_num")
                    factory   = get("factory")

                    if not order_num or not factory:
                        continue
                    if order_num.lower() in ("page", "no.", "no", "item", "pos", ""):
                        continue

                    parts.append({
                        "order_num":           order_num,
                        "factory_part_number": factory,
                        "um_part_number":      get("um") or "",
                        "description":         get("description") or "",
                        "unit":                get("unit"),
                    })
    return parts


# ---------------------------------------------------------------------------
# Nombre de sección desde el nombre del archivo
# ---------------------------------------------------------------------------

def parse_filename(filename: str) -> tuple[str, str]:
    """
    'B01_BODY COMP FRAME_FLOOR STEP.pdf'
    → ('B01', 'BODY COMP FRAME / FLOOR STEP')
    """
    stem = Path(filename).stem
    parts = stem.split("_", 1)
    code = parts[0].strip()
    name = parts[1].replace("_", " / ").strip() if len(parts) > 1 else stem
    return code, name


# ---------------------------------------------------------------------------
# Loader principal
# ---------------------------------------------------------------------------

async def load(pdf_dir: str, model_code: str, vehicle_model: str, bucket: str):
    db_url = os.environ["DATABASE_URL"]
    db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    db_url = db_url.replace("postgres+asyncpg://",   "postgres://")

    minio_endpoint = os.environ["MINIO_ENDPOINT"]
    minio_access   = os.environ["MINIO_ACCESS_KEY"]
    minio_secret   = os.environ["MINIO_SECRET_KEY"]
    minio_secure   = os.environ.get("MINIO_SECURE", "false").lower() == "true"

    minio_client = Minio(
        minio_endpoint,
        access_key=minio_access,
        secret_key=minio_secret,
        secure=minio_secure,
    )
    ensure_bucket_public(minio_client, bucket)
    print(f"✅ Bucket '{bucket}' listo (público)\n")

    conn = await asyncpg.connect(db_url)

    pdf_files = sorted(Path(pdf_dir).glob("*.pdf"))
    if not pdf_files:
        print(f"❌ No se encontraron PDFs en '{pdf_dir}'")
        await conn.close()
        return

    print(f"📂 {len(pdf_files)} PDFs — modelo '{model_code}'\n")

    for pdf_path in pdf_files:
        section_code, section_name = parse_filename(pdf_path.name)
        print(f"→ [{section_code}] {section_name}")

        # 1. Renderizar y subir imagen
        diagram_url = None
        try:
            png_bytes = render_page_png(pdf_path)
            object_name = f"{model_code}/{section_code}.png"
            diagram_url = upload_png(minio_client, bucket, object_name, png_bytes)
            print(f"   📸 {diagram_url}")
        except Exception as e:
            print(f"   ⚠️  Imagen: {e}")

        # 2. Parsear tabla
        try:
            parts = parse_parts_table(pdf_path)
            print(f"   📋 {len(parts)} repuestos")
        except Exception as e:
            print(f"   ⚠️  Tabla: {e}")
            parts = []

        # 3. Eliminar sección anterior y reinsertar
        await conn.execute(
            "DELETE FROM parts_manual_sections WHERE model_code=$1 AND section_code=$2",
            model_code, section_code,
        )

        section_id = str(uuid.uuid4())
        await conn.execute(
            """
            INSERT INTO parts_manual_sections
                (id, model_code, section_code, section_name, diagram_url)
            VALUES ($1, $2, $3, $4, $5)
            """,
            section_id, model_code, section_code, section_name, diagram_url,
        )

        # 4. Upsert referencias únicas + insertar posiciones en diagrama
        for p in parts:
            factory = p["factory_part_number"]
            if not factory:
                continue

            # Upsert en parts_references (ON CONFLICT DO NOTHING — primera ocurrencia gana)
            await conn.execute(
                """
                INSERT INTO parts_references
                    (factory_part_number, um_part_number, description, unit)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (factory_part_number) DO NOTHING
                """,
                factory,
                p["um_part_number"],
                p["description"],
                p["unit"],
            )

            # Posición en el diagrama
            await conn.execute(
                """
                INSERT INTO parts_manual_items
                    (id, section_id, order_num, factory_part_number)
                VALUES ($1, $2, $3, $4)
                """,
                str(uuid.uuid4()),
                section_id,
                p["order_num"],
                factory,
            )

        print(f"   ✅ Listo\n")

    # 5. Upsert mapa de catálogo
    await conn.execute(
        """
        INSERT INTO vehicle_catalog_map (vehicle_model_pattern, catalog_model_code)
        VALUES ($1, $2)
        ON CONFLICT (vehicle_model_pattern) DO UPDATE SET catalog_model_code = $2
        """,
        vehicle_model, model_code,
    )
    print(f"✅ Mapa actualizado: '{vehicle_model}' → '{model_code}'")

    await conn.close()
    print("\n🎉 Carga completada.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Carga PDFs del manual de partes al sistema.")
    parser.add_argument("--pdf-dir",        required=True, help="Directorio con los PDFs")
    parser.add_argument("--model-code",     required=True, help="Código interno del modelo (ej: renegade_200_sport)")
    parser.add_argument("--vehicle-model",  required=True, help="Valor exacto de vehicle.model en la base de datos")
    parser.add_argument("--bucket",         default=BUCKET_DEFAULT, help=f"Bucket MinIO (default: {BUCKET_DEFAULT})")
    args = parser.parse_args()

    asyncio.run(load(args.pdf_dir, args.model_code, args.vehicle_model, args.bucket))
