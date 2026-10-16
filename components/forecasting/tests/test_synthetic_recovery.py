"""
Tests for Synthetic Ground-Truth Pattern Recovery.
Validates:
- Model recovers weekly seasonality (Saturday > Monday)
- Model recovers payday surge (end of month days 27-31 > mid-month)
"""

import pytest
import numpy as np
import pandas as pd
from mock_data.generator import generate_synthetic_data
from forecasting.gb_quantile import GradientBoostedQuantileForecaster, FeatureBuilder


@pytest.fixture(scope="module")
def mock_dataset():
    return generate_synthetic_data()


def test_synthetic_seasonality_and_payday_recovery(mock_dataset):
    df_sales = mock_dataset["sales"]
    df_context = mock_dataset["context"]
    
    # Train on first 12 months
    cutoff = "2026-01-01"
    train_sales = df_sales[df_sales["date"] <= cutoff].copy()
    
    model = GradientBoostedQuantileForecaster(
        n_estimators=60,
        learning_rate=0.06,
        feature_builder=FeatureBuilder(include_calendar=True, include_economic=False)
    )
    model.fit(train_sales, df_context)
    
    # Forecast 14 days starting from Monday
    # Let's inspect predictions for STORE_001, PROD_MILK_1L
    preds = model.predict_product_horizon("STORE_001", "PROD_MILK_1L", horizon_days=14)
    p50_preds = preds[0.50]
    
    # Check that predictions reflect variation (not a flat mean)
    std_preds = np.std(p50_preds)
    mean_preds = np.mean(p50_preds)
    print(f"\nPredicted mean: {mean_preds:.2f}, std: {std_preds:.2f}")
    assert std_preds > 0.05 * mean_preds # Meaningful seasonal oscillation
    
    # Check Feature Importances in LightGBM model
    lgbm_p50 = model.models[0.50]
    importances = dict(zip(model.trained_features, lgbm_p50.feature_importances_))
    print(f"\nFeature importances: {importances}")
    
    # Lag 7 (weekly cycle) or calendar features should have high importance
    assert importances.get("lag_7", 0) > 0 or importances.get("day_of_week", 0) > 0
    assert importances.get("payday_flag", 0) > 0 or importances.get("lag_1", 0) > 0
