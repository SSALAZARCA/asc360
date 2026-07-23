"""
compute_prices must not cascade IVA: each stage's tax applies to that
stage's net (pre-tax) base, not to a price that already includes the
previous stage's IVA. The distributor's margin is computed on the
provider's net cost, never on the provider's IVA-inclusive invoice price.
"""
from app.services.pricing_service import compute_prices

FACTORS = {
    "import_factor": 1.42,
    "provider_margin": 0.35,
    "distributor_margin": 0.35,
    "iva_rate": 0.19,
    "trm": 3800.0,
}


def test_none_fob_returns_all_none():
    assert compute_prices(None, FACTORS) == {
        "costo_importado": None,
        "precio_distribuidor": None,
        "precio_publico": None,
    }


def test_costo_importado_has_no_iva():
    result = compute_prices(10.0, FACTORS)
    expected = round(10.0 * FACTORS["import_factor"] * FACTORS["trm"], 0)
    assert result["costo_importado"] == expected


def test_precio_distribuidor_applies_iva_once_on_net_base():
    result = compute_prices(10.0, FACTORS)
    costo_importado_usd = 10.0 * FACTORS["import_factor"]
    net_usd = costo_importado_usd * (1 + FACTORS["provider_margin"])
    expected = round(net_usd * (1 + FACTORS["iva_rate"]) * FACTORS["trm"], 0)
    assert result["precio_distribuidor"] == expected


def test_precio_publico_margin_is_on_distributor_net_not_iva_inclusive_price():
    """
    Regression: distributor margin must be applied on the provider's NET
    cost (pre-IVA), not on precio_distribuidor (which already has IVA in
    it) — otherwise IVA compounds on top of IVA across the two stages.
    """
    result = compute_prices(10.0, FACTORS)
    costo_importado_usd = 10.0 * FACTORS["import_factor"]
    dist_net_usd = costo_importado_usd * (1 + FACTORS["provider_margin"])
    publico_net_usd = dist_net_usd * (1 + FACTORS["distributor_margin"])
    expected = round(publico_net_usd * (1 + FACTORS["iva_rate"]) * FACTORS["trm"], 0)
    assert result["precio_publico"] == expected


def test_iva_does_not_compound_between_distribuidor_and_publico():
    """
    Regression: the old formula applied distributor_margin AND a second
    (1+iva_rate) on top of precio_distribuidor, which already carried the
    first IVA — i.e. IVA-on-IVA. The fix must land strictly below what
    that cascading formula would have produced.
    """
    result = compute_prices(10.0, FACTORS)

    costo_importado_usd = 10.0 * FACTORS["import_factor"]
    dist_net_usd = costo_importado_usd * (1 + FACTORS["provider_margin"])
    dist_iva_inclusive_usd = dist_net_usd * (1 + FACTORS["iva_rate"])
    buggy_publico_usd = (
        dist_iva_inclusive_usd
        * (1 + FACTORS["distributor_margin"])
        * (1 + FACTORS["iva_rate"])
    )
    buggy_precio_publico = round(buggy_publico_usd * FACTORS["trm"], 0)

    assert result["precio_publico"] < buggy_precio_publico
