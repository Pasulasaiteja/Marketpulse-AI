"""
Live Data Adapter & Loader for MarketPulse AI (Member 2).
Loads and aligns real upstream datasets produced by Member 1:
- data/full_ml_feature_matrix.csv (73,000 observations across 10 stores and 20 products)
- data/items_catalog.csv (Product categories, margins, supplier constraints)
- data/stores_metadata.csv (Store locations, population densities, regional taxonomy)
- data/cold_start_priors.csv (Bayesian cluster priors for cold-start and sparse forecasting)

Automatically maps schemas to match CONTRACT.md while retaining full backwards
compatibility with synthetic mock generators.
"""

from pathlib import Path
import os
import pandas as pd
import numpy as np
from typing import Any

# In-memory singleton cache to prevent reading large CSVs repeatedly
_LOADED_DATASET_CACHE: dict[str, Any] | None = None


def get_data_dir() -> Path:
    """
    Locates the directory containing Member 1 CSV datasets.
    Searches 'data/' relative to project root or current working directory.
    """
    # 1. Project root / data
    root_candidate = Path(__file__).resolve().parent.parent / "data"
    if root_candidate.is_dir() and (root_candidate / "full_ml_feature_matrix.csv").exists():
        return root_candidate

    # 2. Current working directory / data
    cwd_candidate = Path.cwd() / "data"
    if cwd_candidate.is_dir() and (cwd_candidate / "full_ml_feature_matrix.csv").exists():
        return cwd_candidate

    # 3. Direct working directory
    if (Path.cwd() / "full_ml_feature_matrix.csv").exists():
        return Path.cwd()

    return root_candidate


def has_live_dataset(data_dir: Path | str | None = None) -> bool:
    """
    Returns True if Member 1's live datasets are present on disk.
    """
    target_dir = Path(data_dir) if data_dir else get_data_dir()
    required = ["full_ml_feature_matrix.csv", "items_catalog.csv"]
    return all((target_dir / fname).exists() for fname in required)


def load_live_dataset(
    data_dir: Path | str | None = None,
    force_reload: bool = False
) -> dict[str, pd.DataFrame]:
    """
    Loads, joins, and normalizes Member 1's real CSV datasets.

    Returns:
    --------
    dict[str, pd.DataFrame] containing:
        - "sales": Historical sales with columns:
                   [date, store_id, product_id, item_id, units_sold, on_promotion, price, category]
        - "context": Macro, calendar, and shock features per date
        - "products": Product catalog, categories, pricing, and lead times
        - "stores": Store metadata, location types, regions
        - "priors": Cold start Bayesian cluster priors
        - "reviews": Feedback records for Component A NLP classification
    """
    global _LOADED_DATASET_CACHE

    if not force_reload and _LOADED_DATASET_CACHE is not None:
        return _LOADED_DATASET_CACHE

    target_dir = Path(data_dir) if data_dir else get_data_dir()
    if not has_live_dataset(target_dir):
        raise FileNotFoundError(
            f"Required live datasets not found in {target_dir}. "
            "Ensure full_ml_feature_matrix.csv and items_catalog.csv exist."
        )

    # 1. Load Items Catalog
    items_path = target_dir / "items_catalog.csv"
    df_items = pd.read_csv(items_path)
    df_items["product_id"] = df_items["item_id"]
    df_items["category"] = df_items["category_id"]

    # 2. Load Stores Metadata
    stores_path = target_dir / "stores_metadata.csv"
    if stores_path.exists():
        df_stores = pd.read_csv(stores_path)
    else:
        df_stores = pd.DataFrame()

    # 3. Load Cold-Start Priors
    priors_path = target_dir / "cold_start_priors.csv"
    if priors_path.exists():
        df_priors = pd.read_csv(priors_path)
        df_priors["product_id"] = df_priors["item_id"]
    else:
        df_priors = pd.DataFrame()

    # 4. Load Feature Matrix & Construct Sales DataFrame
    matrix_path = target_dir / "full_ml_feature_matrix.csv"
    df_matrix = pd.read_csv(matrix_path)

    # Map core sales fields
    df_sales = pd.DataFrame({
        "date": df_matrix["date"],
        "store_id": df_matrix["store_id"],
        "product_id": df_matrix["item_id"],
        "item_id": df_matrix["item_id"],
        "units_sold": df_matrix["sales_quantity"].astype(float),
        "on_promotion": df_matrix["on_promotion"].astype(bool),
        "price": df_matrix["price"].astype(float)
    })

    # Join category from items catalog
    df_sales = df_sales.merge(
        df_items[["item_id", "category"]],
        on="item_id",
        how="left"
    )
    df_sales["category"] = df_sales["category"].fillna("GENERAL")

    # Add product metadata base demand summary
    prod_summary = df_sales.groupby("product_id")["units_sold"].agg(["mean", "std"]).reset_index()
    prod_summary.columns = ["product_id", "base_demand", "sales_std"]
    df_products = df_items.merge(prod_summary, on="product_id", how="left")
    df_products["is_sparse"] = df_products["base_demand"] < 5.0

    # 5. Construct Context DataFrame
    context_cols = [
        col for col in ["date", "is_payday", "is_festival", "is_rain", "temperature_c", "is_stockout"]
        if col in df_matrix.columns
    ]
    df_context = df_matrix[context_cols].drop_duplicates(subset=["date"]).sort_values("date").copy()

    dt = pd.to_datetime(df_context["date"])
    df_context["day_of_week"] = dt.dt.dayofweek
    df_context["is_weekend"] = (dt.dt.dayofweek >= 5).astype(int)
    df_context["month"] = dt.dt.month
    df_context["day_of_month"] = dt.dt.day
    df_context["payday_flag"] = df_context["is_payday"].fillna(0).astype(int) if "is_payday" in df_context else 0
    df_context["holiday_flag"] = df_context["is_festival"].fillna(0).astype(int) if "is_festival" in df_context else 0
    df_context["shock_flag"] = df_context["is_stockout"].fillna(0).astype(int) if "is_stockout" in df_context else 0
    df_context["shock_type"] = np.where(df_context["shock_flag"] == 1, "STOCKOUT_ALERT", "NONE")
    df_context["inflation_index"] = 1.0
    df_context["fuel_price_index"] = 1.0

    # 6. Reviews dataset (if exists or synthetic generator matching actual products)
    reviews_path = target_dir / "reviews.csv"
    if reviews_path.exists():
        df_reviews = pd.read_csv(reviews_path)
    else:
        # Generate targeted reviews for actual item IDs so NLP pipeline is operational
        unique_items = df_items["item_id"].tolist()
        df_reviews = _generate_compatible_reviews(unique_items)

    dataset = {
        "sales": df_sales,
        "context": df_context,
        "products": df_products,
        "stores": df_stores,
        "priors": df_priors,
        "reviews": df_reviews
    }

    _LOADED_DATASET_CACHE = dataset
    return dataset


def _generate_compatible_reviews(item_ids: list[str]) -> pd.DataFrame:
    """
    Generates synthetic review records matching actual item IDs for Component A NLP testing.
    """
    records = []
    templates = [
        ("We urgently need more stock of {item}. It was completely sold out yesterday afternoon.", "NEED"),
        ("The quality of {item} has dropped noticeably and price went up.", "COMPLAINT"),
        ("Customers love the new packaging of {item}. High demand during weekends.", "PREFERENCE"),
        ("Standard daily restocking completed for {item}.", "NEUTRAL")
    ]
    
    for i, item in enumerate(item_ids[:10]):
        template, intent = templates[i % len(templates)]
        records.append({
            "review_id": f"REV_{i+1:04d}",
            "date": "2025-10-14",
            "store_id": "STORE_001",
            "product_or_category": item,
            "text": template.format(item=item),
            "ground_truth_intent": intent
        })
        
    return pd.DataFrame(records)
