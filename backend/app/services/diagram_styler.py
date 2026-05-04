"""
Genera una card visual estilizada para cada sección del catálogo de partes.
Recibe los bytes de la ilustración extraída del PDF y la lista de partes
ya parseada, devuelve PNG bytes listos para subir a MinIO.
"""
import io
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

# ── Rutas de fuentes ──────────────────────────────────────────────────────────
_FONT_CANDIDATES = {
    "regular": [
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        str(Path(__file__).parent.parent / "static" / "fonts" / "LiberationSans-Regular.ttf"),
    ],
    "bold": [
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        str(Path(__file__).parent.parent / "static" / "fonts" / "LiberationSans-Bold.ttf"),
    ],
}

# ── Design tokens ─────────────────────────────────────────────────────────────
BG          = (10,  15,  30)
BG_CARD     = (17,  24,  39)
BG_ROW_ALT  = (13,  19,  36)
ORANGE      = (255, 95,  51)
ORANGE_DIM  = (180, 62,  30)
GREEN       = (16,  185, 129)
WHITE       = (255, 255, 255)
GRAY        = (160, 160, 176)
GRAY_DIM    = (80,  88,  110)
DIVIDER     = (30,  40,  65)

CARD_W      = 1080
PAD         = 44
MAX_ROWS    = 12


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    key = "bold" if bold else "regular"
    for path in _FONT_CANDIDATES[key]:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _remove_white_bg(img: Image.Image, threshold: int = 230) -> Image.Image:
    img = img.convert("RGBA")
    pixels = img.load()
    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = pixels[x, y]
            if r > threshold and g > threshold and b > threshold:
                pixels[x, y] = (r, g, b, 0)
    return img


def create_diagram_card(
    illus_bytes: bytes,
    section_code: str,
    section_name: str,
    model_name: str,
    parts: list[dict],
    logo_bytes: Optional[bytes] = None,
) -> bytes:
    """
    Compone la card estilizada y devuelve los bytes PNG.

    Args:
        illus_bytes: JPEG/PNG de la ilustración extraída del PDF.
        section_code: Ej. "B1".
        section_name: Ej. "FRAME".
        model_name:   Ej. "RENEGADE 200 SPORT".
        parts:        Lista de dicts con keys order_num, factory_part_number, description.
        logo_bytes:   PNG del logo de marca (fondo blanco — se eliminará).
    """
    # ── Ilustración ───────────────────────────────────────────────────────────
    illus = Image.open(io.BytesIO(illus_bytes)).convert("RGB")
    target_w = CARD_W - PAD * 2
    scale    = target_w / illus.width
    illus    = illus.resize((int(illus.width * scale), int(illus.height * scale)), Image.LANCZOS)
    illus_w, illus_h = illus.size

    # ── Alturas ───────────────────────────────────────────────────────────────
    HEADER_H  = 104
    ILLUS_PAD = 32
    ILLUS_BLOCK = illus_h + ILLUS_PAD * 2 + 28

    visible_rows = min(len(parts), MAX_ROWS)
    ROW_H      = 40
    TH_H       = 46
    TBL_PAD_V  = 20
    TABLE_H    = TH_H + ROW_H * visible_rows + TBL_PAD_V * 2 + (18 if len(parts) > MAX_ROWS else 0)
    FOOTER_H   = 58

    CARD_H = HEADER_H + ILLUS_BLOCK + 8 + TABLE_H + FOOTER_H

    # ── Canvas ────────────────────────────────────────────────────────────────
    card = Image.new("RGB", (CARD_W, CARD_H), BG)
    draw = ImageDraw.Draw(card)

    # Dot pattern
    for gy in range(0, CARD_H, 28):
        for gx in range(0, CARD_W, 28):
            draw.ellipse([gx, gy, gx + 1, gy + 1], fill=(20, 28, 50))

    # ── 1. HEADER ─────────────────────────────────────────────────────────────
    draw.rectangle([0, 0, CARD_W, HEADER_H], fill=BG_CARD)
    draw.rectangle([0, 0, 5, HEADER_H], fill=ORANGE)
    draw.rectangle([0, HEADER_H - 1, CARD_W, HEADER_H], fill=DIVIDER)

    logo_end_x = PAD + 10
    if logo_bytes:
        try:
            logo = Image.open(io.BytesIO(logo_bytes))
            logo = _remove_white_bg(logo)
            lh   = 58
            lw   = int(lh * logo.width / logo.height)
            logo = logo.resize((lw, lh), Image.LANCZOS)
            ly   = (HEADER_H - lh) // 2
            card.paste(logo, (PAD + 10, ly), logo)
            logo_end_x = PAD + 10 + lw
        except Exception:
            pass

    # Badge de sección
    font_pill  = _font(18, bold=True)
    pill_bbox  = draw.textbbox((0, 0), section_code, font=font_pill)
    pill_w     = pill_bbox[2] - pill_bbox[0] + 22
    pill_h     = 30
    pill_x     = logo_end_x + 24
    pill_y     = (HEADER_H - pill_h) // 2
    draw.rounded_rectangle([pill_x, pill_y, pill_x + pill_w, pill_y + pill_h], radius=6, fill=ORANGE)
    draw.text((pill_x + 11, pill_y + 6), section_code, font=font_pill, fill=WHITE)

    # Nombre de sección
    font_sec   = _font(28, bold=True)
    sec_x      = pill_x + pill_w + 16
    sec_y      = (HEADER_H - 30) // 2 + 2
    draw.text((sec_x, sec_y), section_name, font=font_sec, fill=WHITE)

    # Label derecha
    font_lbl   = _font(16)
    rtext      = "CATALOGO DE PARTES"
    rb         = draw.textbbox((0, 0), rtext, font=font_lbl)
    draw.text((CARD_W - PAD - (rb[2] - rb[0]), (HEADER_H - 18) // 2 + 2), rtext,
              font=font_lbl, fill=GRAY_DIM)

    # ── 2. ILUSTRACIÓN ────────────────────────────────────────────────────────
    y_illus_block = HEADER_H
    y_illus_inner = y_illus_block + ILLUS_PAD + 28

    # Glow naranja radial
    cx = CARD_W // 2
    cy = y_illus_inner + illus_h // 2
    for i in range(18, 0, -1):
        ratio = i / 18
        sx = int((illus_w // 2 + 60) * ratio)
        sy = int((illus_h // 2 + 40) * ratio)
        col = (
            max(BG[0], int(255 * ratio * 0.35)),
            max(BG[1], int(95  * ratio * 0.35)),
            max(BG[2], int(51  * ratio * 0.35)),
        )
        draw.ellipse([cx - sx, cy - sy, cx + sx, cy + sy], fill=col)

    # Tag "VISTA DE DESPIECE"
    font_tag  = _font(13)
    tag_text  = "VISTA DE DESPIECE"
    tb        = draw.textbbox((0, 0), tag_text, font=font_tag)
    tpw       = tb[2] - tb[0] + 20
    tag_y     = y_illus_block + 14
    draw.rounded_rectangle([PAD, tag_y, PAD + tpw, tag_y + 22], radius=4, fill=DIVIDER)
    draw.text((PAD + 10, tag_y + 4), tag_text, font=font_tag, fill=GRAY)

    # Card de ilustración: sombra → borde naranja → fondo blanco
    draw.rounded_rectangle(
        [PAD + 8 - 2, y_illus_inner + 8 - 2, PAD + illus_w + 8 + 2, y_illus_inner + illus_h + 8 + 2],
        radius=12, fill=(5, 8, 18),
    )
    draw.rounded_rectangle(
        [PAD - 2, y_illus_inner - 2, PAD + illus_w + 2, y_illus_inner + illus_h + 2],
        radius=12, fill=ORANGE_DIM,
    )
    draw.rounded_rectangle(
        [PAD, y_illus_inner, PAD + illus_w, y_illus_inner + illus_h],
        radius=10, fill=(252, 252, 252),
    )
    card.paste(illus, (PAD, y_illus_inner))

    # ── 3. DIVISOR ────────────────────────────────────────────────────────────
    y_div = y_illus_inner + illus_h + ILLUS_PAD
    draw.rectangle([0, y_div, CARD_W, y_div + 1], fill=DIVIDER)

    # ── 4. TABLA DE PARTES ────────────────────────────────────────────────────
    y_table  = y_div + 1
    col1_w   = 90
    col2_w   = 310
    col3_w   = CARD_W - PAD * 2 - col1_w - col2_w
    col_x    = [PAD + 14, PAD + col1_w, PAD + col1_w + col2_w]

    font_th  = _font(14, bold=True)
    font_tr  = _font(14)
    font_sm  = _font(13)

    th_y = y_table + TBL_PAD_V
    draw.rectangle([0, th_y, CARD_W, th_y + TH_H], fill=BG_CARD)
    draw.rectangle([PAD - 1, th_y, PAD + 3, th_y + TH_H], fill=ORANGE)

    for i, (hdr, cx_h) in enumerate(zip(["No.", "CODIGO DE FABRICA", "DESCRIPCION"], col_x)):
        draw.text((cx_h, th_y + (TH_H - 15) // 2 + 2), hdr,
                  font=font_th, fill=ORANGE if i == 0 else GRAY)

    draw.rectangle([PAD, th_y + TH_H, CARD_W - PAD, th_y + TH_H + 1], fill=ORANGE_DIM)

    for idx, part in enumerate(parts[:MAX_ROWS]):
        row_y  = th_y + TH_H + 1 + idx * ROW_H
        row_bg = BG_CARD if idx % 2 == 0 else BG_ROW_ALT
        draw.rectangle([0, row_y, CARD_W, row_y + ROW_H], fill=row_bg)
        draw.rectangle([PAD - 1, row_y, PAD + 2, row_y + ROW_H], fill=DIVIDER)

        ty = row_y + (ROW_H - 15) // 2 + 2
        no_text  = part.get("order_num", "")
        fac_text = part.get("factory_part_number", "")
        desc     = part.get("description", "")

        nb   = draw.textbbox((0, 0), no_text, font=font_th)
        nw   = nb[2] - nb[0]
        draw.text((col_x[0] + (col1_w - 14 - nw) // 2, ty), no_text, font=font_th, fill=GREEN)
        draw.text((col_x[1], ty), fac_text, font=font_tr, fill=GRAY)
        draw.text((col_x[2], ty), desc,     font=font_sm, fill=WHITE)

    bot_y = th_y + TH_H + 1 + visible_rows * ROW_H
    draw.rectangle([PAD, bot_y, CARD_W - PAD, bot_y + 1], fill=DIVIDER)

    if len(parts) > MAX_ROWS:
        extra_text = f"... y {len(parts) - MAX_ROWS} partes mas"
        et_b = draw.textbbox((0, 0), extra_text, font=font_sm)
        draw.text((CARD_W // 2 - (et_b[2] - et_b[0]) // 2, bot_y + 6),
                  extra_text, font=font_sm, fill=GRAY_DIM)

    # ── 5. FOOTER ─────────────────────────────────────────────────────────────
    y_footer = CARD_H - FOOTER_H
    draw.rectangle([0, y_footer, CARD_W, CARD_H], fill=BG_CARD)
    draw.rectangle([0, y_footer, CARD_W, y_footer + 1], fill=DIVIDER)

    font_fb = _font(17, bold=True)
    font_fl = _font(15)
    fy      = y_footer + (FOOTER_H - 18) // 2 + 2

    draw.text((PAD, fy), model_name, font=font_fb, fill=GRAY)

    right_label = "Manual de Partes"
    rb2 = draw.textbbox((0, 0), right_label, font=font_fl)
    draw.text((CARD_W - PAD - (rb2[2] - rb2[0]), fy), right_label, font=font_fl, fill=ORANGE)

    # ── Exportar ──────────────────────────────────────────────────────────────
    buf = io.BytesIO()
    card.save(buf, "PNG", optimize=True)
    return buf.getvalue()
