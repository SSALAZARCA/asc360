"""
tests/test_extract_section_illustration.py -- `_extract_section_illustration`
(`app/api/v1/parts_manual.py`), used by `load_section` when a superadmin
uploads a parts-manual PDF.

Some source PDFs split a section's exploded-view illustration across
MULTIPLE embedded images stacked on the page (e.g. the main assembly plus a
separate bracket/cover, one directly below the other) instead of a single
image. The previous extraction (`imgs = page.get_images(full=True);
extract_image(imgs[0][0])`) only ever grabbed the FIRST embedded image and
silently dropped the rest -- confirmed against a real source PDF
(`F01_HEADLIGHT.pdf`, Rockville 200) where item 4 (a lower bracket, its own
separately-embedded image placed directly below the main assembly image)
never appeared in the generated diagram card.

The fix: compute the union of the on-page placement rectangles of every
embedded image, then render (not re-extract) that exact page region as one
flat image. This captures any number of embedded images (or vector
graphics) correctly composited, regardless of how the source PDF happens to
be assembled.
"""
import io

import fitz
from PIL import Image

from app.api.v1.parts_manual import _extract_section_illustration


def _make_pdf_with_stacked_images(tmp_path) -> str:
    """Builds a real, minimal PDF with TWO embedded images placed directly
    stacked (one above the other), mirroring the real-world PDF's layout
    that exposed this bug."""
    top_img = Image.new("RGB", (200, 100), (255, 0, 0))   # red
    bottom_img = Image.new("RGB", (200, 100), (0, 0, 255))  # blue
    top_buf, bottom_buf = io.BytesIO(), io.BytesIO()
    top_img.save(top_buf, "PNG")
    bottom_img.save(bottom_buf, "PNG")

    doc = fitz.open()
    page = doc.new_page(width=400, height=400)
    page.insert_image(fitz.Rect(50, 50, 250, 150), stream=top_buf.getvalue())
    page.insert_image(fitz.Rect(50, 150, 250, 250), stream=bottom_buf.getvalue())
    pdf_path = str(tmp_path / "stacked.pdf")
    doc.save(pdf_path)
    doc.close()
    return pdf_path


def _make_pdf_with_single_image(tmp_path) -> str:
    img = Image.new("RGB", (200, 100), (0, 255, 0))  # green
    buf = io.BytesIO()
    img.save(buf, "PNG")

    doc = fitz.open()
    page = doc.new_page(width=400, height=400)
    page.insert_image(fitz.Rect(50, 50, 250, 150), stream=buf.getvalue())
    pdf_path = str(tmp_path / "single.pdf")
    doc.save(pdf_path)
    doc.close()
    return pdf_path


def _make_pdf_with_no_images(tmp_path) -> str:
    doc = fitz.open()
    page = doc.new_page(width=400, height=400)
    page.insert_text((50, 50), "Just some vector text, no embedded images")
    pdf_path = str(tmp_path / "vector_only.pdf")
    doc.save(pdf_path)
    doc.close()
    return pdf_path


class TestCapturesEveryEmbeddedImageNotJustTheFirst:
    def test_stacked_images_both_end_up_in_the_extracted_illustration(self, tmp_path):
        """The real bug: with two stacked images, extracting only imgs[0]
        would produce a ~100px-tall result (just the top image). The fix's
        union-of-rects render must span BOTH -- roughly 200px tall."""
        pdf_path = _make_pdf_with_stacked_images(tmp_path)

        illus_bytes = _extract_section_illustration(pdf_path)

        img = Image.open(io.BytesIO(illus_bytes))
        # Rendered at 4x zoom (see implementation): (250-50)*4=800 wide,
        # (250-50)*4=800 tall for the two combined 100pt-tall images stacked.
        assert img.width >= 700
        assert img.height >= 700  # would be ~400 (only the top image) if the bug were still present

    def test_pixel_colors_from_both_images_are_present(self, tmp_path):
        """Confirms both the top (red) and bottom (blue) source images are
        genuinely present in the output, not just that the canvas is tall
        enough by coincidence."""
        pdf_path = _make_pdf_with_stacked_images(tmp_path)

        illus_bytes = _extract_section_illustration(pdf_path)
        img = Image.open(io.BytesIO(illus_bytes)).convert("RGB")

        top_pixel = img.getpixel((img.width // 2, int(img.height * 0.25)))
        bottom_pixel = img.getpixel((img.width // 2, int(img.height * 0.75)))
        assert top_pixel[0] > 200 and top_pixel[2] < 100  # reddish
        assert bottom_pixel[2] > 200 and bottom_pixel[0] < 100  # bluish


class TestSingleImageStillWorks:
    def test_a_single_embedded_image_is_still_extracted_correctly(self, tmp_path):
        pdf_path = _make_pdf_with_single_image(tmp_path)

        illus_bytes = _extract_section_illustration(pdf_path)

        img = Image.open(io.BytesIO(illus_bytes)).convert("RGB")
        pixel = img.getpixel((img.width // 2, img.height // 2))
        assert pixel[1] > 200  # greenish


class TestNoEmbeddedImagesFallsBackToFullPageRender:
    def test_vector_only_page_falls_back_to_a_full_page_render(self, tmp_path):
        pdf_path = _make_pdf_with_no_images(tmp_path)

        illus_bytes = _extract_section_illustration(pdf_path)

        img = Image.open(io.BytesIO(illus_bytes))
        assert img.width > 0 and img.height > 0
