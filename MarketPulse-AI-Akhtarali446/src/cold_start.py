"""
src/cold_start.py
Demographic store clustering using scikit-learn KMeans and prior profile generation 
for cold-start stores (<14 days history).
"""

import pandas as pd
import numpy as np
from sklearn.preprocessing import OneHotEncoder
from sklearn.cluster import KMeans


def generate_cold_start_priors_kmeans(
    sales_df: pd.DataFrame, 
    stores_df: pd.DataFrame, 
    n_clusters: int = 2,
    min_history_days: int = 14
) -> pd.DataFrame:
    """
    Uses scikit-learn OneHotEncoder + KMeans to cluster stores based on demographic metadata,
    and calculates cluster-level item prior demand profiles for cold-start stores.
    """
    store_history = (
        sales_df.groupby("store_id")["date"]
        .agg(min_date="min", max_date="max")
        .reset_index()
    )
    store_history["history_days"] = (store_history["max_date"] - store_history["min_date"]).dt.days + 1

    store_meta = pd.merge(stores_df, store_history, on="store_id", how="left").fillna({"history_days": 0})

    established_stores = store_meta[store_meta["history_days"] >= min_history_days]["store_id"].tolist()
    cold_start_stores = store_meta[store_meta["history_days"] < min_history_days]["store_id"].tolist()

    feature_cols = ["location_type", "population_class", "region_id"]
    encoder = OneHotEncoder(sparse_output=False)
    encoded_features = encoder.fit_transform(store_meta[feature_cols])

    actual_clusters = min(n_clusters, len(store_meta))
    kmeans = KMeans(n_clusters=actual_clusters, random_state=42, n_init=10)
    store_meta["cluster_id"] = kmeans.fit_predict(encoded_features)

    established_sales = sales_df[sales_df["store_id"].isin(established_stores)].merge(
        store_meta[["store_id", "cluster_id"]], on="store_id"
    )

    if established_sales.empty:
        return sales_df.groupby("item_id")["sales_quantity"].mean().reset_index().rename(
            columns={"sales_quantity": "prior_sales_quantity"}
        )

    cluster_priors = (
        established_sales.groupby(["cluster_id", "item_id"])["sales_quantity"]
        .mean()
        .reset_index()
        .rename(columns={"sales_quantity": "prior_sales_quantity"})
    )

    return cluster_priors


# Backward compatibility alias
def generate_cold_start_priors(sales_df: pd.DataFrame, stores_df: pd.DataFrame, min_history_days: int = 14) -> pd.DataFrame:
    return generate_cold_start_priors_kmeans(sales_df, stores_df, min_history_days=min_history_days)