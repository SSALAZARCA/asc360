"""
Certificate Service — Generador de Certificados Individuales de Aduanas.
Portado verbatim de generador_dim_automatico.py (Empadronamientos).
"""

import os
import re
import base64
import io
import datetime

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML as WeasyHTML

STATIC_DIR = os.path.join(os.path.dirname(__file__), "../static/empadronamiento")
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "../html_templates")

# ---------------------------------------------------------------------------
# Diccionario de traducción de colores (portado verbatim)
# ---------------------------------------------------------------------------
DICT_COLORES = {
    'RED': 'ROJO',
    'BLUE': 'AZUL',
    'BLACK': 'NEGRO',
    'WHITE': 'BLANCO',
    'GREY': 'GRIS',
    'GRAY': 'GRIS',
    'GREEN': 'VERDE',
    'YELLOW': 'AMARILLO',
    'ORANGE': 'NARANJA',
    'MATTE': 'MATE',
    'MATT': 'MATE',
    'GLOSSY': 'BRILLANTE',
    'SILVER': 'PLATA',
    'BROWN': 'CAFÉ',
    'GOLD': 'DORADO',
}


def traducir_color(color_ingles: str) -> str:
    if not color_ingles:
        return ""
    c = str(color_ingles).upper().strip()

    # Traducción directa
    for eng, esp in DICT_COLORES.items():
        c = c.replace(eng, esp)

    # Ajuste gramatical: "MATE NEGRO" -> "NEGRO MATE"
    # Solo si empieza con MATE o BRILLANTE y tiene mas palabras
    parts = c.split()
    if len(parts) > 1:
        if parts[0] in ['MATE', 'BRILLANTE']:
            modifier = parts.pop(0)
            parts.append(modifier)
            c = " ".join(parts)

    return c


def get_image_base64(path: str) -> str:
    if path and os.path.exists(path):
        with open(path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    return ""


def process_signature_base64(path: str) -> str:
    try:
        from PIL import Image
        img = Image.open(path).convert("RGBA")
        datas = img.getdata()
        newData = []
        for item in datas:
            # Hacer transparente lo blanco (umbral 200)
            if item[0] > 200 and item[1] > 200 and item[2] > 200:
                newData.append((255, 255, 255, 0))
            else:
                newData.append(item)
        img.putdata(newData)
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode('utf-8')
    except ImportError:
        return get_image_base64(path)
    except Exception:
        return get_image_base64(path)


def generate_qr(data: str) -> str:
    import qrcode
    qr = qrcode.QRCode(version=1, box_size=10, border=1)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode('utf-8')


def encontrar_specs_para_modelo(vehicle_models: list, modelo_str: str) -> dict:
    """
    Fuzzy match — portado de encontrar_specs_para_modelo() de generador_dim_automatico.py.
    vehicle_models: lista de objetos VehicleModel ORM.
    modelo_str: string del modelo tal como viene del DIM o de la orden.
    Returns dict con keys: cilindrada, potencia, peso, vueltas_aire, posicion_cortina, sistemas_control, fuel_system
    """
    defaults = {
        'cilindrada': 'N/A',
        'potencia': 'N/A',
        'peso': 'N/A',
        'vueltas_aire': 'N/A',
        'posicion_cortina': 'N/A',
        'sistemas_control': 'CATALIZADOR / CANISTER',
        'fuel_system': 'CARBURADOR',
    }

    if not vehicle_models or not modelo_str:
        return defaults

    # 1. Limpieza básica del modelo a buscar
    modelo_clean = re.sub(r'[^A-Z0-9]', '', modelo_str).upper()

    # Construir dict {model_name_clean: obj} para búsqueda
    specs_db = {re.sub(r'[^A-Z0-9]', '', m.model_name).upper(): m for m in vehicle_models}

    # 2. Intento exacto
    if modelo_clean in specs_db:
        obj = specs_db[modelo_clean]
        return {
            'cilindrada': obj.cilindrada or 'N/A',
            'potencia': obj.potencia or 'N/A',
            'peso': obj.peso or 'N/A',
            'vueltas_aire': obj.vueltas_aire or 'N/A',
            'posicion_cortina': obj.posicion_cortina or 'N/A',
            'sistemas_control': obj.sistemas_control or 'CATALIZADOR / CANISTER',
            'fuel_system': obj.fuel_system or 'CARBURADOR',
        }

    # 3. Intento fuzzy (palabras clave)
    tokens_dim = set(re.sub(r'[^A-Z0-9]', ' ', modelo_str).upper().split())
    tokens_dim = {
        t for t in tokens_dim
        if len(t) > 2 and t not in ['MOTOCICLETA', 'VEHICULO', 'CLASE', 'UM', 'UNITED', 'MOTORS']
    }

    mejores_candidatos = []
    for key_spec, obj in specs_db.items():
        matches = sum(1 for token in tokens_dim if token in key_spec)
        if matches > 0:
            mejores_candidatos.append((matches, key_spec, obj))

    if mejores_candidatos:
        mejores_candidatos.sort(key=lambda x: (x[0], len(x[1])), reverse=True)
        obj = mejores_candidatos[0][2]
        return {
            'cilindrada': obj.cilindrada or 'N/A',
            'potencia': obj.potencia or 'N/A',
            'peso': obj.peso or 'N/A',
            'vueltas_aire': obj.vueltas_aire or 'N/A',
            'posicion_cortina': obj.posicion_cortina or 'N/A',
            'sistemas_control': obj.sistemas_control or 'CATALIZADOR / CANISTER',
            'fuel_system': obj.fuel_system or 'CARBURADOR',
        }

    return defaults


def generate_certificado_bytes(unit, order, vehicle_model) -> bytes:
    """
    Genera el PDF del certificado individual de aduanas para una unidad.

    Args:
        unit: ShipmentMotoUnit ORM object
        order: ShipmentOrder ORM object
        vehicle_model: VehicleModel ORM object o None

    Returns:
        bytes del PDF generado
    """
    # 1. Traducir color
    color_es = traducir_color(unit.color or "")

    # 2. Obtener specs del vehicle_model o usar defaults
    if vehicle_model:
        specs = {
            'cilindrada': vehicle_model.cilindrada or 'N/A',
            'potencia': vehicle_model.potencia or 'N/A',
            'peso': vehicle_model.peso or 'N/A',
            'vueltas': vehicle_model.vueltas_aire or 'N/A',
            'cortina': vehicle_model.posicion_cortina or 'N/A',
            'sistemas': vehicle_model.sistemas_control or 'CATALIZADOR / CANISTER',
            'fuel_system': vehicle_model.fuel_system or 'CARBURADOR',
        }
    else:
        specs = {
            'cilindrada': 'N/A',
            'potencia': 'N/A',
            'peso': 'N/A',
            'vueltas': 'N/A',
            'cortina': 'N/A',
            'sistemas': 'CATALIZADOR / CANISTER',
            'fuel_system': 'CARBURADOR',
        }

    # Si tiene sistema de inyección, ajustar vueltas/cortina
    fuel_upper = specs['fuel_system'].upper()
    if 'INYEC' in fuel_upper or 'EFI' in fuel_upper:
        specs['vueltas'] = 'N/A'
        specs['cortina'] = 'INYECCIÓN'

    # 3. Cargar assets estáticos como base64
    logo_b64 = get_image_base64(os.path.join(STATIC_DIR, "logo.png"))
    firma_b64 = process_signature_base64(os.path.join(STATIC_DIR, "firma.png"))

    # 4. Generar QR
    today = datetime.date.today().strftime("%Y-%m-%d")
    modelo_str = order.model or ''
    qr_data = f"MOTORCOM|{unit.vin_number}|{unit.engine_number}|{modelo_str}|{today}|VALIDO"
    qr_b64 = generate_qr(qr_data)

    # 5. Renderizar template Jinja2
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
    template = env.get_template("certificado_individual.html")

    html_content = template.render(
        vin=unit.vin_number or '',
        motor=unit.engine_number or '',
        color=color_es,
        modelo=modelo_str,
        marca='UNITED MOTORS (UM)',
        anio=unit.model_year or order.model_year or 2026,
        cilindrada=specs['cilindrada'],
        potencia=specs['potencia'],
        peso=specs['peso'],
        vueltas=specs['vueltas'],
        cortina=specs['cortina'],
        sistemas=specs['sistemas'],
        no_acep=unit.no_acep or 'PENDIENTE',
        f_acep=str(unit.f_acep) if unit.f_acep else today,
        no_lev=unit.no_lev or 'PENDIENTE',
        f_lev=str(unit.f_lev) if unit.f_lev else today,
        logo_b64=logo_b64,
        firma_b64=firma_b64,
        qr_b64=qr_b64,
        today=today,
    )

    # 6. WeasyPrint → PDF bytes
    pdf_bytes = WeasyHTML(string=html_content).write_pdf()
    return pdf_bytes
