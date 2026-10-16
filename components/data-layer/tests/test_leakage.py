"""
tests/test_leakage.py
Unit tests asserting strict absence of future data leakage in feature engineering.
"""

import pandas as pd
import numpy as np
from src.pipeline import add_lag_and_rolling_features


def test_no_future_data_leakage():
    # Setup dummy sales data over 10 days
    dates = pd.date_range("2026-01-01", periods=10, freq="D")
    sales_a = [10.0, 12.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 50.0]
    
    df_original = pd.DataFrame({
        "date": dates,
        "store_id": "STORE_001",
        "item_id": "ITEM_101",
        "sales_quantity": sales_a
    })
    
    features_original = add_lag_and_rolling_features(df_original, lags=[1, 7], rolling_windows=[7])
    
    # Mutate sales_quantity at t=8 and t=9 (future days relative to t=5)
    sales_b = sales_a.copy()
    sales_b[8] = 9999.0
    sales_b[9] = 8888.0
    
    df_mutated = pd.DataFrame({
        "date": dates,
        "store_id": "STORE_001",
        "item_id": "ITEM_101",
        "sales_quantity": sales_b
    })
    
    features_mutated = add_lag_and_rolling_features(df_mutated, lags=[1, 7], rolling_windows=[7])
    
    # Features at t <= 7 must remain identical despite future mutations
    sub_orig = features_original.iloc[:7][["sales_lag_1", "sales_lag_7", "sales_roll_mean_7"]]
    sub_mut = features_mutated.iloc[:7][["sales_lag_1", "sales_lag_7", "sales_roll_mean_7"]]
    
    pd.testing.assert_frame_equal(sub_orig, sub_mut)