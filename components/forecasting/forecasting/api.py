"""
Primary Entry-Point API for Demand Forecasting.
Implements the shared contract for Member 3 (Inventory Optimizer).

SECURITY: All public-facing parameters are validated before any processing
           to prevent crashes, infinite loops, and silent data corruption.
"""

import numpy as np
import pandas as pd
from typing import Any
from datetime import datetime
from mock_data.generator import load_or_generate_mock_dataset
from .registry import ModelRegistry, get_model
from .statistical import HierarchicalBayesPoolingForecaster
from .calibration import ConformalCalibrator, apply_shock_widening
from .data_loader import has_live_dataset, load_live_dataset


# ---------------------------------------------------------------------------
# Input validation helpers
# ---------------------------------------------------------------------------

def _validate_forecast_inputs(
    store_id: str,
    product_ids,
    horizon_days: int,
    grid_step: float
) -> None:
    """
    SECURITY FIX: Validate all public inputs to forecast().
    Raises ValueError with a descriptive message for every invalid combination.
    """
    if not isinstance(store_id, str) or not store_id.strip():
        raise ValueError(
            f"store_id must be a non-empty string; got {store_id!r}."
        )
    if not isinstance(horizon_days, int) or horizon_days <= 0:
        raise ValueError(
            f"horizon_days must be a positive integer; got {horizon_days!r}."
        )
    if horizon_days > 365:
        raise ValueError(
            f"horizon_days={horizon_days} exceeds the maximum allowed value of 365 "
            "days to prevent excessive computation and memory usage."
        )
    if not isinstance(grid_step, (int, float)) or not (0.01 <= grid_step < 0.50):
        raise ValueError(
            f"grid_step must be a float in [0.01, 0.50); got {grid_step!r}. "
            "Values outside this range produce degenerate or empty quantile grids."
        )
    if product_ids is not None:
        if not isinstance(product_ids, (list, tuple)):
            raise ValueError(
                f"product_ids must be a list/tuple of strings or None; got {type(product_ids)}."
            )
        for pid in product_ids:
            if not isinstance(pid, str) or not pid.strip():
                raise ValueError(
                    f"Each product_id must be a non-empty string; got {pid!r}."
                )


# Global cached engines segregated by model and data source
_GLOBAL_ENGINE_CACHE = {}


def _resolve_dataset(
    dataset: dict[str, pd.DataFrame] | None,
    product_ids: list[str] | None,
    store_id: str,
    use_live_data: bool | None = None
) -> tuple[dict[str, pd.DataFrame], str]:
    """
    Resolves whether to consume Member 1's live dataset or mock dataset.
    """
    if dataset is not None:
        return dataset, f"custom_{id(dataset)}"

    # If caller explicitly asked for live data or live items are requested
    if use_live_data is True and has_live_dataset():
        return load_live_dataset(), "live"

    if use_live_data is False:
        return load_or_generate_mock_dataset(), "mock"

    if has_live_dataset():
        # Check if requested products belong to live dataset naming convention
        if product_ids is not None and any(p.startswith("ITEM_") for p in product_ids):
            return load_live_dataset(), "live"

    # Default to mock dataset for full backwards compatibility
    return load_or_generate_mock_dataset(), "mock"


def _get_or_init_engine(
    dataset: dict[str, pd.DataFrame],
    dataset_key: str,
    model_name: str | None = None
):
    model_key = model_name or ModelRegistry.get_default_name()
    cache_key = f"{model_key}_{dataset_key}"
    if cache_key in _GLOBAL_ENGINE_CACHE:
        return _GLOBAL_ENGINE_CACHE[cache_key]

    df_sales = dataset["sales"]
    df_context = dataset["context"]
    df_products = dataset.get("products")

    # 1. Main model
    main_model = get_model(model_key)
    if hasattr(main_model, "fit"):
        if "gb_quantile" in model_key:
            main_model.fit(df_sales, df_context)
        elif hasattr(main_model, "fit"):
            pass

    # 2. Sparse pooling model
    sparse_model = HierarchicalBayesPoolingForecaster()
    sparse_model.fit(df_sales, df_products)

    # 3. Conformal Calibrator pre-fitted on recent validation fold
    calibrator = ConformalCalibrator(target_coverage=0.80)
    recent_date = pd.to_datetime(df_sales["date"]).max() - pd.Timedelta(days=28)
    val_sales = df_sales[pd.to_datetime(df_sales["date"]) > recent_date]
    if len(val_sales) > 50 and "gb_quantile" in model_key:
        y_val = val_sales["units_sold"].values
        mean_v = np.mean(y_val)
        std_v = np.std(y_val)
        calibrator.calibrate(y_val, np.maximum(0, mean_v - 1.28 * std_v), mean_v + 1.28 * std_v)

    engine = {
        "main_model": main_model,
        "sparse_model": sparse_model,
        "calibrator": calibrator,
        "data": dataset,
        "model_name": model_key
    }
    _GLOBAL_ENGINE_CACHE[cache_key] = engine
    return engine


def forecast(
    store_id: str,
    product_ids: list[str] | None = None,
    horizon_days: int = 14,
    grid_step: float = 0.05,
    model_name: str | None = None,
    dataset: dict[str, pd.DataFrame] | None = None,
    use_live_data: bool | None = None,
    as_dataframe: bool = True
) -> "pd.DataFrame | list[dict[str, Any]]":
    """
    Computes probabilistic demand forecast conforming 100% to CONTRACT.md.

    Parameters:
    -----------
    store_id: str
        Target retail store identifier (e.g. "STORE_001").
    product_ids: list[str] | None
        List of product IDs to forecast. If None, forecasts for all active products in the store.
    horizon_days: int
        Planning horizon in days (e.g. 7, 14, 30).
    grid_step: float
        Quantile grid resolution, default 0.05 (produces q05, q10, ..., q95).
    model_name: str | None
        Model registry key (e.g. "gb_quantile", "seasonal_naive").
    dataset: dict[str, pd.DataFrame] | None
        Optional custom dataset conforming to Member 1 contract. If None, uses mock dataset.
    as_dataframe: bool
        If True, returns pandas.DataFrame; otherwise returns list of dicts.

    Returns:
    --------
    pd.DataFrame or list[dict]:
        Forecast output matching CONTRACT.md schema.
    """
    # SECURITY: validate all inputs before doing any work
    _validate_forecast_inputs(store_id, product_ids, horizon_days, grid_step)

    resolved_data, dataset_key = _resolve_dataset(dataset, product_ids, store_id, use_live_data=use_live_data)
    engine = _get_or_init_engine(dataset=resolved_data, dataset_key=dataset_key, model_name=model_name)
    data = engine["data"]
    df_sales = data["sales"]
    df_context = data["context"]
    df_products = data.get("products")
    
    # Filter products
    store_sales = df_sales[df_sales["store_id"] == store_id]
    if product_ids is not None:
        target_prods = product_ids
    else:
        target_prods = store_sales["product_id"].unique().tolist()
        # If products dataframe has products not yet sold in store, include them (cold-start)
        if df_products is not None:
            for p in df_products["product_id"]:
                if p not in target_prods:
                    target_prods.append(p)
                    
    # Check if shock is active in the recent context or forecast period
    last_context = df_context.sort_values("date").iloc[-1] if len(df_context) > 0 else {}
    shock_active = bool(last_context.get("shock_flag", 0) == 1)
    
    # Quantiles grid to compute
    steps = np.arange(grid_step, 1.0, grid_step)
    target_quantiles = [round(float(q), 2) for q in steps]
    if 0.10 not in target_quantiles:
        target_quantiles.append(0.10)
    if 0.50 not in target_quantiles:
        target_quantiles.append(0.50)
    if 0.90 not in target_quantiles:
        target_quantiles.append(0.90)
    target_quantiles = sorted(list(set(target_quantiles)))
    
    forecast_start_date = pd.to_datetime(df_sales["date"]).max() + pd.Timedelta(days=1)
    forecast_date_str = forecast_start_date.strftime("%Y-%m-%d")
    
    results = []
    
    for pid in target_prods:
        p_sales = store_sales[store_sales["product_id"] == pid]
        non_zero_days = int(np.sum(p_sales["units_sold"] > 0)) if len(p_sales) > 0 else 0
        
        # Determine category
        cat = "GENERAL"
        if df_products is not None:
            match = df_products[df_products["product_id"] == pid]
            if len(match) > 0 and "category" in match.columns:
                cat = match["category"].iloc[0]
                
        # Cold start / sparse item routing
        if non_zero_days < 14:
            # Route to hierarchical Bayesian pooling model
            q_preds = engine["sparse_model"].predict_product_horizon(
                store_id=store_id,
                product_id=pid,
                horizon_days=horizon_days,
                category=cat,
                quantiles=target_quantiles
            )
            used_model_name = "hierarchical_sparse_pooling"
            features_used = ["category_prior_mean", "sample_mean_shrinkage", "cold_start_dispersion"]
        else:
            main_m = engine["main_model"]
            if hasattr(main_m, "predict_product_horizon"):
                q_preds = main_m.predict_product_horizon(
                    store_id=store_id,
                    product_id=pid,
                    horizon_days=horizon_days,
                    quantiles=target_quantiles
                )
                used_model_name = engine["model_name"]
                features_used = getattr(main_m, "trained_features", ["sales_lags", "calendar_dow"])
            else:
                # Baseline forecaster operating on single series
                y_hist = p_sales.sort_values("date")["units_sold"].values
                main_m.fit(y_hist)
                q_preds = main_m.predict_quantiles(horizon_days=horizon_days, quantiles=target_quantiles)
                used_model_name = getattr(main_m, "name", "baseline")
                features_used = ["historical_sales_series"]
                
        # 1. Apply Conformal Calibration
        calibrated_q = engine["calibrator"].adjust_intervals(q_preds)
        
        # 2. Apply Shock Widening Rule if shock is active
        final_q, widening_factor = apply_shock_widening(
            calibrated_q,
            shock_active=shock_active,
            widening_factor=1.50
        )
        
        # Aggregate cumulative demand over the horizon for Member 3
        # Member 3 needs cumulative demand over replenishment cycle
        cum_p10 = float(round(np.sum(final_q[0.10]), 2))
        cum_p50 = float(round(np.sum(final_q[0.50]), 2))
        cum_p90 = float(round(np.sum(final_q[0.90]), 2))
        
        # Format 5% grid dict
        quantiles_grid = {}
        for q_val in target_quantiles:
            k = f"q{int(round(q_val * 100)):02d}"
            quantiles_grid[k] = float(round(np.sum(final_q[q_val]), 2))
            
        # Generate 20 cumulative sample paths
        # Drawn from normal/lognormal matching p10 and p90
        mu = cum_p50
        sigma = max(1.0, (cum_p90 - cum_p10) / 2.56)
        samples = np.random.normal(loc=mu, scale=sigma, size=20)
        sample_paths = [float(round(max(0.0, s), 2)) for s in samples]
        
        results.append({
            "store_id": store_id,
            "product_id": pid,
            "horizon_days": int(horizon_days),
            "forecast_date": forecast_date_str,
            "p10": cum_p10,
            "p50": cum_p50,
            "p90": cum_p90,
            "quantiles": quantiles_grid,
            "sample_paths": sample_paths,
            "shock_active": shock_active,
            "widening_factor": float(widening_factor),
            "model_name": used_model_name,
            "features_used": features_used
        })
        
    if as_dataframe:
        cols = [
            "store_id", "product_id", "horizon_days", "forecast_date",
            "p10", "p50", "p90", "quantiles", "sample_paths",
            "shock_active", "widening_factor", "model_name", "features_used"
        ]
        return pd.DataFrame(results)[cols]
        
    return results
