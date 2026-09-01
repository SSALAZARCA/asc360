"""
tests/services/test_dim_parser_service.py — regression coverage for the
VIN-split-across-page-break bug in `dim_parser_service.py`.

Bug summary: when a DIAN "Declaración de Importación" (DIM) PDF cuts a VIN
mid-string at a page break, the DIAN document itself marks the cut with the
literal "(continúa al respaldo)" on the original page, and the real
continuation appears at the top of the next page. Before the fix,
`limpiar_texto_continuidad()` only removed the literal marker string on the
original page but left that page's own trailing footer/boilerplate
(payment references, "Levante No.", signature block, etc.) attached right
after the truncated fragment. Once all pages were concatenated, the
truncated VIN ended up glued to irrelevant footer text instead of to its
real continuation on the next page, so the regex in
`buscar_vins_en_bloque()` never matched a valid 17-char VIN and the vehicle
silently vanished from the parser's output — no error, no warning.

The fix: `limpiar_texto_continuidad()` now truncates the page text at the
first occurrence of "(continúa al respaldo)", discarding everything after
it on that same page, so the join with the next page's (already correctly
cleaned) continuation happens with nothing but a single space in between.
"""
from pathlib import Path

import pytest

from app.services.dim_parser_service import (
    limpiar_texto_continuidad,
    parse_dim_pdf,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent
    / "fixtures"
    / "dim_vin_split_across_page_break.pdf"
)

EXPECTED_VINS = [
    "SD5TDLPA2T0F00212",
    "SD5TDLPA9T0F00224",
    "SD5TDLPA5T0F00219",
    "SD5TDLPA1T0F00217",
    "SD5TDLPA1T0F00220",
    "SD5TDLPA9T0F00207",
    "SD5TDLPAXT0F00216",
    "SD5TDLPA3T0F00218",
    "SD5TDLPA6T0F00214",
    "SD5TDLPA2T0F00209",  # split across the page break — was missing before the fix
]

SPLIT_VIN = "SD5TDLPA2T0F00209"
NOT_SPLIT_VIN = "SD5TDLPA2T0F00212"  # fully contained on page 1, no page-break involved


def _load_fixture_bytes() -> bytes:
    return FIXTURE_PATH.read_bytes()


class TestParseDimPdfRegression:
    def test_all_ten_vins_are_extracted_from_real_pdf(self):
        vehiculos = parse_dim_pdf(_load_fixture_bytes())
        vins = [v["vin"] for v in vehiculos]

        assert set(EXPECTED_VINS) == set(vins)

    def test_vin_split_across_page_break_is_included(self):
        vehiculos = parse_dim_pdf(_load_fixture_bytes())
        vins = [v["vin"] for v in vehiculos]

        assert SPLIT_VIN in vins

    def test_non_split_vin_still_extracts_correctly(self):
        """A VIN fully contained on a single page, with no
        "(continúa al respaldo)" involved, must keep working after the fix."""
        vehiculos = parse_dim_pdf(_load_fixture_bytes())
        vins = [v["vin"] for v in vehiculos]

        assert NOT_SPLIT_VIN in vins


class TestParseDimPdfMetadataRegression:
    """Regression coverage: truncating a page's text at "(continúa al
    respaldo)" (needed for VIN extraction) must NOT also delete that same
    page's acceptance/levante metadata, which lives in the footer right
    after the marker on the real fixture PDF."""

    def test_no_lev_and_f_lev_survive_the_continua_al_respaldo_truncation(self):
        vehiculos = parse_dim_pdf(_load_fixture_bytes())

        assert vehiculos, "expected at least one vehicle parsed from fixture"
        for v in vehiculos:
            assert v["no_lev"] == "032026001173567"
            assert v["f_lev"] == "2026-08-26"

    def test_no_acep_and_f_acep_remain_correct(self):
        vehiculos = parse_dim_pdf(_load_fixture_bytes())

        assert vehiculos, "expected at least one vehicle parsed from fixture"
        for v in vehiculos:
            assert v["no_acep"] == "032026001104809"
            assert v["f_acep"] == "2026-07-28"


class TestLimpiarTextoContinuidad:
    def test_strips_footer_after_continua_al_respaldo_marker(self):
        pagina = (
            "104. Descripción de mercancías (Incluya marcas, seriales y otros) "
            "VIN: SD5TDLPA2T0F0(continúa al respaldo)\n"
            "127 . Valor pagos anteriores: 0 128 . Recibo oficial de pago "
            "anterior No.: XXXXXXXXXXXXXXX 129. Fecha: XXXX XX XX\n"
            "Estado de levante: Levante automático 032026001104809\n"
            "133. Fecha: 2026 07 28\n"
            "Firma declarante: ..."
        )

        limpio = limpiar_texto_continuidad(pagina)

        assert limpio.endswith("SD5TDLPA2T0F0")
        assert "continúa al respaldo" not in limpio
        assert "Valor pagos anteriores" not in limpio
        assert "Levante automático" not in limpio
        assert "Firma declarante" not in limpio

    def test_page_without_marker_is_unaffected(self):
        pagina = "104. Descripción de mercancías VIN: SD5TDLPA2T0F00212, color BLANCO"

        limpio = limpiar_texto_continuidad(pagina)

        assert "SD5TDLPA2T0F00212" in limpio
        assert "color BLANCO" in limpio

    def test_continuation_page_header_stripping_still_works(self):
        """Pre-existing behavior on continuation pages must be preserved."""
        pagina = (
            "REPÚBLICA DE COLOMBIA Página 1 de 1\n"
            "105. Continuación descripción mercancías (Incluya marcas, seriales y otros)\n"
            "0209, NUMERO SERIAL MOTOR: 1P63MKT0F00212"
        )

        limpio = limpiar_texto_continuidad(pagina)

        assert limpio.startswith("0209")
        assert "105. Continuación" not in limpio


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
