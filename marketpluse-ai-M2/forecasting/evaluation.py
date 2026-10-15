"""
Evaluation module for Demand Forecasting.
Provides retail time-series metrics and rolling-origin backtest harness with zero leakage.
"""

import numpy as np
import pandas as pd
from typing import Generator, Any


def calc_mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Mean Absolute Error"""
    return float(np.mean(np.abs(y_true - y_pred)))


def calc_rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Root Mean Squared Error"""
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def calc_wape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """
    Weighted Absolute Percentage Error (WAPE).
    WAPE = sum(|y - y_hat|) / sum(y)
    Avoids division by zero that occurs with MAPE in sparse retail data.
    """
    total_true = np.sum(y_true)
    if total_true <= 0:
        return 0.0 if np.sum(np.abs(y_true - y_pred)) == 0 else 1.0
    return float(np.sum(np.abs(y_true - y_pred)) / total_true)


def calc_mase(y_true: np.ndarray, y_pred: np.ndarray, y_train: np.ndarray, seasonal_period: int = 7) -> float:
    """
    Mean Absolute Scaled Error (MASE).
    Scales MAE by the in-sample seasonal naive MAE.
    Values < 1.0 indicate the model beats seasonal-naive.
    """
    n_train = len(y_train)
    if n_train <= seasonal_period:
        # Fallback to non-seasonal diff
        diff = np.abs(np.diff(y_train))
    else:
        diff = np.abs(y_train[seasonal_period:] - y_train[:-seasonal_period])
        
    scale = np.mean(diff)
    if scale <= 1e-8:
        scale = 1.0
        
    mae = np.mean(np.abs(y_true - y_pred))
    return float(mae / scale)


def calc_pinball_loss(y_true: np.ndarray, q_pred: np.ndarray, tau: float) -> float:
    """
    Pinball Loss (Quantile Loss) for quantile tau in (0, 1).
    Loss = max(tau * (y - q), (1 - tau) * (q - y))
    """
    error = y_true - q_pred
    loss = np.maximum(tau * error, (tau - 1.0) * error)
    return float(np.mean(loss))


def evaluate_forecast(
    y_true: np.ndarray,
    y_p50: np.ndarray,
    quantiles_dict: dict[float, np.ndarray] | None = None,
    y_train: np.ndarray | None = None,
    seasonal_period: int = 7
) -> dict[str, float]:
    """
    Computes standard point and probabilistic metrics.
    """
    y_true = np.asarray(y_true, dtype=float)
    y_p50 = np.asarray(y_p50, dtype=float)
    
    metrics = {
        "mae": calc_mae(y_true, y_p50),
        "rmse": calc_rmse(y_true, y_p50),
        "wape": calc_wape(y_true, y_p50)
    }
    
    if y_train is not None and len(y_train) > seasonal_period:
        metrics["mase"] = calc_mase(y_true, y_p50, y_train, seasonal_period=seasonal_period)
        
    if quantiles_dict is not None:
        pinball_vals = []
        for tau, q_arr in quantiles_dict.items():
            q_arr = np.asarray(q_arr, dtype=float)
            p_loss = calc_pinball_loss(y_true, q_arr, tau)
            tau_key = f"pinball_p{int(round(tau * 100)):02d}"
            metrics[tau_key] = p_loss
            pinball_vals.append(p_loss)
            
        metrics["pinball_mean"] = float(np.mean(pinball_vals))
        
        # Check empirical 80% coverage: [p10, p90]
        if 0.10 in quantiles_dict and 0.90 in quantiles_dict:
            q10 = np.asarray(quantiles_dict[0.10], dtype=float)
            q90 = np.asarray(quantiles_dict[0.90], dtype=float)
            covered = (y_true >= q10) & (y_true <= q90)
            metrics["coverage_80"] = float(np.mean(covered))
            metrics["interval_width_80"] = float(np.mean(q90 - q10))
            
    return metrics


def rolling_origin_split(
    df: pd.DataFrame,
    date_col: str = "date",
    horizon_days: int = 14,
    n_splits: int = 3,
    step_days: int = 14,
    min_train_days: int = 90
) -> Generator[tuple[pd.DataFrame, pd.DataFrame, pd.Timestamp], None, None]:
    """
    Generates temporal rolling-origin train and test splits with strict temporal ordering.
    Guarantees zero future data leakage.
    
    Yields:
    -------
    (train_df, test_df, cutoff_date)
    """
    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col])
    all_dates = np.sort(df[date_col].unique())
    max_date = all_dates[-1]
    
    # Generate cutoffs backwards from max_date
    cutoffs = []
    for i in range(n_splits):
        cutoff = max_date - pd.Timedelta(days=horizon_days + i * step_days)
        # Check train duration
        train_start = all_dates[0]
        if (cutoff - train_start).days >= min_train_days:
            cutoffs.append(cutoff)
            
    cutoffs.reverse() # Chronological order
    
    for cutoff in cutoffs:
        test_end = cutoff + pd.Timedelta(days=horizon_days)
        train_df = df[df[date_col] <= cutoff].copy()
        test_df = df[(df[date_col] > cutoff) & (df[date_col] <= test_end)].copy()
        yield train_df, test_df, cutoff
