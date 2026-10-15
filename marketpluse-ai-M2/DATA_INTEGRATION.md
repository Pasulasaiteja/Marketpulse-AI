# MarketPulse AI - Data Integration & Live Datasets Guide

**Module:** Member 2 — Demand Forecasting & Market Signals  
**Status:** Live Upstream Integration Completed & Fully Verified (20/20 Tests Passing)  

---

## 1. Overview of Ingested Member 1 Datasets

The forecasting and market signals engine now seamlessly ingests Member 1's real upstream retail datasets located in `data/`:

| Dataset File | File Size / Record Count | Description & Scope |
|---|---|---|
| **`data/full_ml_feature_matrix.csv`** | **28.3 MB**<br>73,000 rows | Complete 1-year historical dataset (2025-01-01 to 2025-12-31) spanning **10 stores** (`STORE_001` to `STORE_010`) and **20 items** (`ITEM_001` to `ITEM_020`). Contains daily sales quantities, prices, promotions, stockouts, calendar cyclical features, weather, and engineered lags/rolling features. |
| **`data/items_catalog.csv`** | 20 items | Item master catalog linking `item_id` to `category_id` (`CAT_1`–`CAT_4`), unit cost price, selling price, supplier ID, and lead time in days. |
| **`data/stores_metadata.csv`** | 10 stores | Retail store topology, store names, location types (`rural_kiosk`, `urban_flagship`), population densities, and geographic regions. |
| **`data/cold_start_priors.csv`** | 40 priors | Cluster-level Bayesian prior demand quantities across item clusters. |

---

## 2. Schema Normalization & Mapping

The adapter in [`forecasting/data_loader.py`](forecasting/data_loader.py) normalizes Member 1's schema into the shared contract format:

### Sales Data Mapping
* `item_id` ➔ mapped to `product_id` (and aliased as `item_id` for dual compatibility)
* `sales_quantity` ➔ mapped to `units_sold`
* `on_promotion` ➔ normalized as boolean flag
* `category_id` from catalog ➔ merged as `category` (`CAT_1`, `CAT_2`, `CAT_3`, `CAT_4`)

### Context & Shock Mapping
* `is_payday` ➔ `payday_flag` (1 or 0)
* `is_festival` ➔ `holiday_flag` (1 or 0)
* `is_stockout` ➔ `shock_flag` (1 or 0) with `shock_type = "STOCKOUT_ALERT"`
* `temperature_c` & `is_rain` ➔ weather context
* `sin_dow`, `cos_dow`, `sin_month`, `cos_month` ➔ calendar cyclic features

### Products & Margins Mapping
* Unit profit margin: $\text{Margin} = \text{selling\_price} - \text{cost\_price}$
* Replenishment cycle: `lead_time_days` (3 to 7 days)
* Supplier accountability: `supplier_id`

---

## 3. How to Use Live Data in `forecast()`

### Automatic Routing
When you request any product from Member 1 (e.g. `ITEM_001`, `ITEM_002`):
```python
from forecasting import forecast

# Automatically routes to data/full_ml_feature_matrix.csv
df = forecast(
    store_id="STORE_001",
    product_ids=["ITEM_001", "ITEM_002", "ITEM_003"],
    horizon_days=14,
    grid_step=0.05
)

print(df[["store_id", "product_id", "p10", "p50", "p90", "shock_active"]])
```

### Explicit Selection
You can explicitly force live data or mock data via `use_live_data`:
```python
# Force live dataset on all active products in STORE_002:
df_live = forecast(store_id="STORE_002", horizon_days=14, use_live_data=True)

# Force legacy mock data:
df_mock = forecast(store_id="STORE_001", product_ids=["PROD_MILK_1L"], use_live_data=False)
```

---

## 4. Test Verification Summary

The live data loader is verified by dedicated unit tests in [`tests/test_live_data_loader.py`](tests/test_live_data_loader.py):

```
tests/test_live_data_loader.py::test_has_live_dataset_detection PASSED   [ 25%]
tests/test_live_data_loader.py::test_load_live_dataset_structure_and_types PASSED [ 50%]
tests/test_live_data_loader.py::test_forecast_api_with_live_dataset PASSED [ 75%]
tests/test_live_data_loader.py::test_forecast_backwards_compatibility_mock_data PASSED [100%]
```

The entire repository test suite (**20/20 tests**) passes cleanly.
