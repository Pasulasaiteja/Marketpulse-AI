from pathlib import Path
import pandas as pd
from src.loader import load_dataset
from src.canonical_schemas import pivot_context
from src.pipeline import (
    reindex_continuous_dates,
    flag_stockouts,
    cap_outliers_iqr,
    add_cyclical_calendar_features,
    add_price_features,
    add_lag_and_rolling_features,
)
from src.cold_start import generate_cold_start_priors_kmeans

# 1. Load raw tables
sales, stores, items, context = load_dataset("synthetic")

# 2. Build full feature matrix
clean_df = reindex_continuous_dates(sales)
flagged_df = flag_stockouts(clean_df)
capped_df = cap_outliers_iqr(flagged_df)
calendar_df = add_cyclical_calendar_features(capped_df)
price_df = add_price_features(calendar_df)
feature_matrix = add_lag_and_rolling_features(price_df)
wide_context = pivot_context(context)

full_ml_matrix = pd.merge(feature_matrix, wide_context, on=["date", "store_id"], how="left")
cold_start_priors = generate_cold_start_priors_kmeans(sales, stores)

# 3. Save to the shared repository dataset directory (repo_root/data/processed)
out_dir = Path(__file__).resolve().parents[2] / "data" / "processed"
out_dir.mkdir(parents=True, exist_ok=True)

full_ml_matrix.to_csv(out_dir / "full_ml_feature_matrix.csv", index=False)
stores.to_csv(out_dir / "stores_metadata.csv", index=False)
items.to_csv(out_dir / "items_catalog.csv", index=False)
cold_start_priors.to_csv(out_dir / "cold_start_priors.csv", index=False)

print("Export complete! Files saved to the shared data/processed/ directory")