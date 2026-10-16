"""
Model Registry & Configuration for MarketPulse AI.
Allows Member 5 and other team members to dynamically select and swap forecasting engines.
"""

from typing import Any, Callable, Type
from .baselines import (
    SeasonalNaiveForecaster,
    MovingAverageForecaster,
    ExponentialSmoothingForecaster
)
from .gb_quantile import GradientBoostedQuantileForecaster, FeatureBuilder
from .statistical import HierarchicalBayesPoolingForecaster, AutoStatisticalForecaster


class ModelRegistry:
    """
    Central registry for demand forecasting models.
    Supports registration, listing, instantiation, and default model swapping.
    """
    _registry: dict[str, dict[str, Any]] = {}
    _default_model: str = "gb_quantile"

    @classmethod
    def register(cls, key: str, factory: Callable[..., Any], description: str, tags: list[str] | None = None):
        cls._registry[key] = {
            "factory": factory,
            "description": description,
            "tags": tags or []
        }

    @classmethod
    def get(cls, key: str | None = None, **kwargs) -> Any:
        model_key = key or cls._default_model
        if model_key not in cls._registry:
            available = list(cls._registry.keys())
            raise KeyError(f"Model '{model_key}' not found in registry. Available models: {available}")
        return cls._registry[model_key]["factory"](**kwargs)

    @classmethod
    def set_default(cls, key: str):
        if key not in cls._registry:
            raise KeyError(f"Cannot set default. Model '{key}' not found in registry.")
        cls._default_model = key

    @classmethod
    def get_default_name(cls) -> str:
        return cls._default_model

    @classmethod
    def list_models(cls) -> list[dict[str, Any]]:
        return [
            {
                "key": k,
                "description": v["description"],
                "tags": v["tags"],
                "is_default": (k == cls._default_model)
            }
            for k, v in cls._registry.items()
        ]


# Register baseline and production models
ModelRegistry.register(
    "gb_quantile",
    lambda **kwargs: GradientBoostedQuantileForecaster(
        n_estimators=kwargs.get("n_estimators", 50),
        learning_rate=kwargs.get("learning_rate", 0.06),
        feature_builder=FeatureBuilder(include_calendar=True, include_economic=True)
    ),
    description="Production LightGBM Quantile Regressor with lags and calendar features",
    tags=["production", "gbdt", "quantiles"]
)

ModelRegistry.register(
    "seasonal_naive",
    lambda **kwargs: SeasonalNaiveForecaster(seasonal_period=kwargs.get("seasonal_period", 7)),
    description="Weekly Seasonal Naive Baseline (m=7)",
    tags=["baseline", "fast"]
)

ModelRegistry.register(
    "moving_average",
    lambda **kwargs: MovingAverageForecaster(window=kwargs.get("window", 14)),
    description="14-day Moving Average Baseline",
    tags=["baseline"]
)

ModelRegistry.register(
    "exponential_smoothing",
    lambda **kwargs: ExponentialSmoothingForecaster(seasonal_periods=kwargs.get("seasonal_periods", 7)),
    description="Holt-Winters Additive Exponential Smoothing",
    tags=["baseline", "statistical"]
)

ModelRegistry.register(
    "hierarchical_sparse",
    lambda **kwargs: HierarchicalBayesPoolingForecaster(
        min_history_threshold=kwargs.get("min_history_threshold", 14),
        prior_cv=kwargs.get("prior_cv", 0.65)
    ),
    description="Hierarchical Category Prior Pooling for sparse & cold-start products",
    tags=["specialized", "cold_start", "sparse"]
)


def get_model(name: str | None = None, **kwargs) -> Any:
    return ModelRegistry.get(name, **kwargs)


def register_model(key: str, factory: Callable[..., Any], description: str, tags: list[str] | None = None):
    ModelRegistry.register(key, factory, description, tags)
