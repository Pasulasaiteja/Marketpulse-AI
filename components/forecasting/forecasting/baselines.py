"""
Baseline forecasting models for Demand Forecasting.
Includes:
- Seasonal-Naive (weekly cycle m=7)
- Moving Average (rolling window)
- Exponential Smoothing (Holt-Winters / SES)
"""

import numpy as np
import pandas as pd
from scipy import stats
from typing import Any


class BaseForecaster:
    """Abstract base class for all forecasters."""
    def __init__(self, name: str):
        self.name = name
        self.is_fitted = False
        
    def fit(self, y: np.ndarray, dates: pd.DatetimeIndex | None = None, **kwargs) -> "BaseForecaster":
        raise NotImplementedError
        
    def predict_quantiles(
        self,
        horizon_days: int,
        quantiles: list[float] = [0.10, 0.50, 0.90]
    ) -> dict[float, np.ndarray]:
        """
        Returns a dict mapping quantile (e.g. 0.10, 0.50, 0.90) to an array of length horizon_days.
        """
        raise NotImplementedError


class SeasonalNaiveForecaster(BaseForecaster):
    """
    Seasonal-Naive baseline for retail weekly seasonality (m=7).
    y_{t+h} = y_{t + h - 7*k}
    Uncertainty derived from empirical seasonal residual standard deviation.
    """
    def __init__(self, seasonal_period: int = 7):
        super().__init__(name="seasonal_naive")
        self.seasonal_period = seasonal_period
        self.history = np.array([])
        self.resid_std = 1.0
        self.residuals = np.array([])
        
    def fit(self, y: np.ndarray, dates: pd.DatetimeIndex | None = None, **kwargs) -> "SeasonalNaiveForecaster":
        y = np.asarray(y, dtype=float)
        self.history = y
        m = self.seasonal_period
        
        if len(y) > m:
            # In-sample seasonal residuals: y_t - y_{t-m}
            self.residuals = y[m:] - y[:-m]
            self.resid_std = float(np.std(self.residuals)) if len(self.residuals) > 1 else 1.0
            if self.resid_std < 1e-4:
                self.resid_std = 1.0
        else:
            self.resid_std = float(np.std(y)) if len(y) > 1 else 1.0
            self.residuals = np.zeros(1)
            
        self.is_fitted = True
        return self
        
    def predict_quantiles(
        self,
        horizon_days: int,
        quantiles: list[float] = [0.10, 0.50, 0.90]
    ) -> dict[float, np.ndarray]:
        if not self.is_fitted or len(self.history) == 0:
            raise RuntimeError("Model must be fitted before predict_quantiles.")
            
        m = self.seasonal_period
        recent = self.history[-m:] if len(self.history) >= m else np.pad(self.history, (m - len(self.history), 0), 'edge')
        
        # Point forecast: repeat seasonal pattern
        reps = int(np.ceil(horizon_days / m))
        point_preds = np.tile(recent, reps)[:horizon_days]
        
        # Quantile estimates based on Gaussian / empirical residual distribution
        out_quantiles = {}
        for q in quantiles:
            z = stats.norm.ppf(q)
            # Forecast error variance grows slightly with horizon step h
            h_factors = np.sqrt(1.0 + 0.05 * np.arange(horizon_days))
            q_vals = point_preds + z * self.resid_std * h_factors
            out_quantiles[q] = np.maximum(0.0, q_vals)
            
        return out_quantiles


class MovingAverageForecaster(BaseForecaster):
    """
    Moving Average baseline over window W (default 14 days).
    """
    def __init__(self, window: int = 14):
        super().__init__(name=f"moving_average_{window}")
        self.window = window
        self.mean_val = 0.0
        self.std_val = 1.0
        
    def fit(self, y: np.ndarray, dates: pd.DatetimeIndex | None = None, **kwargs) -> "MovingAverageForecaster":
        y = np.asarray(y, dtype=float)
        w = min(self.window, len(y))
        recent = y[-w:]
        self.mean_val = float(np.mean(recent)) if len(recent) > 0 else 0.0
        self.std_val = float(np.std(recent)) if len(recent) > 1 else max(1.0, 0.2 * self.mean_val)
        if self.std_val < 1e-4:
            self.std_val = max(1.0, 0.2 * self.mean_val)
        self.is_fitted = True
        return self
        
    def predict_quantiles(
        self,
        horizon_days: int,
        quantiles: list[float] = [0.10, 0.50, 0.90]
    ) -> dict[float, np.ndarray]:
        if not self.is_fitted:
            raise RuntimeError("Model must be fitted before predict_quantiles.")
            
        point_preds = np.full(horizon_days, self.mean_val)
        out_quantiles = {}
        for q in quantiles:
            z = stats.norm.ppf(q)
            h_factors = np.sqrt(1.0 + 0.08 * np.arange(horizon_days))
            q_vals = point_preds + z * self.std_val * h_factors
            out_quantiles[q] = np.maximum(0.0, q_vals)
            
        return out_quantiles


class ExponentialSmoothingForecaster(BaseForecaster):
    """
    Exponential Smoothing baseline using statsmodels Holt-Winters / SES.
    """
    def __init__(self, seasonal_periods: int = 7):
        super().__init__(name="exponential_smoothing")
        self.seasonal_periods = seasonal_periods
        self.model_res = None
        self.last_val = 0.0
        self.std_val = 1.0
        
    def fit(self, y: np.ndarray, dates: pd.DatetimeIndex | None = None, **kwargs) -> "ExponentialSmoothingForecaster":
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
        y = np.asarray(y, dtype=float)
        self.last_val = float(y[-1]) if len(y) > 0 else 0.0
        
        m = self.seasonal_periods
        # We need at least 2*m observations for seasonal Holt-Winters
        if len(y) >= 2 * m and np.all(y >= 0):
            try:
                # Add tiny epsilon to avoid zeros if multiplicative
                y_adj = np.maximum(y, 1e-3)
                hw = ExponentialSmoothing(
                    y_adj,
                    seasonal_periods=m,
                    trend="add",
                    seasonal="add",
                    initialization_method="estimated"
                )
                self.model_res = hw.fit(optimized=True)
                residuals = y_adj - self.model_res.fittedvalues
                self.std_val = float(np.std(residuals)) if len(residuals) > 1 else max(1.0, 0.2 * np.mean(y))
            except Exception:
                # Fallback to Simple Exponential Smoothing
                self._fit_simple(y)
        else:
            self._fit_simple(y)
            
        self.is_fitted = True
        return self
        
    def _fit_simple(self, y: np.ndarray):
        from statsmodels.tsa.holtwinters import SimpleExpSmoothing
        try:
            ses = SimpleExpSmoothing(y, initialization_method="estimated")
            self.model_res = ses.fit()
            residuals = y - self.model_res.fittedvalues
            self.std_val = float(np.std(residuals)) if len(residuals) > 1 else max(1.0, 0.2 * np.mean(y))
        except Exception:
            self.model_res = None
            self.std_val = float(np.std(y)) if len(y) > 1 else 1.0
            
    def predict_quantiles(
        self,
        horizon_days: int,
        quantiles: list[float] = [0.10, 0.50, 0.90]
    ) -> dict[float, np.ndarray]:
        if not self.is_fitted:
            raise RuntimeError("Model must be fitted before predict_quantiles.")
            
        if self.model_res is not None:
            try:
                point_preds = np.asarray(self.model_res.forecast(horizon_days), dtype=float)
            except Exception:
                point_preds = np.full(horizon_days, self.last_val)
        else:
            point_preds = np.full(horizon_days, self.last_val)
            
        point_preds = np.maximum(0.0, point_preds)
        out_quantiles = {}
        for q in quantiles:
            z = stats.norm.ppf(q)
            h_factors = np.sqrt(1.0 + 0.05 * np.arange(horizon_days))
            q_vals = point_preds + z * self.std_val * h_factors
            out_quantiles[q] = np.maximum(0.0, q_vals)
            
        return out_quantiles
