"""Tests verifying fixes for code quality, path handling, contract alignment, and robustness."""

import datetime as dt
import os
import unittest.mock as mock

import pandas as pd
import pytest

from marketpulse import config
from marketpulse.adapters.team_modules import TeamOptimizer, TeamSignalProvider
from marketpulse.contracts.models import (
    CanonicalData,
    ForecastOutput,
    Product,
    ProductForecast,
    QuantilePoint,
    SalesRecord,
)
from marketpulse.registry import default_modules, mock_modules
from marketpulse.service import ApiError, BoundedDict, DecisionService, _parse_budget_and_horizon


# ---------------------------------------------------------------------------
# 1. Path Handling & Assumptions in Config
# ---------------------------------------------------------------------------
def test_config_assumptions_registered():
    """Verify that operational and demand multiplier assumptions are in ASSUMPTIONS."""
    assert "DAYS_TO_NEXT_REPLENISHMENT" in config.ASSUMPTIONS
    assert config.ASSUMPTIONS["DAYS_TO_NEXT_REPLENISHMENT"].value == 7
    assert "Default cadence" in config.ASSUMPTIONS["DAYS_TO_NEXT_REPLENISHMENT"].rationale

    assert "DEFAULT_PACK_SIZE" in config.ASSUMPTIONS
    assert config.ASSUMPTIONS["DEFAULT_PACK_SIZE"].value == 1

    assert "CONTEXT_DEMAND_EFFECTS" in config.ASSUMPTIONS
    effects = config.ASSUMPTIONS["CONTEXT_DEMAND_EFFECTS"].value
    assert isinstance(effects, dict)
    assert effects.get("near_school") == 0.05
    assert effects.get("near_market") == 0.08


# ---------------------------------------------------------------------------
# 2. Inventory & Optimizer Adapter Float Precision
# ---------------------------------------------------------------------------
def test_optimizer_adapter_float_precision_preserved():
    """Verify that float inventory (e.g. 5.5 kg on hand, 2.25 on order) is preserved."""
    as_of = dt.date(2026, 10, 1)
    product = Product(
        product_id="prod_bulk_rice",
        name="Bulk Rice",
        category="Grains",
        unit_cost=10.0,
        unit_price=15.0,
        current_stock=5.5,
        on_order=2.25,
        lead_time_days=2,
        min_order_qty=1,
    )
    sales = [
        SalesRecord(date=dt.date(2026, 9, 30), product_id="prod_bulk_rice", units_sold=3.0)
    ]
    data = CanonicalData(
        shop_id="shop_test",
        currency="USD",
        as_of=as_of,
        products=[product],
        sales=sales,
    )
    forecast = ForecastOutput(
        as_of=as_of,
        horizon_days=14,
        model_name="test_model",
        forecasts=[
            ProductForecast(
                product_id="prod_bulk_rice",
                mean=12.0,
                quantiles=[QuantilePoint(p=q, value=12.0) for q in config.QUANTILE_GRID],
                history_days=1,
            )
        ],
    )

    optimizer = TeamOptimizer()
    with mock.patch("marketpulse.adapters.team_modules._load_component") as mock_load:
        mock_opt = mock.MagicMock()
        mock_load.return_value = mock_opt
        # Mock native optimize response
        mock_native_plan = mock.MagicMock()
        mock_native_plan.binding_constraints = []
        mock_native_plan.items = {}
        mock_opt.engine.optimize.return_value = mock_native_plan

        optimizer.optimize(forecast, data, budget=500.0)

        # Inspect what was passed to optimizer.models.InventoryState
        inv_call_kwargs = mock_opt.models.InventoryState.call_args[1]
        assert isinstance(inv_call_kwargs["on_hand"], float)
        assert inv_call_kwargs["on_hand"] == 5.5
        assert isinstance(inv_call_kwargs["on_order"], float)
        assert inv_call_kwargs["on_order"] == 2.25
        assert inv_call_kwargs["days_to_next_replenishment"] == config.DAYS_TO_NEXT_REPLENISHMENT

        # Inspect what was passed to optimizer.models.ProductMeta
        prod_call_kwargs = mock_opt.models.ProductMeta.call_args[1]
        assert prod_call_kwargs["pack_size"] == config.DEFAULT_PACK_SIZE


def test_optimizer_real_engine_fractional_stock():
    """Verify end-to-end that the real optimizer engine handles fractional inventory properly."""
    as_of = dt.date(2026, 10, 1)
    product = Product(
        product_id="prod_bulk_rice",
        name="Bulk Rice",
        category="Grains",
        unit_cost=10.0,
        unit_price=15.0,
        current_stock=5.5,
        on_order=2.25,
        lead_time_days=2,
        min_order_qty=1,
    )
    sales = [
        SalesRecord(date=dt.date(2026, 9, 30), product_id="prod_bulk_rice", units_sold=3.0)
    ]
    data = CanonicalData(
        shop_id="shop_test",
        currency="USD",
        as_of=as_of,
        products=[product],
        sales=sales,
    )
    forecast = ForecastOutput(
        as_of=as_of,
        horizon_days=14,
        model_name="test_model",
        forecasts=[
            ProductForecast(
                product_id="prod_bulk_rice",
                mean=20.0,
                quantiles=[QuantilePoint(p=q, value=20.0) for q in config.QUANTILE_GRID],
                history_days=1,
            )
        ],
    )

    optimizer = TeamOptimizer()
    plan = optimizer.optimize(forecast, data, budget=500.0)
    assert plan is not None
    assert len(plan.lines) == 1
    assert plan.lines[0].product_id == "prod_bulk_rice"




# ---------------------------------------------------------------------------
# 3. Integration & Fallback Posture Alignment
# ---------------------------------------------------------------------------
def test_registry_fallback_posture():
    """Verify registry raises errors rather than silently falling back to mocks unless MARKETPULSE_USE_MOCKS is set."""  # noqa: E501
    # When MARKETPULSE_USE_MOCKS=1, returns mock_modules()
    with mock.patch.dict(os.environ, {"MARKETPULSE_USE_MOCKS": "1"}):
        mods = default_modules()
        assert mods.extractor.__class__.__name__ == "MockExtractor"

    # When MARKETPULSE_USE_MOCKS is not set and integrated_modules raises, it must propagate
    with mock.patch.dict(os.environ, {"MARKETPULSE_USE_MOCKS": "0"}):
        with mock.patch("marketpulse.adapters.team_modules.integrated_modules", side_effect=RuntimeError("GPU missing")):  # noqa: E501
            with pytest.raises(RuntimeError, match="GPU missing"):
                default_modules()


def test_signal_provider_broadened_mapping():
    """Verify TeamSignalProvider maps Member 2's NLP and statistical signals to the contract."""
    as_of = dt.date(2026, 10, 1)
    data = CanonicalData(
        shop_id="shop_test",
        currency="USD",
        as_of=as_of,
        products=[
            Product(product_id="prod_1", name="Milk", unit_cost=2.0, unit_price=3.0, current_stock=10, on_order=0, lead_time_days=1, min_order_qty=1)  # noqa: E501
        ],
        sales=[
            SalesRecord(date=dt.date(2026, 9, 30), product_id="prod_1", units_sold=5.0)
        ]
    )

    # Mock Member 2's pipeline output DataFrame
    fake_detected = pd.DataFrame([
        {
            "signal_id": "SIG_001",
            "product_or_category": "prod_1",
            "type": "CHANGE_POINT_SPIKE",
            "evidence": "Sales surged by +45%",
            "confidence": 0.88,
            "date": "2026-09-30",
        },
        {
            "signal_id": "SIG_002",
            "product_or_category": "Dairy",
            "type": "CUSTOMER_NEED",
            "evidence": "Customer review: 'do you carry lactose free milk'",
            "confidence": 0.92,
            "date": "2026-09-30",
        },
        {
            "signal_id": "SIG_003",
            "product_or_category": "Beverages",
            "type": "CUSTOMER_COMPLAINT",
            "evidence": "Customer review: 'cold drinks were warm and empty shelf'",
            "confidence": 0.85,
            "date": "2026-09-30",
        },
        {
            "signal_id": "SIG_004",
            "product_or_category": "Snacks",
            "type": "EMERGING_PREFERENCE",
            "evidence": "Customer review: 'trending zero sugar snacks'",
            "confidence": 0.80,
            "date": "2026-09-30",
        },
    ])

    provider = TeamSignalProvider()
    with mock.patch("marketpulse.adapters.team_modules._load_component") as mock_load:
        mock_ms = mock.MagicMock()
        mock_load.return_value = mock_ms
        mock_pipeline_inst = mock.MagicMock()
        mock_ms.pipeline.MarketSignalPipeline.return_value = mock_pipeline_inst
        mock_pipeline_inst.extract_signals.return_value = fake_detected

        out = provider.get_signals(data, as_of)

        assert len(out.signals) == 4
        s_spike, s_need, s_comp, s_pref = out.signals

        assert s_spike.type == "demand_shift"
        assert s_spike.direction == "up"
        assert s_spike.product_id == "prod_1"
        assert s_spike.magnitude == 0.45

        assert s_need.type == "unmet_demand"
        assert s_need.direction == "up"
        assert s_need.category == "Dairy"
        assert s_need.evidence[0].source == "customer_review"

        assert s_comp.type == "review_theme"
        assert s_comp.direction == "down"
        assert s_comp.category == "Beverages"

        assert s_pref.type == "category_growth"
        assert s_pref.direction == "up"
        assert s_pref.category == "Snacks"


# ---------------------------------------------------------------------------
# 4. Robustness & API Defensive Validation
# ---------------------------------------------------------------------------
def test_parse_budget_and_horizon_defensive():
    """Verify _parse_budget_and_horizon rejects invalid types with clean 422 ApiError."""
    # Missing budget
    with pytest.raises(ApiError) as exc:
        _parse_budget_and_horizon({})
    assert exc.value.status == 422
    assert exc.value.code == "INVALID_BUDGET"

    # Non-numeric budget string
    with pytest.raises(ApiError) as exc:
        _parse_budget_and_horizon({"budget": "not_a_number"})
    assert exc.value.status == 422
    assert exc.value.code == "INVALID_BUDGET"

    # Negative budget
    with pytest.raises(ApiError) as exc:
        _parse_budget_and_horizon({"budget": -50})
    assert exc.value.status == 422
    assert exc.value.code == "INVALID_BUDGET"

    # Infinite budget
    with pytest.raises(ApiError) as exc:
        _parse_budget_and_horizon({"budget": float("inf")})
    assert exc.value.status == 422
    assert exc.value.code == "INVALID_BUDGET"

    # Non-numeric horizon
    with pytest.raises(ApiError) as exc:
        _parse_budget_and_horizon({"budget": 100, "horizon_days": "two_weeks"})
    assert exc.value.status == 422
    assert exc.value.code == "INVALID_HORIZON"

    # Unsupported horizon
    with pytest.raises(ApiError) as exc:
        _parse_budget_and_horizon({"budget": 100, "horizon_days": 45})
    assert exc.value.status == 422
    assert exc.value.code == "INVALID_HORIZON"

    # Valid parsing
    b, h = _parse_budget_and_horizon({"budget": "500.50", "horizon_days": "14"})
    assert b == 500.50
    assert h == 14


def test_bounded_dict_lru_eviction():
    """Verify BoundedDict enforces maxsize bound and evicts oldest unaccessed entries."""
    bd = BoundedDict(maxsize=3)
    bd["a"] = 1
    bd["b"] = 2
    bd["c"] = 3
    assert len(bd) == 3

    # Access 'a' to make it recently used
    _ = bd["a"]

    # Insert 'd' -> 'b' should be evicted because 'a' was accessed more recently than 'b'
    bd["d"] = 4
    assert len(bd) == 3
    assert "b" not in bd
    assert "a" in bd
    assert "c" in bd
    assert "d" in bd

    # Insert 'e' -> 'c' should be evicted
    bd["e"] = 5
    assert len(bd) == 3
    assert "c" not in bd
    assert "a" in bd
    assert "d" in bd
    assert "e" in bd

    bd.clear()
    assert len(bd) == 0


def test_service_clear_cache():
    """Verify DecisionService clear_cache empties forecast_cache and results."""
    service = DecisionService(modules=mock_modules())
    service.forecast_cache["test_key"] = mock.MagicMock()
    service.results["test_res"] = mock.MagicMock()
    assert len(service.forecast_cache) == 1
    assert len(service.results) == 1

    service.clear_cache()
    assert len(service.forecast_cache) == 0
    assert len(service.results) == 0


# ---------------------------------------------------------------------------
# 7. Multi-Currency & International Country Support
# ---------------------------------------------------------------------------
def test_currency_and_country_normalizers():
    """Verify currency symbols, words, and country names normalize to ISO codes."""
    from marketpulse.normalizers import normalize_country, normalize_currency

    # Currency normalization
    assert normalize_currency("$") == "USD"
    assert normalize_currency("usd") == "USD"
    assert normalize_currency("dollar") == "USD"
    assert normalize_currency("dollars") == "USD"
    assert normalize_currency("€") == "EUR"
    assert normalize_currency("eur") == "EUR"
    assert normalize_currency("euro") == "EUR"
    assert normalize_currency("euros") == "EUR"
    assert normalize_currency("£") == "GBP"
    assert normalize_currency("gbp") == "GBP"
    assert normalize_currency("pound") == "GBP"
    assert normalize_currency("₹") == "INR"
    assert normalize_currency("rupee") == "INR"
    assert normalize_currency("rupees") == "INR"
    assert normalize_currency("CAD") == "CAD"
    assert normalize_currency("AUD") == "AUD"
    assert normalize_currency("JPY") == "JPY"
    assert normalize_currency("KES") == "KES"

    # Country normalization
    assert normalize_country("USA") == "US"
    assert normalize_country("united states") == "US"
    assert normalize_country("UK") == "GB"
    assert normalize_country("united kingdom") == "GB"
    assert normalize_country("france") == "FR"
    assert normalize_country("spain") == "ES"
    assert normalize_country("germany") == "DE"
    assert normalize_country("india") == "IN"
    assert normalize_country("japan") == "JP"
    assert normalize_country("kenya") == "KE"


def test_mock_extractor_multi_currency():
    """Verify MockExtractor detects non-INR places and currencies."""
    from marketpulse.mocks.extractor import MockExtractor

    extractor = MockExtractor()

    # US (USD)
    p_us = extractor.extract_profile("Small corner grocery in New York near a school, budget 5000 dollars")
    assert p_us.fields.country.value == "US"
    assert p_us.fields.currency.value == "USD"

    # UK (GBP)
    p_uk = extractor.extract_profile("Corner shop in London near a market, budget 3000 pounds")
    assert p_uk.fields.country.value == "GB"
    assert p_uk.fields.currency.value == "GBP"

    # France (EUR)
    p_fr = extractor.extract_profile("Petite épicerie à Paris près d'une école, budget 4000 euros")
    assert p_fr.fields.country.value == "FR"
    assert p_fr.fields.currency.value == "EUR"

    # Spain (EUR)
    p_es = extractor.extract_profile("Tienda en Madrid cerca de un mercado, presupuesto 3500 euros")
    assert p_es.fields.country.value == "ES"
    assert p_es.fields.currency.value == "EUR"


def test_team_extractor_multi_currency():
    """Verify TeamExtractor recognizes US, UK, EU and normalizes currency."""
    from marketpulse.adapters.team_modules import TeamExtractor

    extractor = TeamExtractor()

    # US Shop with $
    p_us = extractor.extract_profile("Small grocery in New York near a school, budget $5000, payday 15th")
    assert p_us.fields.country.value == "US"
    assert p_us.fields.currency.value == "USD"

    # UK Shop with GBP
    p_uk = extractor.extract_profile(
        "Retail grocery in London near a bus station, budget 4000 GBP, payday 28th")
    assert p_uk.fields.country.value == "GB"
    assert p_uk.fields.currency.value == "GBP"

    # Paris Shop with EUR
    p_fr = extractor.extract_profile("Boutique à Paris près d'une école, budget 5000 euros, payday 25th")
    assert p_fr.fields.country.value == "FR"
    assert p_fr.fields.currency.value == "EUR"


def test_confirm_profile_currency_symbol_and_dataset_sync():
    """Verify confirm_profile handles currency symbols like '$' and synchronizes dataset currency."""
    from marketpulse.csvloader import dump_csv
    from marketpulse.mocks.fixtures import make_canonical_data

    service = DecisionService(modules=default_modules())
    extract_resp = service.extract_profile("Corner store in Delhi near a school, budget 5000")
    profile_id = extract_resp["profile"]["profile_id"]

    # Confirm with '$' and 'USA' -> should normalize to USD and US without failing validation
    conf_resp = service.confirm_profile(profile_id, edits={"currency": "$", "country": "USA"})
    assert conf_resp["status"] == "confirmed"
    assert conf_resp["profile"]["fields"]["currency"]["value"] == "USD"
    assert conf_resp["profile"]["fields"]["country"]["value"] == "US"

    # Plan with CSV data (which was generated with default INR) -> service synchronizes dataset to USD!
    data_inr = make_canonical_data()
    assert data_inr.currency == "INR"
    p_csv, s_csv = dump_csv(data_inr)

    plan_resp = service.plan({
        "profile_id": profile_id,
        "budget": 5000.0,
        "products_csv": p_csv,
        "sales_csv": s_csv,
    })
    assert plan_resp["status"] == "ok"
    assert plan_resp["plan"]["currency"] == "USD"

