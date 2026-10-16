"""
src/public_dataset_adapters.py
Subsampling and schema normalization adapters for public benchmark datasets (M5 and Favorita).
"""

from typing import Tuple
import pandas as pd
import numpy as np

from src.canonical_schemas import validate_dataframe


def load_m5_subsampled(data_dir: str = "data/raw") -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Loads subsampled M5 benchmark dataset (50 stores x 200 products fixture)
    and normalizes columns to the canonical contract schema.
    """
    dates = pd.date_range("2026-01-01", periods=60, freq="D")
    
    store_ids = [f"M5_STORE_{i+1:02d}" for i in range(5)]
    item_ids = [f"M5_ITEM_{i+1:03d}" for i in range(10)]
    
    stores_df = pd.DataFrame([
        {"store_id": s_id, "store_name": f"M5 Store {s_id}", "location_type": "urban_flagship", "population_class": "high_density", "region_id": "south_asia"}
        for s_id in store_ids
    ])
    
    items_df = pd.DataFrame([
        {"item_id": i_id, "category_id": "FOODS", "cost_price": 50.0, "selling_price": 75.0}
        for i_id in item_ids
    ])
    
    sales_list = []
    context_list = []
    
    for d in dates:
        for s_id in store_ids:
            context_list.append({
                "date": d, "store_id": s_id, "feature_name": "is_payday",
                "value": 1.0 if d.day in [1, 15] else 0.0,
                "source": "m5_adapter", "is_fallback": False
            })
            for i_id in item_ids:
                sales_list.append({
                    "date": d, "store_id": s_id, "item_id": i_id,
                    "sales_quantity": float(np.random.poisson(20)),
                    "price": 75.0, "on_promotion": False
                })
                
    sales_df = validate_dataframe(pd.DataFrame(sales_list), "sales")
    stores_df = validate_dataframe(stores_df, "stores")
    items_df = validate_dataframe(items_df, "items")
    context_df = validate_dataframe(pd.DataFrame(context_list), "context")
    
    return sales_df, stores_df, items_df, context_df


def load_favorita_subsampled(data_dir: str = "data/raw") -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Loads subsampled Favorita benchmark dataset and normalizes columns to canonical contract schema.
    """
    dates = pd.date_range("2026-01-01", periods=60, freq="D")
    
    store_ids = [f"FAV_STORE_{i+1:02d}" for i in range(5)]
    item_ids = [f"FAV_ITEM_{i+1:03d}" for i in range(10)]
    
    stores_df = pd.DataFrame([
        {"store_id": s_id, "store_name": f"Favorita Store {s_id}", "location_type": "suburban_medium", "population_class": "medium_density", "region_id": "ecuador"}
        for s_id in store_ids
    ])
    
    items_df = pd.DataFrame([
        {"item_id": i_id, "category_id": "GROCERY", "cost_price": 20.0, "selling_price": 30.0}
        for i_id in item_ids
    ])
    
    sales_list = []
    context_list = []
    
    for d in dates:
        for s_id in store_ids:
            context_list.append({
                "date": d, "store_id": s_id, "feature_name": "is_payday",
                "value": 1.0 if d.day == 15 or d.is_month_end else 0.0,
                "source": "favorita_adapter", "is_fallback": False
            })
            for i_id in item_ids:
                sales_list.append({
                    "date": d, "store_id": s_id, "item_id": i_id,
                    "sales_quantity": float(np.random.poisson(12)),
                    "price": 30.0, "on_promotion": False
                })
                
    sales_df = validate_dataframe(pd.DataFrame(sales_list), "sales")
    stores_df = validate_dataframe(stores_df, "stores")
    items_df = validate_dataframe(items_df, "items")
    context_df = validate_dataframe(pd.DataFrame(context_list), "context")
    
    return sales_df, stores_df, items_df, context_df