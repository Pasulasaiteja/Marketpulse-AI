"""
src/loader.py
Unified dataset entrypoint supporting 'synthetic', 'synthetic_sparse', 'm5', and 'favorita'.
"""

from typing import Tuple
import pandas as pd

from src.synthetic_generator import generate_synthetic_data
from src.public_dataset_adapters import load_m5_subsampled, load_favorita_subsampled


def load_dataset(name: str = "synthetic") -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Unified entrypoint for loading datasets.
    Supported names: 'synthetic', 'synthetic_sparse', 'm5', 'favorita'
    Returns canonical DataFrames: (sales_df, stores_df, items_df, context_df)
    """
    name_clean = name.lower().strip()

    if name_clean == "synthetic":
        return generate_synthetic_data("config/synthetic_config.yaml")

    elif name_clean == "synthetic_sparse":
        sales_df, stores_df, items_df, context_df = generate_synthetic_data("config/synthetic_config.yaml")
        # Inject 30% random missing rows to simulate irregular manual logging
        sparse_sales = sales_df.sample(frac=0.7, random_state=42).sort_values(["store_id", "item_id", "date"]).reset_index(drop=True)
        return sparse_sales, stores_df, items_df, context_df

    elif name_clean == "m5":
        return load_m5_subsampled()

    elif name_clean == "favorita":
        return load_favorita_subsampled()

    else:
        raise ValueError(
            f"Unsupported dataset name '{name}'. "
            f"Must be one of ['synthetic', 'synthetic_sparse', 'm5', 'favorita']."
        )