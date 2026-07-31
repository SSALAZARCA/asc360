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
ORANGE      = (255, 95,  51)
ORANGE_DIM  = (180, 62,  30)
WHITE       = (255, 255, 255)
GRAY        = (160, 160, 176)
GRAY_DIM    = (80,  88,  110)
DIVIDER     = (30,  40,  65)

CARD_W      = 1080
PAD         = 44


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
    logo_bytes: Optional[bytes] = None,
) -> bytes:
    """
    Compone la card estilizada (encabezado + ilustración) y devuelve los bytes PNG.

    Args:
        illus_bytes: JPEG/PNG de la ilustración extraída del PDF.
        section_code: Ej. "B1".
        section_name: Ej. "FRAME".
        logo_bytes:   PNG del logo de marca (fondo blanco — se eliminará).
    """
    # ── Ilustración ───────────────────────────────────────────────────────────
    illus = Image.open(io.BytesIO(illus_bytes)).convert("RGB")
    target_w = CARD_W - PAD * 2
    scale    = target_w / illus.width
    illus    = illus.resize((int(illus.width * scale), int(illus.height * scale)), Image.LANCZOS)
    illus_w, illus_h = illus.size

    # ── Alturas ───────────────────────────────────────────────────────────────
    # Card is header + illustration ONLY. The parts table used to be baked in
    # here too, but it duplicated (and, capped at MAX_ROWS, truncated worse
    # than) the structured part list both consumers now render themselves
    # (`/distribuidor/repuestos`'s own list panel, `/tg/parts`'s per-position
    # search) -- dropping it gives the illustration the full card and makes
    # the image's height depend only on the illustration, never on how many
    # parts a section happens to have.
    HEADER_H  = 104
    ILLUS_PAD = 32
    ILLUS_BLOCK = illus_h + ILLUS_PAD * 2 + 28

    CARD_H = HEADER_H + ILLUS_BLOCK + 8

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

    # ── Exportar ──────────────────────────────────────────────────────────────
    buf = io.BytesIO()
    card.save(buf, "PNG", optimize=True)
    return buf.getvalue()
