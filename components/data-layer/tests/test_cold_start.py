"""
tests/test_cold_start.py
Unit tests verifying store clustering prior calculations and dataset loader execution.
"""

import pandas as pd
from src.loader import load_dataset
from src.cold_start import generate_cold_start_priors


def test_load_dataset_entrypoints():
    for name in ["synthetic", "synthetic_sparse", "m5", "favorita"]:
        sales_df, stores_df, items_df, context_df = load_dataset(name)
        assert not sales_df.empty
        assert not stores_df.empty
        assert not items_df.empty
        assert not context_df.empty


def test_cold_start_prior_generation():
    sales_df, stores_df, _, _ = load_dataset("synthetic")

    # Force STORE_001 to have only 5 days of history (cold start)
    max_date = sales_df["date"].min() + pd.Timedelta(days=5)
    sales_df_truncated = sales_df[
        ~((sales_df["store_id"] == "STORE_001") & (sales_df["date"] > max_date))
    ].copy()

    priors = generate_cold_start_priors(sales_df_truncated, stores_df, min_history_days=14)
    assert not priors.empty
    assert "prior_sales_quantity" in priors.columns