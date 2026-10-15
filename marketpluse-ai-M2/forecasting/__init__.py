"""
Forecasting Package for MarketPulse AI (Member 2).
Provides probabilistic demand forecasting, baselines, GBDT quantile models,
statistical models, calibration, and market signal integration.
"""

from .api import forecast
from .registry import ModelRegistry, get_model, register_model
from .baselines import (
    BaseForecaster,
    SeasonalNaiveForecaster,
    MovingAverageForecaster,
    ExponentialSmoothingForecaster
)
from .evaluation import (
    calc_mae,
    calc_rmse,
    calc_wape,
    calc_mase,
    calc_pinball_loss,
    evaluate_forecast,
    rolling_origin_split
)
from .gb_quantile import GradientBoostedQuantileForecaster, FeatureBuilder
from .statistical import HierarchicalBayesPoolingForecaster, AutoStatisticalForecaster
from .calibration import ConformalCalibrator, apply_shock_widening
from .data_loader import has_live_dataset, load_live_dataset

__all__ = [
    "forecast",
    "has_live_dataset",
    "load_live_dataset",
    "ModelRegistry",
    "get_model",
    "register_model",
    "BaseForecaster",
    "SeasonalNaiveForecaster",
    "MovingAverageForecaster",
    "ExponentialSmoothingForecaster",
    "GradientBoostedQuantileForecaster",
    "FeatureBuilder",
    "HierarchicalBayesPoolingForecaster",
    "AutoStatisticalForecaster",
    "ConformalCalibrator",
    "apply_shock_widening",
    "calc_mae",
    "calc_rmse",
    "calc_wape",
    "calc_mase",
    "calc_pinball_loss",
    "evaluate_forecast",
    "rolling_origin_split"
]
