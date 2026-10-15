"""
tests/test_synthetic_ground_truth.py
Verifies that synthetic data signals (like payday boosts) match ground-truth configuration ratios.
"""

import pandas as pd
from src.synthetic_generator import generate_synthetic_data, load_config


def test_payday_ground_truth_effect():
    cfg = load_config("config/synthetic_config.yaml")
    sales_df, _, _, context_df = generate_synthetic_data("config/synthetic_config.yaml")

    # Filter context for payday dates
    payday_dates = context_df[
        (context_df["feature_name"] == "is_payday") & (context_df["value"] == 1.0)
    ]["date"].unique()

    # Exclude stockout days (where sales_quantity == 0) to evaluate true demand boost
    valid_sales = sales_df[sales_df["sales_quantity"] > 0].copy()

    payday_sales_mean = valid_sales[valid_sales["date"].isin(payday_dates)]["sales_quantity"].mean()
    non_payday_sales_mean = valid_sales[~valid_sales["date"].isin(payday_dates)]["sales_quantity"].mean()

    ratio = payday_sales_mean / non_payday_sales_mean
    expected_boost = cfg["multipliers"]["payday_boost"]

    # Verify boost ratio is within 25% margin of expectation
    assert abs(ratio - expected_boost) < 0.35