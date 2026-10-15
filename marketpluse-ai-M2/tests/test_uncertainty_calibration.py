"""
Tests for Prediction Interval Calibration (Conformal Prediction).
Pass condition: 80% interval covers roughly 80% of actuals within tolerance.
"""

import pytest
import numpy as np
from forecasting.calibration import ConformalCalibrator


def test_conformal_calibrator_achieves_target_coverage():
    np.random.seed(42)
    n = 200
    y_val = np.random.normal(50.0, 10.0, n)
    
    # Simulate an under-confident or overly narrow model (coverage ~60%)
    # Narrow interval: [y_mean - 0.84*std, y_mean + 0.84*std] ~60% normal coverage
    q10_raw = np.full(n, 50.0 - 0.84 * 10.0)
    q90_raw = np.full(n, 50.0 + 0.84 * 10.0)
    
    raw_coverage = np.mean((y_val >= q10_raw) & (y_val <= q90_raw))
    assert raw_coverage < 0.70 # Under-covered before calibration
    
    calibrator = ConformalCalibrator(target_coverage=0.80)
    delta = calibrator.calibrate(y_val, q10_raw, q90_raw)
    assert delta > 0.0 # Delta should widen the interval
    
    # Test on unseen validation holdout
    y_test = np.random.normal(50.0, 10.0, 300)
    q10_test = np.full(300, 50.0 - 0.84 * 10.0)
    q90_test = np.full(300, 50.0 + 0.84 * 10.0)
    
    calibrated = calibrator.adjust_intervals({
        0.10: q10_test,
        0.50: np.full(300, 50.0),
        0.90: q90_test
    })
    
    calibrated_cov = np.mean((y_test >= calibrated[0.10]) & (y_test <= calibrated[0.90]))
    print(f"\nRaw coverage: {raw_coverage:.2%}, Calibrated coverage: {calibrated_cov:.2%}")
    # 80% interval covers roughly 80% of actuals (within tolerance [75%, 88%])
    assert 0.75 <= calibrated_cov <= 0.88
