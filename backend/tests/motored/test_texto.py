"""
Motored Pedidos — Fase 2 "Ingesta" (sdd/motored-pedidos-ingesta, ADR-7).

Pure, DB-free tests for `services/texto.py::normalizar_encabezado` -- la
función compartida de normalización de encabezados extraída de Fase 1's
`carga_excel.py::_normalize_header`.

`quitar_separadores=False` (default) DEBE ser byte-a-byte idéntica al
comportamiento previo de `_normalize_header` -- Fase 1 sigue llamándola con
el default y no debe cambiar en absoluto. `quitar_separadores=True` es el
modo nuevo que Fase 2 necesita para encabezados de archivos de movimiento
como "Dct.referencia".
"""
from app.motored.services.texto import normalizar_encabezado


def test_default_strips_accents_trims_and_lowercases_pinning_fase1_behavior():
    """Pin exacto del comportamiento previo de `_normalize_header` -- si
    esto cambia, Fase 1's bulk-upload de maestros se rompe."""
    assert normalizar_encabezado("Días de seguridad") == "dias de seguridad"


def test_default_is_case_and_accent_insensitive_but_keeps_spaces():
    assert normalizar_encabezado("DIAS_SEGURIDAD") == "dias_seguridad"
    assert normalizar_encabezado("  Código  ") == "codigo"


def test_none_returns_empty_string():
    assert normalizar_encabezado(None) == ""


def test_default_arg_is_false_explicit_call_matches_implicit_call():
    valor = "Días de Empaque"
    assert normalizar_encabezado(valor) == normalizar_encabezado(valor, quitar_separadores=False)


def test_quitar_separadores_strips_periods_for_movement_headers():
    assert normalizar_encabezado("Dct.referencia", quitar_separadores=True) == "dctreferencia"


def test_quitar_separadores_strips_underscores():
    assert normalizar_encabezado("unidad_empaque", quitar_separadores=True) == "unidadempaque"


def test_quitar_separadores_strips_spaces_and_hyphens():
    assert normalizar_encabezado("Días de seguridad", quitar_separadores=True) == "diasdeseguridad"
    assert normalizar_encabezado("algo-mas", quitar_separadores=True) == "algomas"


def test_quitar_separadores_false_leaves_separators_intact():
    assert normalizar_encabezado("Dct.referencia", quitar_separadores=False) == "dct.referencia"
