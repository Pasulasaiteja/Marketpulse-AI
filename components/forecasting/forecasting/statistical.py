"""
Statistical Forecasting & Hierarchical Cold-Start Pooling Module.
Includes:
- HierarchicalBayesPoolingForecaster: Category prior pooling for sparse & cold-start products.
- AutoStatisticalForecaster: ETS / SARIMAX statistical model for stationary or seasonal series.
"""

import numpy as np
import pandas as pd
from scipy import stats
from .baselines import BaseForecaster


class HierarchicalBayesPoolingForecaster(BaseForecaster):
    """
    Hierarchical category pooling forecaster for sparse products and new store launches.
    Blends product-level history with category-level priors as documented in ASSUMPTIONS.md.
    """
    def __init__(
        self,
        min_history_threshold: int = 14,
        prior_cv: float = 0.65
    ):
        super().__init__(name="hierarchical_sparse_pooling")
        self.min_history_threshold = min_history_threshold
        self.prior_cv = prior_cv
        self.category_priors: dict[str, float] = {}
        self.store_cat_priors: dict[tuple[str, str], float] = {}
        self.product_stats: dict[tuple[str, str], dict[str, float]] = {}

    def fit(
        self,
        df_sales: pd.DataFrame,
        df_products: pd.DataFrame | None = None,
        **kwargs
    ) -> "HierarchicalBayesPoolingForecaster":
        """
        Fits category-level and store-category baseline priors.
        """
        df = df_sales.copy()
        
        # Merge category if not present
        if "category" not in df.columns and df_products is not None:
            df = df.merge(df_products[["product_id", "category"]], on="product_id", how="left")
            
        if "category" not in df.columns:
            df["category"] = "GENERAL"
            
        # 1. Global Category Priors (mean non-zero sales)
        cat_means = df[df["units_sold"] > 0].groupby("category")["units_sold"].mean().to_dict()
        overall_mean = df[df["units_sold"] > 0]["units_sold"].mean() if len(df[df["units_sold"] > 0]) > 0 else 10.0
        self.category_priors = {cat: float(val) for cat, val in cat_means.items()}
        self.overall_mean = float(overall_mean)
        
        # 2. Store-Category Priors
        store_cat_means = df[df["units_sold"] > 0].groupby(["store_id", "category"])["units_sold"].mean().to_dict()
        self.store_cat_priors = {(s, c): float(val) for (s, c), val in store_cat_means.items()}
        
        # 3. Product stats per store
        prod_grp = df.groupby(["store_id", "product_id"])
        for (store, prod), group in prod_grp:
            non_zero_days = int(np.sum(group["units_sold"] > 0))
            total_days = len(group)
            prod_mean = float(group["units_sold"].mean())
            cat = group["category"].iloc[0] if "category" in group.columns else "GENERAL"
            self.product_stats[(store, prod)] = {
                "non_zero_days": non_zero_days,
                "total_days": total_days,
                "mean": prod_mean,
                "category": cat
            }
            
        self.is_fitted = True
        return self

    def predict_product_horizon(
        self,
        store_id: str,
        product_id: str,
        horizon_days: int = 14,
        category: str | None = None,
        quantiles: list[float] = [0.10, 0.50, 0.90]
    ) -> dict[float, np.ndarray]:
        """
        Produces forecasts with honest, wide uncertainty for sparse / cold-start products.
        """
        if not self.is_fitted:
            raise RuntimeError("Model must be fitted before predict.")
            
        stats_info = self.product_stats.get((store_id, product_id))
        
        if stats_info is None:
            # Complete Cold Start: 0 days in history
            cat = category or "GENERAL"
            prior_mean = self.store_cat_priors.get((store_id, cat)) or self.category_priors.get(cat, self.overall_mean)
            mu_est = prior_mean * 0.40 # Cold start initial discount
            sigma_est = max(1.5, mu_est * self.prior_cv * 1.5) # Wide intervals
        else:
            cat = stats_info["category"]
            n = stats_info["non_zero_days"]
            sample_mean = stats_info["mean"]
            prior_mean = self.store_cat_priors.get((store_id, cat)) or self.category_priors.get(cat, self.overall_mean)
            
            if n >= self.min_history_threshold:
                mu_est = sample_mean
                sigma_est = max(1.0, 0.25 * mu_est)
            else:
                # Bayesian shrinkage: alpha = n / threshold
                alpha = n / float(self.min_history_threshold)
                mu_est = alpha * sample_mean + (1.0 - alpha) * (0.5 * prior_mean)
                sigma_est = max(1.5, mu_est * self.prior_cv)
                
        out_quantiles = {}
        for q in quantiles:
            z = stats.norm.ppf(q)
            h_factors = np.sqrt(1.0 + 0.05 * np.arange(horizon_days))
            q_arr = np.maximum(0.0, mu_est + z * sigma_est * h_factors)
            out_quantiles[q] = q_arr
            
        return out_quantiles


class AutoStatisticalForecaster(BaseForecaster):
    """
    Statistical model (AutoARIMA / ETS) for demand series.
    Provides robust parametric predictive distributions.
    """
    def __init__(self, seasonal_period: int = 7):
        super().__init__(name="statistical_ets_arima")
        self.seasonal_period = seasonal_period
        self.fitted_models: dict[tuple[str, str], Any] = {}

    def fit(self, df_sales: pd.DataFrame, **kwargs) -> "AutoStatisticalForecaster":
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
        df = df_sales.copy()
        for (store, prod), group in df.groupby(["store_id", "product_id"]):
            y = group.sort_values("date")["units_sold"].values
            if len(y) >= 2 * self.seasonal_period and np.sum(y > 0) > 10:
                try:
                    # ETS with additive season
                    model = ExponentialSmoothing(
                        np.maximum(1e-2, y),
                        seasonal_periods=self.seasonal_period,
                        trend="add",
                        seasonal="add",
                        initialization_method="estimated"
                    ).fit(optimized=True)
                    resid_std = float(np.std(model.fittedvalues - y))
                    self.fitted_models[(store, prod)] = (model, resid_std)
                except Exception:
                    self.fitted_models[(store, prod)] = (None, float(np.std(y)) if len(y) > 1 else 1.0)
            else:
                self.fitted_models[(store, prod)] = (None, float(np.std(y)) if len(y) > 1 else 1.0)
                
        self.is_fitted = True
        return self

    def predict_product_horizon(
        self,
        store_id: str,
        product_id: str,
        horizon_days: int = 14,
        quantiles: list[float] = [0.10, 0.50, 0.90]
    ) -> dict[float, np.ndarray]:
        if (store_id, product_id) not in self.fitted_models:
            return {q: np.zeros(horizon_days) for q in quantiles}
            
        model, resid_std = self.fitted_models[(store_id, product_id)]
        if model is not None:
            try:
                point_preds = np.asarray(model.forecast(horizon_days), dtype=float)
            except Exception:
                point_preds = np.zeros(horizon_days)
        else:
            point_preds = np.zeros(horizon_days)
            
        point_preds = np.maximum(0.0, point_preds)
        out_quantiles = {}
        for q in quantiles:
            z = stats.norm.ppf(q)
            h_factors = np.sqrt(1.0 + 0.05 * np.arange(horizon_days))
            out_quantiles[q] = np.maximum(0.0, point_preds + z * resid_std * h_factors)
            
        return out_quantiles
