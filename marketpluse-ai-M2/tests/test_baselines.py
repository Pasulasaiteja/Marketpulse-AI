"""
Unit tests for Baseline Models & Evaluation Metrics.
Checks:
- Seasonal-Naive, Moving Average, Exponential Smoothing
- Metric calculations (MAE, RMSE, WAPE, MASE, Pinball loss)
- Quantile ordering (q10 <= q50 <= q90)
- Rolling-origin zero-leakage splits
"""

import pytest
import numpy as np
import pandas as pd
from forecasting.baselines import (
    SeasonalNaiveForecaster,
    MovingAverageForecaster,
    ExponentialSmoothingForecaster
)
from forecasting.evaluation import (
    calc_mae,
    calc_rmse,
    calc_wape,
    calc_mase,
    calc_pinball_loss,
    evaluate_forecast,
    rolling_origin_split
)


def test_metric_calculations():
    y_true = np.array([10.0, 20.0, 30.0])
    y_pred = np.array([12.0, 18.0, 33.0])
    
    assert calc_mae(y_true, y_pred) == pytest.approx(7.0 / 3.0)
    assert calc_rmse(y_true, y_pred) == pytest.approx(np.sqrt((4 + 4 + 9) / 3.0))
    assert calc_wape(y_true, y_pred) == pytest.approx(7.0 / 60.0)
    
    # Pinball loss
    # For tau=0.5, pinball loss is 0.5 * MAE
    p50_loss = calc_pinball_loss(y_true, y_pred, tau=0.5)
    assert p50_loss == pytest.approx(0.5 * (7.0 / 3.0))
    
    # MASE
    y_train = np.array([10.0, 15.0, 12.0, 18.0, 20.0, 25.0, 22.0, 11.0, 16.0])
    mase = calc_mase(y_true, y_pred, y_train, seasonal_period=7)
    assert mase > 0.0


def test_baseline_forecasters_horizons_and_quantiles():
    np.random.seed(42)
    # Synthetic series with weekly seasonality
    base = 20.0
    dow_effect = np.tile([0.8, 0.9, 1.0, 1.0, 1.2, 1.4, 1.3], 10)
    y_train = base * dow_effect + np.random.normal(0, 1.5, len(dow_effect))
    
    models = [
        SeasonalNaiveForecaster(seasonal_period=7),
        MovingAverageForecaster(window=14),
        ExponentialSmoothingForecaster(seasonal_periods=7)
    ]
    
    for model in models:
        model.fit(y_train)
        for horizon in [7, 14, 30]:
            quantiles = model.predict_quantiles(horizon_days=horizon, quantiles=[0.10, 0.50, 0.90])
            assert 0.10 in quantiles
            assert 0.50 in quantiles
            assert 0.90 in quantiles
            
            q10 = quantiles[0.10]
            q50 = quantiles[0.50]
            q90 = quantiles[0.90]
            
            assert len(q10) == horizon
            assert len(q50) == horizon
            assert len(q90) == horizon
            
            # Non-negativity
            assert np.all(q10 >= 0.0)
            assert np.all(q50 >= 0.0)
            assert np.all(q90 >= 0.0)
            
            # Monotonicity: q10 <= q50 <= q90
            assert np.all(q10 <= q50 + 1e-5)
            assert np.all(q50 <= q90 + 1e-5)


def test_rolling_origin_no_leakage():
    dates = pd.date_range("2026-01-01", "2026-06-30", freq="D")
    df = pd.DataFrame({
        "date": dates,
        "units_sold": np.random.poisson(15, len(dates))
    })
    
    horizon = 14
    splits = list(rolling_origin_split(df, date_col="date", horizon_days=horizon, n_splits=3, min_train_days=60))
    assert len(splits) == 3
    
    for train_df, test_df, cutoff in splits:
        # Strict temporal separation
        assert train_df["date"].max() <= cutoff
        assert test_df["date"].min() > cutoff
        assert (test_df["date"].max() - cutoff).days <= horizon
        # No overlap between train and test
        assert len(set(train_df["date"]).intersection(set(test_df["date"]))) == 0
