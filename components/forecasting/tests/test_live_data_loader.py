"""
Tests for Live Dataset Adapter (Member 1 Live Data Integration).
Validates:
- Discovery of Member 1 CSVs in data/
- Ingestion, schema alignment, and normalization of 73,000-row feature matrix
- Automatic routing of forecast() to live datasets when ITEM_* IDs are requested
- Backwards compatibility with mock data
"""

import pytest
import pandas as pd
from forecasting.data_loader import has_live_dataset, load_live_dataset
from forecasting.api import forecast


def test_has_live_dataset_detection():
    assert has_live_dataset() is True


def test_load_live_dataset_structure_and_types():
    data = load_live_dataset()
    assert isinstance(data, dict)
    
    # Check all expected tables are present
    for table_name in ["sales", "context", "products", "stores", "priors", "reviews"]:
        assert table_name in data
        assert isinstance(data[table_name], pd.DataFrame)
        assert len(data[table_name]) > 0

    df_sales = data["sales"]
    assert len(df_sales) == 73000
    assert set(["date", "store_id", "product_id", "units_sold", "on_promotion", "price", "category"]).issubset(df_sales.columns)

    df_context = data["context"]
    assert len(df_context) == 365
    assert set(["date", "payday_flag", "holiday_flag", "shock_flag", "day_of_week", "is_weekend"]).issubset(df_context.columns)

    df_products = data["products"]
    assert len(df_products) == 20
    assert set(["product_id", "category", "cost_price", "selling_price", "supplier_id", "lead_time_days"]).issubset(df_products.columns)


def test_forecast_api_with_live_dataset():
    # Calling forecast with Member 1's actual items on STORE_001
    df_fc = forecast(
        store_id="STORE_001",
        product_ids=["ITEM_001", "ITEM_002"],
        horizon_days=14,
        grid_step=0.05
    )

    assert isinstance(df_fc, pd.DataFrame)
    assert len(df_fc) == 2

    for _, row in df_fc.iterrows():
        assert row["store_id"] == "STORE_001"
        assert row["product_id"] in ["ITEM_001", "ITEM_002"]
        assert row["horizon_days"] == 14

        # Monotonicity check
        assert row["p10"] >= 0.0
        assert row["p10"] <= row["p50"]
        assert row["p50"] <= row["p90"]

        # Quantiles check
        q_dict = row["quantiles"]
        assert "q10" in q_dict and "q50" in q_dict and "q90" in q_dict
        assert len(q_dict) >= 19

        # Sample paths
        assert len(row["sample_paths"]) == 20


def test_forecast_backwards_compatibility_mock_data():
    # Calling forecast with legacy mock product ID
    df_mock = forecast(
        store_id="STORE_001",
        product_ids=["PROD_MILK_1L"],
        horizon_days=7,
        use_live_data=False
    )
    assert len(df_mock) == 1
    assert df_mock.iloc[0]["product_id"] == "PROD_MILK_1L"
