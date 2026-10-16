"""
Gradient-Boosted Quantile Regressor for Demand Forecasting.
Builds lagged sales, rolling statistics, and calendar features.
Fits LightGBM models with quantile loss for p10, p50, p90, and full quantile grids.
Enforces non-negativity and quantile monotonicity.
"""

import numpy as np
import pandas as pd
from typing import Any
import lightgbm as lgb
from .baselines import BaseForecaster


class FeatureBuilder:
    """
    Constructs time-series features with zero leakage.
    Supports lag features, rolling statistics, calendar indicators, and context features.
    """
    def __init__(
        self,
        lags: list[int] = [1, 7, 14, 28],
        windows: list[int] = [7, 14, 28],
        include_calendar: bool = True,
        include_economic: bool = False,
        include_shocks: bool = False,
        include_signals: bool = False
    ):
        self.lags = lags
        self.windows = windows
        self.include_calendar = include_calendar
        self.include_economic = include_economic
        self.include_shocks = include_shocks
        self.include_signals = include_signals
        self.feature_cols: list[str] = []

    def transform(
        self,
        df_sales: pd.DataFrame,
        df_context: pd.DataFrame | None = None,
        signals_df: pd.DataFrame | None = None
    ) -> pd.DataFrame:
        """
        Transforms raw daily sales and context into an ML feature matrix.
        Assumes df_sales contains: date, store_id, product_id, units_sold.
        """
        df = df_sales.copy()
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values(["store_id", "product_id", "date"]).reset_index(drop=True)
        
        # 1. Autoregressive Lags & Rolling features grouped by store & product
        feature_cols = []
        for lag in self.lags:
            col_name = f"lag_{lag}"
            df[col_name] = df.groupby(["store_id", "product_id"])["units_sold"].shift(lag)
            feature_cols.append(col_name)
            
        for w in self.windows:
            mean_col = f"rolling_mean_{w}"
            std_col = f"rolling_std_{w}"
            # Shift by 1 to ensure no target leakage in rolling window!
            shifted = df.groupby(["store_id", "product_id"])["units_sold"].shift(1)
            df[mean_col] = shifted.groupby([df["store_id"], df["product_id"]]).rolling(w, min_periods=1).mean().reset_index(drop=True)
            df[std_col] = shifted.groupby([df["store_id"], df["product_id"]]).rolling(w, min_periods=1).std().reset_index(drop=True).fillna(0.0)
            feature_cols.extend([mean_col, std_col])
            
        # 2. Calendar features
        if self.include_calendar:
            df["day_of_week"] = df["date"].dt.dayofweek
            df["is_weekend"] = df["day_of_week"].isin([5, 6]).astype(int)
            df["day_of_month"] = df["date"].dt.day
            df["month"] = df["date"].dt.month
            
            # Context features from df_context if provided
            if df_context is not None:
                ctx = df_context.copy()
                ctx["date"] = pd.to_datetime(ctx["date"])
                merge_cols = ["date"]
                if "payday_flag" in ctx.columns:
                    merge_cols.append("payday_flag")
                if "holiday_flag" in ctx.columns:
                    merge_cols.append("holiday_flag")
                    
                df = df.merge(ctx[merge_cols], on="date", how="left")
                df["payday_flag"] = df["payday_flag"].fillna(0).astype(int)
                df["holiday_flag"] = df["holiday_flag"].fillna(0).astype(int)
                feature_cols.extend(["day_of_week", "is_weekend", "day_of_month", "month", "payday_flag", "holiday_flag"])
            else:
                # Derive approximate payday
                df["payday_flag"] = ((df["day_of_month"] >= 27) | (df["day_of_month"] <= 2)).astype(int)
                df["holiday_flag"] = 0
                feature_cols.extend(["day_of_week", "is_weekend", "day_of_month", "month", "payday_flag", "holiday_flag"])
                
        # 3. Macro / Economic features
        if self.include_economic and df_context is not None:
            ctx = df_context.copy()
            ctx["date"] = pd.to_datetime(ctx["date"])
            econ_cols = [c for c in ["inflation_index", "fuel_price_index"] if c in ctx.columns]
            if econ_cols:
                df = df.merge(ctx[["date"] + econ_cols], on="date", how="left")
                for ec in econ_cols:
                    df[ec] = df[ec].bfill().ffill().fillna(100.0)
                feature_cols.extend(econ_cols)
                
        # 4. Shock features
        if self.include_shocks and df_context is not None:
            ctx = df_context.copy()
            ctx["date"] = pd.to_datetime(ctx["date"])
            if "shock_flag" in ctx.columns:
                df = df.merge(ctx[["date", "shock_flag"]], on="date", how="left")
                df["shock_flag"] = df["shock_flag"].fillna(0).astype(int)
                feature_cols.append("shock_flag")
                
        # 5. Market signals features
        if self.include_signals:
            if signals_df is not None and not signals_df.empty:
                sig = signals_df.copy()
                sig["date"] = pd.to_datetime(sig["date"])
                # Create a signal intensity feature per product
                sig_counts = sig.groupby(["date", "product_or_category"]).agg(
                    signal_count=("signal_id", "count"),
                    signal_conf_mean=("confidence", "mean")
                ).reset_index()
                sig_counts.rename(columns={"product_or_category": "product_id"}, inplace=True)
                df = df.merge(sig_counts, on=["date", "product_id"], how="left")
                df["signal_count"] = df["signal_count"].fillna(0)
                df["signal_conf_mean"] = df["signal_conf_mean"].fillna(0.0)
            else:
                df["signal_count"] = 0
                df["signal_conf_mean"] = 0.0
            feature_cols.extend(["signal_count", "signal_conf_mean"])

        self.feature_cols = feature_cols
        return df


class GradientBoostedQuantileForecaster(BaseForecaster):
    """
    LightGBM Quantile Regressor trained across pinball loss quantiles (e.g. 0.10, 0.50, 0.90).
    Features direct multi-step / recursive forecasting for arbitrary horizons.
    """
    def __init__(
        self,
        quantiles: list[float] = [0.10, 0.50, 0.90],
        feature_builder: FeatureBuilder | None = None,
        n_estimators: int = 80,
        learning_rate: float = 0.05,
        max_depth: int = 5,
        num_leaves: int = 31,
        seed: int = 42
    ):
        super().__init__(name="gb_quantile_lgbm")
        self.quantiles = sorted(quantiles)
        self.feature_builder = feature_builder or FeatureBuilder()
        self.n_estimators = n_estimators
        self.learning_rate = learning_rate
        self.max_depth = max_depth
        self.num_leaves = num_leaves
        self.seed = seed
        self.models: dict[float, lgb.LGBMRegressor] = {}
        self.trained_features: list[str] = []
        self.last_sales_data: pd.DataFrame | None = None
        self.last_context_data: pd.DataFrame | None = None

    def fit(
        self,
        df_sales: pd.DataFrame,
        df_context: pd.DataFrame | None = None,
        signals_df: pd.DataFrame | None = None,
        **kwargs
    ) -> "GradientBoostedQuantileForecaster":
        """
        Fits quantile models on historical feature matrix.
        """
        self.last_sales_data = df_sales.copy()
        self.last_context_data = df_context.copy() if df_context is not None else None
        self.last_signals_df = signals_df.copy() if signals_df is not None else None
        
        feature_df = self.feature_builder.transform(df_sales, df_context, signals_df)
        feature_cols = self.feature_builder.feature_cols
        self.trained_features = feature_cols
        
        # Drop rows with NaN in features (due to longest lag 28)
        valid_df = feature_df.dropna(subset=feature_cols + ["units_sold"]).copy()
        if len(valid_df) < 20:
            # Insufficient history for complex GBDT; will fit on available data with smaller lag
            valid_df = feature_df.dropna(subset=["lag_1", "rolling_mean_7", "units_sold"]).copy()
            feature_cols = [c for c in feature_cols if c in valid_df.columns and not valid_df[c].isna().any()]
            self.trained_features = feature_cols

        X = valid_df[feature_cols].values
        y = valid_df["units_sold"].values
        
        for q in self.quantiles:
            model = lgb.LGBMRegressor(
                objective="quantile",
                alpha=q,
                n_estimators=self.n_estimators,
                learning_rate=self.learning_rate,
                max_depth=self.max_depth,
                num_leaves=self.num_leaves,
                random_state=self.seed,
                verbose=-1
            )
            model.fit(X, y)
            self.models[q] = model
            
        self.is_fitted = True
        return self

    def predict_product_horizon(
        self,
        store_id: str,
        product_id: str,
        horizon_days: int = 14,
        df_context_future: pd.DataFrame | None = None,
        quantiles: list[float] | None = None
    ) -> dict[float, np.ndarray]:
        """
        Generates recursive multi-step forecasts for the given store and product.
        Enforces quantile monotonicity (q10 <= q50 <= q90).
        """
        if not self.is_fitted:
            raise RuntimeError("Model must be fitted before predict.")
            
        eval_quantiles = sorted(quantiles) if quantiles is not None else self.quantiles
        
        # Filter store & product history
        prod_sales = self.last_sales_data[
            (self.last_sales_data["store_id"] == store_id) &
            (self.last_sales_data["product_id"] == product_id)
        ].copy()
        prod_sales["date"] = pd.to_datetime(prod_sales["date"])
        prod_sales = prod_sales.sort_values("date").reset_index(drop=True)
        
        if len(prod_sales) == 0:
            # Fallback zero
            return {q: np.zeros(horizon_days) for q in eval_quantiles}
            
        # Recursive prediction loop
        current_history = prod_sales[["date", "store_id", "product_id", "units_sold"]].copy()
        last_date = current_history["date"].max()
        
        p50_preds = []
        p10_preds = []
        p90_preds = []
        
        for step in range(1, horizon_days + 1):
            next_date = last_date + pd.Timedelta(days=step)
            
            # Append placeholder row for next_date
            placeholder = pd.DataFrame([{
                "date": next_date,
                "store_id": store_id,
                "product_id": product_id,
                "units_sold": np.nan
            }])
            extended = pd.concat([current_history, placeholder], ignore_index=True)
            
            # Generate features
            feat_df = self.feature_builder.transform(
                extended,
                df_context=self.last_context_data if df_context_future is None else pd.concat([self.last_context_data, df_context_future]),
                signals_df=self.last_signals_df
            )
            
            # Extract feature vector for next_date
            row_feat = feat_df[feat_df["date"] == next_date][self.trained_features].values
            
            # Predict p50 for recursive lag update
            pred_p50 = float(self.models[0.50].predict(row_feat)[0]) if 0.50 in self.models else float(np.mean([self.models[q].predict(row_feat)[0] for q in self.models]))
            pred_p50 = max(0.0, pred_p50)
            
            # Predict other quantiles
            step_q = {}
            for q in self.models:
                val = max(0.0, float(self.models[q].predict(row_feat)[0]))
                step_q[q] = val
                
            # Monotonicity adjustment
            q_keys = sorted(step_q.keys())
            for i in range(1, len(q_keys)):
                if step_q[q_keys[i]] < step_q[q_keys[i - 1]]:
                    step_q[q_keys[i]] = step_q[q_keys[i - 1]]
                    
            p50_preds.append(step_q.get(0.50, pred_p50))
            p10_preds.append(step_q.get(0.10, max(0.0, pred_p50 * 0.7)))
            p90_preds.append(step_q.get(0.90, pred_p50 * 1.35))
            
            # Update history with median prediction for subsequent lags
            placeholder["units_sold"] = pred_p50
            current_history = pd.concat([current_history, placeholder], ignore_index=True)

        res = {
            0.10: np.array(p10_preds),
            0.50: np.array(p50_preds),
            0.90: np.array(p90_preds)
        }
        
        # If user asked for full 5% grid, interpolate across quantiles
        if eval_quantiles != [0.10, 0.50, 0.90]:
            grid_res = {}
            for target_q in eval_quantiles:
                if target_q in res:
                    grid_res[target_q] = res[target_q]
                elif target_q < 0.10:
                    scale = target_q / 0.10
                    grid_res[target_q] = np.maximum(0.0, res[0.10] * scale)
                elif target_q < 0.50:
                    alpha = (target_q - 0.10) / 0.40
                    grid_res[target_q] = res[0.10] + alpha * (res[0.50] - res[0.10])
                elif target_q < 0.90:
                    alpha = (target_q - 0.50) / 0.40
                    grid_res[target_q] = res[0.50] + alpha * (res[0.90] - res[0.50])
                else: # target_q >= 0.90
                    extra = (target_q - 0.90) / 0.10
                    grid_res[target_q] = res[0.90] + extra * 0.25 * (res[0.90] - res[0.50])
            return grid_res

        return res
