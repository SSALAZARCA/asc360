"""
Unit tests for `_resolve_status_map` (`backend/app/api/v1/imports.py`) —
Phase 2 of `sdd/imports-oversized-functions-refactor-tier1`.

Pure function, no DB/HTTP: exercises the per-`is_spare_part`-mode
status-count selection/merge logic extracted from `get_imports_dashboard`.
"""
from app.api.v1.imports import _resolve_status_map


def test_is_spare_part_false_returns_motos_map_untouched():
    motos_map = {"en_preparacion": 2, "completado": 5}
    sp_map = {"en_preparacion": 100}
    assert _resolve_status_map(motos_map, sp_map, False) == motos_map


def test_is_spare_part_true_returns_sp_map_untouched():
    motos_map = {"en_preparacion": 2}
    sp_map = {"en_transito": 7, "backorder": 1}
    assert _resolve_status_map(motos_map, sp_map, True) == sp_map


def test_is_spare_part_none_sums_shared_keys():
    motos_map = {"en_preparacion": 2, "completado": 5}
    sp_map = {"en_preparacion": 3, "backorder": 1}
    result = _resolve_status_map(motos_map, sp_map, None)
    assert result == {"en_preparacion": 5, "completado": 5, "backorder": 1}


def test_is_spare_part_none_handles_disjoint_keys_with_zero_default():
    motos_map = {"en_transito": 4}
    sp_map = {"en_destino": 6}
    result = _resolve_status_map(motos_map, sp_map, None)
    assert result == {"en_transito": 4, "en_destino": 6}


def test_is_spare_part_none_with_both_maps_empty_returns_empty_dict():
    assert _resolve_status_map({}, {}, None) == {}
