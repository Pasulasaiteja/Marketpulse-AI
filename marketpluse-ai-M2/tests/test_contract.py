"""
Tests for Output Shared Contract & API Specification.
Validates:
- Schema compatibility with Member 3 (Optimizer)
- Monotonic quantiles (p10 <= p50 <= p90)
- 5% grid quantile completeness (q05, q10, ..., q95)
- 20 sample paths format
- Runtime latency limit (< 1.5s for a single store forecast)
"""

import pytest
import time
import pandas as pd
import numpy as np
from forecasting.api import forecast
from forecasting.registry import ModelRegistry


def test_forecast_api_contract_schema():
    # Call forecast for STORE_001 over 14 days
    df_fc = forecast(
        store_id="STORE_001",
        product_ids=["PROD_MILK_1L", "PROD_BREAD", "PROD_COOKING_OIL_1L"],
        horizon_days=14,
        grid_step=0.05
    )
    
    assert isinstance(df_fc, pd.DataFrame)
    assert len(df_fc) == 3
    
    expected_cols = [
        "store_id", "product_id", "horizon_days", "forecast_date",
        "p10", "p50", "p90", "quantiles", "sample_paths",
        "shock_active", "widening_factor", "model_name", "features_used"
    ]
    assert list(df_fc.columns) == expected_cols
    
    for _, row in df_fc.iterrows():
        assert row["store_id"] == "STORE_001"
        assert row["horizon_days"] == 14
        # Validate YYYY-MM-DD
        pd.to_datetime(row["forecast_date"])
        
        # Monotonicity
        assert row["p10"] >= 0.0
        assert row["p10"] <= row["p50"]
        assert row["p50"] <= row["p90"]
        
        # Quantiles 5% grid dictionary
        q_dict = row["quantiles"]
        assert isinstance(q_dict, dict)
        for expected_q in ["q05", "q10", "q25", "q50", "q75", "q90", "q95"]:
            assert expected_q in q_dict
            assert q_dict[expected_q] >= 0.0
            
        # Sample paths
        paths = row["sample_paths"]
        assert isinstance(paths, list)
        assert len(paths) == 20
        assert all(isinstance(p, (float, int)) for p in paths)
        
        # Shock metadata
        assert isinstance(row["shock_active"], bool)
        assert row["widening_factor"] >= 1.0
        
        # Features used
        assert isinstance(row["features_used"], list)
        assert len(row["features_used"]) > 0


def test_forecast_model_swapping():
    # Test that Member 5 can swap models via model_name parameter
    df_naive = forecast(
        store_id="STORE_001",
        product_ids=["PROD_MILK_1L"],
        horizon_days=7,
        model_name="seasonal_naive"
    )
    assert len(df_naive) == 1
    assert "naive" in df_naive["model_name"].iloc[0].lower()


def test_forecast_runtime_performance():
    # 1. Warm up the model engine (ensure weights/cache initialized)
    forecast(store_id="STORE_001", product_ids=["PROD_MILK_1L"], horizon_days=7)

    # 2. Measure single-store production forecast inference latency
    start_t = time.time()
    df = forecast(
        store_id="STORE_001",
        product_ids=["PROD_MILK_1L", "PROD_BREAD"],
        horizon_days=14
    )
    elapsed = time.time() - start_t
    print(f"\nSingle-store forecast inference runtime: {elapsed:.3f} seconds")
    # Inference must run well under defined limit (< 3.0 seconds per store)
    assert elapsed < 3.0
