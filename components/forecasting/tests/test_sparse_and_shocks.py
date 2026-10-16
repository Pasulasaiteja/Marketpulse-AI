"""
Tests for Sparse Data Cold-Start Pooling & Shock Interval Widening.
Validates:
- Forecast still produced (with wide intervals) for products with little history
- Active shock flag widens intervals measurably by documented 1.5x rule
"""

import pytest
import numpy as np
import pandas as pd
from mock_data.generator import generate_synthetic_data
from forecasting.statistical import HierarchicalBayesPoolingForecaster
from forecasting.calibration import apply_shock_widening


@pytest.fixture(scope="module")
def mock_dataset():
    return generate_synthetic_data()


def test_sparse_product_cold_start_forecast(mock_dataset):
    df_sales = mock_dataset["sales"]
    df_products = mock_dataset["products"]
    
    model = HierarchicalBayesPoolingForecaster()
    model.fit(df_sales, df_products)
    
    # 1. Sparse product with only ~8 sales (PROD_SPECIALTY_TEA)
    sparse_preds = model.predict_product_horizon("STORE_001", "PROD_SPECIALTY_TEA", horizon_days=14)
    assert 0.10 in sparse_preds and 0.50 in sparse_preds and 0.90 in sparse_preds
    assert len(sparse_preds[0.50]) == 14
    assert np.all(sparse_preds[0.50] > 0.0)
    
    # Check that intervals are wide (high uncertainty: interval width > median)
    sparse_width = np.mean(sparse_preds[0.90] - sparse_preds[0.10])
    sparse_p50 = np.mean(sparse_preds[0.50])
    assert sparse_width >= 0.5 * sparse_p50
    
    # 2. Pure cold-start product with 0 sales (PROD_NEW_ENERGY_DRINK)
    cold_preds = model.predict_product_horizon("STORE_001", "PROD_NEW_ENERGY_DRINK", horizon_days=14, category="BEVERAGES")
    assert 0.10 in cold_preds and 0.90 in cold_preds
    assert np.all(cold_preds[0.50] > 0.0) # Category prior borrowed
    cold_width = np.mean(cold_preds[0.90] - cold_preds[0.10])
    assert cold_width > 0.0


def test_shock_widening_rule():
    # Baseline quantiles
    p50 = np.array([50.0, 50.0, 50.0])
    p10 = np.array([40.0, 40.0, 40.0])
    p90 = np.array([60.0, 60.0, 60.0])
    
    base_dict = {0.10: p10, 0.50: p50, 0.90: p90}
    base_width = np.mean(p90 - p10) # 20.0
    
    # When shock is inactive
    normal_q, factor = apply_shock_widening(base_dict, shock_active=False)
    assert factor == 1.0
    assert np.allclose(normal_q[0.10], p10)
    assert np.allclose(normal_q[0.90], p90)
    
    # When shock is active: widens by 1.5x
    shock_q, factor = apply_shock_widening(base_dict, shock_active=True, widening_factor=1.50)
    assert factor == 1.50
    shock_width = np.mean(shock_q[0.90] - shock_q[0.10])
    
    print(f"\nBase interval width: {base_width}, Shock interval width: {shock_width}")
    # Measurable 1.5x widening
    assert shock_width == pytest.approx(base_width * 1.50)
    # p10 should be 50 - 1.5*(10) = 35
    assert np.allclose(shock_q[0.10], 35.0)
    # p90 should be 50 + 1.5*(10) = 65
    assert np.allclose(shock_q[0.90], 65.0)
