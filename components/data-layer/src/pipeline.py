"""
src/pipeline.py
Production-grade ML feature engineering pipeline:
- Continuous calendar reindexing & stockout flagging
- Outlier Winsorization / IQR Capping
- Cyclical Sine/Cosine Calendar Encodings
- Price Elasticity & Discount Ratios
- EWMA & Shifted Rolling Statistics
- Time-based Splits
"""

from typing import List, Tuple
import pandas as pd
import numpy as np

from src.canonical_schemas import validate_dataframe


def clean_sales_data(df: pd.DataFrame) -> pd.DataFrame:
    validated = validate_dataframe(df, "sales")
    cleaned = validated.drop_duplicates(subset=["date", "store_id", "item_id"], keep="last")
    cleaned["sales_quantity"] = cleaned["sales_quantity"].clip(lower=0.0)
    return cleaned.sort_values(["store_id", "item_id", "date"]).reset_index(drop=True)


def reindex_continuous_dates(df: pd.DataFrame) -> pd.DataFrame:
    df = clean_sales_data(df)
    min_date = df["date"].min()
    max_date = df["date"].max()
    full_date_range = pd.date_range(start=min_date, end=max_date, freq="D")
    
    reindexed_groups = []
    for (store_id, item_id), group in df.groupby(["store_id", "item_id"]):
        group = group.set_index("date").reindex(full_date_range)
        group["store_id"] = store_id
        group["item_id"] = item_id
        group["sales_quantity"] = group["sales_quantity"].fillna(0.0)
        group["on_promotion"] = group["on_promotion"].fillna(False).astype(bool)
        group["price"] = group["price"].ffill().bfill()
        reindexed_groups.append(group.reset_index().rename(columns={"index": "date"}))
        
    return pd.concat(reindexed_groups, ignore_index=True).sort_values(["store_id", "item_id", "date"]).reset_index(drop=True)


def flag_stockouts(df: pd.DataFrame) -> pd.DataFrame:
    res = df.copy()
    res["is_stockout"] = res["sales_quantity"] == 0.0
    return res


def cap_outliers_iqr(df: pd.DataFrame, factor: float = 3.0) -> pd.DataFrame:
    """Caps extreme sales spikes above Q3 + factor * IQR per item."""
    res = df.copy()
    non_zero = res[res["sales_quantity"] > 0]
    
    q25 = non_zero.groupby("item_id")["sales_quantity"].transform(lambda x: x.quantile(0.25))
    q75 = non_zero.groupby("item_id")["sales_quantity"].transform(lambda x: x.quantile(0.75))
    iqr = q75 - q25
    upper_bound = q75 + (factor * iqr)
    
    res = res.merge(upper_bound.rename("upper_bound"), left_index=True, right_index=True, how="left")
    res["upper_bound"] = res["upper_bound"].fillna(res["sales_quantity"].max())
    res["sales_quantity_capped"] = np.minimum(res["sales_quantity"], res["upper_bound"])
    res = res.drop(columns=["upper_bound"])
    return res


def add_cyclical_calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    """Computes sin/cos transformations for day of week, day of year, and month."""
    res = df.copy()
    
    dow = res["date"].dt.dayofweek
    doy = res["date"].dt.dayofyear
    month = res["date"].dt.month

    res["sin_dow"] = np.sin(2 * np.pi * dow / 7.0)
    res["cos_dow"] = np.cos(2 * np.pi * dow / 7.0)

    res["sin_doy"] = np.sin(2 * np.pi * doy / 365.25)
    res["cos_doy"] = np.cos(2 * np.pi * doy / 365.25)

    res["sin_month"] = np.sin(2 * np.pi * month / 12.0)
    res["cos_month"] = np.cos(2 * np.pi * month / 12.0)

    return res


def add_price_features(df: pd.DataFrame) -> pd.DataFrame:
    """Computes price ratios, discount depth, and rolling price statistics."""
    res = df.sort_values(["store_id", "item_id", "date"]).copy()
    
    # 14-day rolling historical average price (shifted by 1)
    shifted_price = res.groupby(["store_id", "item_id"])["price"].shift(1)
    res["price_roll_mean_14"] = (
        shifted_price.groupby([res["store_id"], res["item_id"]])
        .transform(lambda x: x.rolling(14, min_periods=1).mean())
    )
    
    # Price Ratio & Elasticity Signals
    res["price_ratio"] = res["price"] / (res["price_roll_mean_14"] + 1e-5)
    res["discount_depth"] = np.where(
        res["on_promotion"], 
        1.0 - (res["price"] / (res["price_roll_mean_14"] + 1e-5)), 
        0.0
    )
    
    return res


def add_lag_and_rolling_features(
    df: pd.DataFrame, 
    lags: List[int] = [1, 7, 14, 28], 
    rolling_windows: List[int] = [7, 14, 28]
) -> pd.DataFrame:
    """
    Computes leakage-free lags, EWMA, and rolling statistics.
    """
    res = df.sort_values(["store_id", "item_id", "date"]).copy()

    # Determine target series (use capped sales if available)
    target_col = "sales_quantity_capped" if "sales_quantity_capped" in res.columns else "sales_quantity"

    # 1. Lags
    for lag in lags:
        res[f"sales_lag_{lag}"] = (
            res.groupby(["store_id", "item_id"])[target_col].shift(lag)
        )

    # Shift target by 1 day to ensure zero leakage for rolling stats
    shifted_target = res.groupby(["store_id", "item_id"])[target_col].shift(1)

    # 2. Rolling Statistics
    for window in rolling_windows:
        res[f"sales_roll_mean_{window}"] = (
            shifted_target.groupby([res["store_id"], res["item_id"]])
            .transform(lambda x: x.rolling(window, min_periods=1).mean())
        )
        res[f"sales_roll_std_{window}"] = (
            shifted_target.groupby([res["store_id"], res["item_id"]])
            .transform(lambda x: x.rolling(window, min_periods=1).std())
        ).fillna(0.0)

    # 3. Exponentially Weighted Moving Average (EWMA)
    for span in [7, 14]:
        res[f"sales_ewma_{span}"] = (
            shifted_target.groupby([res["store_id"], res["item_id"]])
            .transform(lambda x: x.ewm(span=span, min_periods=1).mean())
        )

    return res


def time_based_split(
    df: pd.DataFrame, 
    train_ratio: float = 0.7, 
    val_ratio: float = 0.15
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    sorted_df = df.sort_values("date").reset_index(drop=True)
    unique_dates = sorted_df["date"].drop_duplicates().sort_values().tolist()

    n_dates = len(unique_dates)
    train_end_idx = int(n_dates * train_ratio)
    val_end_idx = int(n_dates * (train_ratio + val_ratio))

    train_dates = set(unique_dates[:train_end_idx])
    val_dates = set(unique_dates[train_end_idx:val_end_idx])
    test_dates = set(unique_dates[val_end_idx:])

    train_df = sorted_df[sorted_df["date"].isin(train_dates)].copy()
    val_df = sorted_df[sorted_df["date"].isin(val_dates)].copy()
    test_df = sorted_df[sorted_df["date"].isin(test_dates)].copy()

    return train_df, val_df, test_df