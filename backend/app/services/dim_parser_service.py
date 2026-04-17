"""
DIM Parser Service
Portado verbatim de generador_dim_automatico.py (Empadronamientos).
Extrae VINs y datos de aduana (no_acep, f_acep, no_lev, f_lev) de un PDF de Declaración de Importación de Mercancías.
"""

import re
import datetime
import io

import pdfplumber


def limpiar_texto_continuidad(texto_pagina: str) -> str:
    txt = re.sub(r'\u000C', ' ', texto_pagina)
    txt = re.sub(r'\(continúa al respaldo\)', ' ', txt)
    if "105. Continuación descripción mercancías" in txt:
        marcador = "105. Continuación descripción mercancías"
        idx = txt.find(marcador)
        if idx != -1:
            idx_eol = txt.find('\n', idx)
            if idx_eol != -1:
                txt = txt[idx_eol + 1:]
    # Unir palabras cortadas por saltos de línea:
    # Si una línea termina con letras y la siguiente empieza con letras,
    # es probable que sea una palabra cortada. Unimos sin espacio.
    # Ej: "REFERENCI\nA:" -> "REFERENCIA:"
    txt = re.sub(r'([A-Za-z])\s*\n\s*([A-Za-z])', r'\1\2', txt)
    # Normalizar todos los espacios múltiples en uno
    txt = re.sub(r'\s+', ' ', txt)
    return txt


def buscar_vins_en_bloque(texto_bloque: str) -> list:
    texto_norm = re.sub(r'\s+', ' ', texto_bloque)
    possible_vins = []

    # 1. Regex específica (SD5...)
    for m in re.finditer(r'(SD[A-Z0-9\s]{14,30})', texto_norm):
        raw = m.group(1)
        clean = re.sub(r'[^A-Z0-9]', '', raw)
        if len(clean) >= 17:
            vin_c = clean[:17]
            if vin_c not in possible_vins:
                possible_vins.append(vin_c)

    # 2. Búsqueda genérica
    if not possible_vins:
        raw_words = texto_norm.replace(',', ' ').split()
        for w in raw_words:
            w_clean = re.sub(r'[^A-Z0-9]', '', w)
            if len(w_clean) == 17 and (w_clean.startswith('S') or w_clean.startswith('L')):
                possible_vins.append(w_clean)

    return possible_vins


def parse_dim_pdf(file_bytes: bytes) -> list:
    """
    Extrae datos de aduana y VINs de un PDF de Declaración de Importación (DIM).

    Returns:
        Lista de dicts: [{vin, no_acep, f_acep, no_lev, f_lev}, ...]
        - f_acep y f_lev son strings en formato YYYY-MM-DD

    Raises:
        ValueError: Si el PDF no contiene texto digital (escaneado) o no se encontraron VINs.
    """
    vehiculos = []
    formularios = {}

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        last_form_num = None
        has_text = False

        for i, page in enumerate(pdf.pages):
            txt = page.extract_text() or ""
            if len(txt.strip()) > 50:
                has_text = True

            m_form = re.search(r'(?:formulario|Aceptación).*?(\d{13,16}[\d-]*)', txt, re.IGNORECASE)
            current_form_num = "DESCONOCIDO"
            if m_form:
                current_form_num = m_form.group(1).strip()
            else:
                m_solo_num = re.search(r'\b(\d{13,16}[\d-]*)\b', txt[:500])
                if m_solo_num:
                    current_form_num = m_solo_num.group(1).strip()

            if current_form_num == "DESCONOCIDO" and last_form_num:
                current_form_num = last_form_num
            key = current_form_num[:15]

            txt_limpio = limpiar_texto_continuidad(txt)
            if key not in formularios:
                formularios[key] = ""
            formularios[key] += " " + txt_limpio
            last_form_num = current_form_num

    if not has_text:
        raise ValueError(
            "El PDF no contiene texto digital legible. "
            "El archivo cargado es una FOTO o un documento ESCANEADO. "
            "Pida a la agencia de aduanas el PDF DIGITAL ORIGINAL descargado de la plataforma, "
            "que no esté impreso ni escaneado."
        )

    for key_form, full_text in formularios.items():
        full_text_norm = re.sub(r'\s+', ' ', full_text)

        # --- no_acep ---
        m_acep = re.search(r'No\.\s*Aceptación.*?(\d{10,20})', full_text_norm)
        no_acep = m_acep.group(1) if m_acep else key_form

        # --- f_acep (campo 133) ---
        m_f_acep = re.search(
            r'(?:133\.|Aceptaci[oó]n).*?Fe[hc]*ha.*?\s*(\d{4}\s*[-/]?\s*\d{2}\s*[-/]?\s*\d{2})',
            full_text_norm, re.IGNORECASE
        )
        if not m_f_acep:
            # Fallback genérico para Aceptación
            m_f_acep = re.search(
                r'Aceptaci[oó]n.*?(\d{4}\s*[-/]?\s*\d{2}\s*[-/]?\s*\d{2})',
                full_text_norm, re.IGNORECASE
            )

        if m_f_acep:
            c = re.sub(r'[^0-9]', '', m_f_acep.group(1))
            f_acep = f"{c[:4]}-{c[4:6]}-{c[6:8]}"
        else:
            f_acep = datetime.date.today().strftime("%Y-%m-%d")

        # --- no_lev ---
        m_lev = re.search(r'Levante\s*No\.\s*(\d{10,20})', full_text_norm, re.IGNORECASE)
        no_lev = m_lev.group(1) if m_lev else "PENDIENTE"

        # --- f_lev (campo 135) ---
        m_f_lev = re.search(
            r'(?:135\s*\.|Fecha\s*Firma).{0,100}?(\d{4}\s*[-/]?\s*\d{2}\s*[-/]?\s*\d{2})',
            full_text_norm, re.IGNORECASE
        )
        if not m_f_lev:
            # Fallback a Levante...Fecha
            m_f_lev = re.search(
                r'Levante.{0,100}?Fe[hc]*ha.{0,100}?(\d{4}\s*[-/]?\s*\d{2}\s*[-/]?\s*\d{2})',
                full_text_norm, re.IGNORECASE
            )

        if m_f_lev:
            c = re.sub(r'[^0-9]', '', m_f_lev.group(1))
            f_lev = f"{c[:4]}-{c[4:6]}-{c[6:8]}"
        else:
            f_lev = datetime.date.today().strftime("%Y-%m-%d")

        # --- Partir en bloques por ITEM ---
        partes = re.split(r'(\([Ii][Tt][Ee][Mm]\s*\d+\))', full_text_norm)
        bloques = []
        curr = ""
        for p in partes:
            if re.match(r'\([Ii][Tt][Ee][Mm]\s*\d+\)', p):
                if curr:
                    bloques.append(curr)
                curr = p
            else:
                curr += " " + p
        if curr:
            bloques.append(curr)

        # Filtrar bloques relevantes
        bloques = [b for b in bloques if "ITEM" in b.upper() or "PRODUCTO" in b.upper() or "MOTOCICLETA" in b.upper()]

        for bloque in bloques:
            vins_found = buscar_vins_en_bloque(bloque)

            # Fallback simple
            if len(vins_found) == 0:
                match_vin_zone = re.search(
                    r'(?:VIN|CHASIS).*?:(.*?)(?:NUMERO SERIAL MOTOR|MOTOR)',
                    bloque, re.IGNORECASE
                )
                if match_vin_zone:
                    raws = match_vin_zone.group(1).split(',')
                    vins_found = [r.strip() for r in raws if len(r.strip()) > 10]

            for vin in vins_found:
                vehiculos.append({
                    'vin': vin,
                    'no_acep': no_acep,
                    'f_acep': f_acep,
                    'no_lev': no_lev,
                    'f_lev': f_lev,
                })

    if not vehiculos:
        raise ValueError(
            "No se encontraron VINs en el documento. "
            "Verifique que el PDF sea una Declaración de Importación de Mercancías (DIM) válida."
        )

    return vehiculos
