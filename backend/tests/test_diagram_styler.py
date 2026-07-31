"""
tests/test_diagram_styler.py -- `create_diagram_card` (`app/services/diagram_styler.py`).

Both frontend consumers of this composited PNG (`/distribuidor/repuestos`'s
own "Listado de Componentes" panel, and `/tg/parts`'s per-position search)
already have their own structured, un-truncated way to show a part's full
detail -- the parts TABLE that used to be baked into this image was pure
duplication, and worse than the structured data because it was capped at
`MAX_ROWS` with a "... y N partes mas" note whenever a section had more
parts than that. This change removes the table and footer from the
generated card entirely (and drops the now-unused `parts`/`model_name`
parameters) -- the card is just header + illustration, so it can never be
"cropped"/truncated again: there's no table left to truncate, and the
image's height depends only on the illustration, never on how many parts a
section happens to have.
"""
import io

from PIL import Image

from app.services.diagram_styler import create_diagram_card


def _make_illustration_bytes(w=400, h=300) -> bytes:
    img = Image.new("RGB", (w, h), (255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


class TestCardIsHeaderAndIllustrationOnly:
    def test_returns_a_valid_png_at_the_fixed_card_width(self):
        png_bytes = create_diagram_card(
            illus_bytes=_make_illustration_bytes(w=400, h=300),
            section_code="B1", section_name="FRAME",
        )
        img = Image.open(io.BytesIO(png_bytes))
        assert img.format == "PNG"
        assert img.width == 1080  # CARD_W

    def test_height_is_bounded_regardless_of_how_many_parts_the_section_has(self):
        """No `parts` argument exists anymore -- the whole point of removing
        the table is that the card's height can no longer be inflated by a
        section having many parts. Before this change, the same illustration
        with a 20-row table measured 1590px tall; header + illustration alone
        must stay comfortably under that."""
        png_bytes = create_diagram_card(
            illus_bytes=_make_illustration_bytes(w=400, h=300),
            section_code="B1", section_name="FRAME",
        )
        img = Image.open(io.BytesIO(png_bytes))
        assert img.height < 1200

    def test_height_scales_with_illustration_height_only(self):
        short_illus_card = create_diagram_card(
            illus_bytes=_make_illustration_bytes(w=400, h=200),
            section_code="B1", section_name="FRAME",
        )
        tall_illus_card = create_diagram_card(
            illus_bytes=_make_illustration_bytes(w=400, h=800),
            section_code="B1", section_name="FRAME",
        )
        short_img = Image.open(io.BytesIO(short_illus_card))
        tall_img = Image.open(io.BytesIO(tall_illus_card))
        assert tall_img.height > short_img.height

    def test_no_longer_accepts_the_removed_parts_and_model_name_arguments(self):
        """Pins the signature change: `parts`/`model_name` are gone, not
        silently ignored, so a caller can't believe it's still passing
        parts data anywhere."""
        import pytest
        with pytest.raises(TypeError):
            create_diagram_card(
                illus_bytes=_make_illustration_bytes(),
                section_code="B1", section_name="FRAME",
                model_name="RENEGADE 200", parts=[],
            )
