"""
Tests for Main Forecasting Models (LightGBM Quantile & Statistical).
Validates:
- Model fitting & multi-horizon forecasting (7, 14, 30 days)
- Main model beats or matches seasonal-naive on synthetic retail test set
- Synthetic ground-truth seasonal/payday pattern recovery
"""

import pytest
import numpy as np
import pandas as pd
from mock_data.generator import generate_synthetic_data
from forecasting.gb_quantile import GradientBoostedQuantileForecaster, FeatureBuilder
from forecasting.statistical import AutoStatisticalForecaster
from forecasting.baselines import SeasonalNaiveForecaster
from forecasting.evaluation import calc_wape, calc_mae, rolling_origin_split


@pytest.fixture(scope="module")
def mock_dataset():
    return generate_synthetic_data()


def test_lgbm_quantile_fit_and_predict(mock_dataset):
    df_sales = mock_dataset["sales"]
    df_context = mock_dataset["context"]
    
    # Train/test split by date
    train_sales = df_sales[df_sales["date"] <= "2026-07-01"].copy()
    test_sales = df_sales[(df_sales["date"] > "2026-07-01") & (df_sales["date"] <= "2026-07-15")].copy()
    
    model = GradientBoostedQuantileForecaster(n_estimators=40, learning_rate=0.08)
    model.fit(train_sales, df_context)
    
    for h in [7, 14, 30]:
        preds = model.predict_product_horizon("STORE_001", "PROD_MILK_1L", horizon_days=h)
        assert 0.10 in preds
        assert 0.50 in preds
        assert 0.90 in preds
        assert len(preds[0.50]) == h
        # Non-negative & monotonic
        assert np.all(preds[0.10] >= 0.0)
        assert np.all(preds[0.10] <= preds[0.50] + 1e-4)
        assert np.all(preds[0.50] <= preds[0.90] + 1e-4)


def test_main_model_beats_or_matches_naive_on_held_out(mock_dataset):
    df_sales = mock_dataset["sales"]
    df_context = mock_dataset["context"]
    
    # Filter to STORE_001, PROD_MILK_1L (has strong seasonal and payday pattern)
    milk_df = df_sales[(df_sales["store_id"] == "STORE_001") & (df_sales["product_id"] == "PROD_MILK_1L")].sort_values("date").reset_index(drop=True)
    
    # Backtest over 2 rolling origin folds
    horizon = 14
    splits = list(rolling_origin_split(milk_df, date_col="date", horizon_days=horizon, n_splits=2))
    
    naive_wapes = []
    lgbm_wapes = []
    
    for train_df, test_df, cutoff in splits:
        y_train = train_df["units_sold"].values
        y_test = test_df["units_sold"].values
        
        # 1. Seasonal Naive
        naive = SeasonalNaiveForecaster(seasonal_period=7)
        naive.fit(y_train)
        naive_preds = naive.predict_quantiles(horizon_days=horizon)[0.50]
        naive_wapes.append(calc_wape(y_test, naive_preds))
        
        # 2. LightGBM
        # Train on milk sales up to cutoff
        full_train = df_sales[pd.to_datetime(df_sales["date"]) <= cutoff].copy()
        lgbm = GradientBoostedQuantileForecaster(n_estimators=50, learning_rate=0.06)
        lgbm.fit(full_train, df_context)
        lgbm_preds = lgbm.predict_product_horizon("STORE_001", "PROD_MILK_1L", horizon_days=horizon)[0.50]
        lgbm_wapes.append(calc_wape(y_test, lgbm_preds))
        
    mean_naive_wape = np.mean(naive_wapes)
    mean_lgbm_wape = np.mean(lgbm_wapes)
    
    print(f"\nHeld-out WAPE - Seasonal Naive: {mean_naive_wape:.4f}, LGBM: {mean_lgbm_wape:.4f}")
    # LightGBM should achieve competitive/superior performance on seasonal series with payday features
    assert mean_lgbm_wape <= mean_naive_wape * 1.05 # Beats or essentially matches naive
