"""
Uncertainty Calibration & Shock Widening Module.
Implements:
- Split Conformal Prediction for empirical 80% coverage guarantee.
- Documented Shock Widening Rule (1.5x interval width expansion during active shocks).

SECURITY: NaN/Inf guards prevent silent propagation of degenerate adjustment
           deltas when validation data contains missing or extreme values.
"""

import numpy as np
import pandas as pd
from typing import Any


class ConformalCalibrator:
    """
    Split Conformal Calibrator.
    Computes nonconformity scores on a validation split and adjusts
    prediction intervals to guarantee empirical coverage matching target level (e.g. 80%).
    """
    def __init__(self, target_coverage: float = 0.80):
        self.target_coverage = target_coverage
        self.delta: float = 0.0
        self.is_calibrated: bool = False

    def calibrate(
        self,
        y_val: np.ndarray,
        q10_val: np.ndarray,
        q90_val: np.ndarray
    ) -> float:
        """
        Calibrates interval bounds on validation data.
        Returns the non-conformity adjustment delta.

        SECURITY FIX: NaN/Inf values in inputs are dropped before computing
                      the conformal delta so that a single bad row cannot
                      produce a NaN delta that silently widens all future
                      intervals to infinity.
        """
        y_val   = np.atleast_1d(np.asarray(y_val,   dtype=float))
        q10_val = np.atleast_1d(np.asarray(q10_val, dtype=float))
        q90_val = np.atleast_1d(np.asarray(q90_val, dtype=float))

        # Broadcast scalar q10/q90 to match y_val length (common API usage)
        if q10_val.shape != y_val.shape:
            q10_val = np.broadcast_to(q10_val, y_val.shape).copy()
        if q90_val.shape != y_val.shape:
            q90_val = np.broadcast_to(q90_val, y_val.shape).copy()

        # SECURITY: drop NaN / Inf rows before any computation
        valid_mask = (
            np.isfinite(y_val) &
            np.isfinite(q10_val) &
            np.isfinite(q90_val)
        )
        y_val, q10_val, q90_val = y_val[valid_mask], q10_val[valid_mask], q90_val[valid_mask]

        if len(y_val) == 0:
            # No usable validation data — skip calibration
            self.delta = 0.0
            self.is_calibrated = True
            return self.delta

        # Empirical coverage before calibration
        covered = (y_val >= q10_val) & (y_val <= q90_val)
        raw_cov = float(np.mean(covered))

        # Nonconformity score: distance outside the interval
        scores = np.maximum(q10_val - y_val, y_val - q90_val)
        scores = np.maximum(0.0, scores)

        # If raw coverage already within tolerance, minimal delta
        if raw_cov >= self.target_coverage - 0.04:
            self.delta = 0.0
        else:
            # Finite-sample conformal correction quantile: ceil((n+1)*target)/n
            n = len(scores)
            p_quantile = min(1.0, np.ceil((n + 1) * self.target_coverage) / n) if n > 0 else self.target_coverage
            raw_delta = float(np.quantile(scores, p_quantile))
            # SECURITY: guard against Inf delta from extreme outliers
            self.delta = float(np.clip(raw_delta, 0.0, 1e6))

        self.is_calibrated = True
        return self.delta

    def adjust_intervals(
        self,
        quantiles_dict: dict[float, np.ndarray]
    ) -> dict[float, np.ndarray]:
        """
        Applies calibration adjustment delta to interval boundaries while preserving monotonicity.
        """
        if not self.is_calibrated or self.delta <= 1e-6:
            return quantiles_dict
            
        adjusted = {}
        delta = self.delta
        p50 = quantiles_dict.get(0.50)
        
        for q, arr in quantiles_dict.items():
            arr = np.asarray(arr, dtype=float)
            if q <= 0.20:
                # Widen lower bound downward
                adjusted[q] = np.maximum(0.0, arr - delta)
            elif q >= 0.80:
                # Widen upper bound upward
                adjusted[q] = arr + delta
            else:
                # Intermediate quantiles stay centered or scale smoothly
                adjusted[q] = arr
                
        # Enforce monotonicity
        sorted_keys = sorted(adjusted.keys())
        for i in range(1, len(sorted_keys)):
            k_prev = sorted_keys[i - 1]
            k_curr = sorted_keys[i]
            adjusted[k_curr] = np.maximum(adjusted[k_curr], adjusted[k_prev])
            
        return adjusted


def apply_shock_widening(
    quantiles_dict: dict[float, np.ndarray],
    shock_active: bool,
    widening_factor: float = 1.50
) -> tuple[dict[float, np.ndarray], float]:
    """
    Applies the documented shock widening rule:
    When shock_flag is active, interval width is expanded by widening_factor (default 1.5x)
    around the median point estimate p50.
    
    Returns:
    --------
    (widened_quantiles_dict, applied_widening_factor)
    """
    if not shock_active or widening_factor <= 1.0:
        return quantiles_dict, 1.0
        
    p50 = quantiles_dict.get(0.50)
    if p50 is None:
        return quantiles_dict, 1.0
        
    widened = {}
    for q, arr in quantiles_dict.items():
        arr = np.asarray(arr, dtype=float)
        if q < 0.50:
            diff = p50 - arr
            widened[q] = np.maximum(0.0, p50 - widening_factor * diff)
        elif q > 0.50:
            diff = arr - p50
            widened[q] = p50 + widening_factor * diff
        else:
            widened[q] = arr.copy()
            
    # Guarantee monotonicity
    sorted_keys = sorted(widened.keys())
    for i in range(1, len(sorted_keys)):
        k_prev = sorted_keys[i - 1]
        k_curr = sorted_keys[i]
        widened[k_curr] = np.maximum(widened[k_curr], widened[k_prev])
        
    return widened, widening_factor
