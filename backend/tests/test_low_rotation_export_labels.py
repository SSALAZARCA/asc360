"""
Tests for the decision->label mapping used by the "Ajuste de Pedidos"
Excel export (backend/app/api/v1/parts_manual.py, export_low_rotation_ordered).

The user reported: items marked "revisado" (green, approved) in the UI
export with no distinguishing text (same as never-decided items), and
never-decided items should show blank, not a dash.
"""
from app.api.v1.parts_manual import _decision_export_label


def test_cancelar_maps_to_cancelar_label():
    assert _decision_export_label("cancelar") == "CANCELAR"


def test_cambiar_maps_to_cambiar_label():
    assert _decision_export_label("cambiar") == "CAMBIAR"


def test_revisado_maps_to_aprobado_label():
    assert _decision_export_label("revisado") == "APROBADO"


def test_no_decision_maps_to_blank_not_dash():
    assert _decision_export_label("") == ""


def test_unknown_decision_falls_back_to_blank():
    assert _decision_export_label("something-unexpected") == ""
