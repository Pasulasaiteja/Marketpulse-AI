# Shared Contracts & API Specification

**Module:** Member 2 — Demand Forecasting & Market Signals (Components A & B)  
**Status:** Frozen for Team Integration  
**Upstream Consumer:** Member 1 (Datasets, Synthetic Priors, Context Features)  
**Downstream Consumer:** Member 3 (Inventory Optimization Engine)  
**Configuration & Orchestration:** Member 5 (System Pipeline & Interface)

---

## 1. Primary Entry-Point: `forecast()`

Member 3 (the Optimizer) calls this function to obtain probabilistic demand estimates across products for a given store and replenishment horizon.

### Python Signature
```python
def forecast(
    store_id: str,
    product_ids: list[str] | None = None,
    horizon_days: int = 14,
    grid_step: float = 0.05,
    model_name: str | None = None,
    as_dataframe: bool = True
) -> pd.DataFrame:
    """
    Computes probabilistic demand forecast for the requested products over the planning horizon.

    Parameters:
    -----------
    store_id: str
        Target retail store identifier (e.g. "STORE_001").
    product_ids: list[str] | None
        List of product IDs to forecast. If None, forecasts for all active products in the store.
    horizon_days: int
        Planning horizon in days (supported: 7, 14, 30). Default is 14.
    grid_step: float
        Quantile grid resolution, default 0.05 (produces q05, q10, ..., q95).
    model_name: str | None
        Model registry key (e.g. "gb_quantile", "seasonal_naive", "ets_statistical", "ensemble").
        If None, uses the best-calibrated production model from registry.
    as_dataframe: bool
        If True, returns pandas.DataFrame; otherwise returns list of dicts.

    Returns:
    --------
    pd.DataFrame:
        DataFrame conforming to the Output Schema below.
    """
```

### Output Schema (Per Store, Product, Horizon)

| Column Name | Type | Description | Example |
|---|---|---|---|
| `store_id` | `str` | Store identifier | `"STORE_001"` |
| `product_id` | `str` | Product identifier | `"PROD_MILK_1L"` |
| `horizon_days` | `int` | Planning horizon in days | `14` |
| `forecast_date` | `str` (YYYY-MM-DD) | Date from which forecast begins (T+1) | `"2026-10-15"` |
| `p10` | `float` | 10th percentile of cumulative demand | `42.5` |
| `p50` | `float` | Median (50th percentile) expected demand | `58.0` |
| `p90` | `float` | 90th percentile of cumulative demand | `79.2` |
| `quantiles` | `dict[str, float]` | Full grid in 5% steps: `q05, q10, ..., q95` | `{"q05": 38.1, "q10": 42.5, ...}` |
| `sample_paths` | `list[float]` | 20 representative cumulative sample paths | `[54.2, 59.1, 62.0, ...]` |
| `shock_active` | `bool` | True if shock flag was active and widened interval | `False` |
| `widening_factor` | `float` | Multiplier applied to interval width | `1.0` |
| `model_name` | `str` | Name/family of forecasting model used | `"gb_quantile_lgbm"` |
| `features_used` | `list[str]` | Exact feature list utilized | `["sales_lag_7", "calendar_dow", "payday_flag"]` |

### Example Output JSON
```json
[
  {
    "store_id": "STORE_001",
    "product_id": "PROD_MILK_1L",
    "horizon_days": 14,
    "forecast_date": "2026-10-15",
    "p10": 42.5,
    "p50": 58.0,
    "p90": 79.2,
    "quantiles": {
      "q05": 38.1,
      "q10": 42.5,
      "q15": 45.0,
      "q20": 47.3,
      "q25": 49.5,
      "q30": 51.4,
      "q35": 53.2,
      "q40": 55.0,
      "q45": 56.6,
      "q50": 58.0,
      "q55": 60.1,
      "q60": 62.4,
      "q65": 64.8,
      "q70": 67.5,
      "q75": 70.4,
      "q80": 73.8,
      "q85": 76.5,
      "q90": 79.2,
      "q95": 84.6
    },
    "sample_paths": [48.2, 52.1, 55.4, 58.0, 61.2, 65.7, 72.0],
    "shock_active": false,
    "widening_factor": 1.0,
    "model_name": "gb_quantile_lgbm",
    "features_used": [
      "sales_lag_1",
      "sales_lag_7",
      "sales_lag_14",
      "sales_rolling_mean_7",
      "day_of_week",
      "is_weekend",
      "payday_active"
    ]
  }
]
```

---

## 2. Market Signal Output Contract (Component A)

Component A extracts structured market intelligence from customer reviews/feedback and pattern shifts in sales data.

### Signal Schema

| Field | Type | Description | Allowed Values / Examples |
|---|---|---|---|
| `signal_id` | `str` | Unique UUID or prefixed ID | `"SIG_20261014_001"` |
| `product_or_category` | `str` | Target product or broader category | `"PROD_MILK_1L"` or `"DAIRY"` |
| `type` | `str` | Type of signal detected | `"CHANGE_POINT_SPIKE"`, `"CHANGE_POINT_DROP"`, `"CUSTOMER_NEED"`, `"CUSTOMER_COMPLAINT"`, `"EMERGING_PREFERENCE"` |
| `evidence` | `str` | Quantified data or excerpt backing the signal | `"Sales velocity increased +42% over 7d rolling window; Cusum score 4.8"` or `"3 customer reviews mention stockout during afternoon peak"` |
| `confidence` | `float` | Model confidence in signal [0.0, 1.0] | `0.85` |
| `date` | `str` (YYYY-MM-DD) | Signal observation date | `"2026-10-14"` |

### Example Signal Output JSON
```json
[
  {
    "signal_id": "SIG_20261014_001",
    "product_or_category": "PROD_COOKING_OIL_1L",
    "type": "CHANGE_POINT_SPIKE",
    "evidence": "Persistent upward mean shift detected via CUSUM (z-score=3.41, p<0.01) after fuel price shock announcement",
    "confidence": 0.92,
    "date": "2026-10-14"
  },
  {
    "signal_id": "SIG_20261014_002",
    "product_or_category": "PROD_OAT_MILK",
    "type": "EMERGING_PREFERENCE",
    "evidence": "Review snippet: 'Do you carry plant based milk or oat milk? We need lactose free options in this area.'",
    "confidence": 0.88,
    "date": "2026-10-14"
  }
]
```

---

## 3. Upstream Data Contract (Consumed from Member 1)

Our forecasting engine expects data formatted as follows (or provided by our standalone mock `mock_data/generator.py`):

1. **Daily Sales History:**
   - `date`: `str` (YYYY-MM-DD)
   - `store_id`: `str`
   - `product_id`: `str`
   - `units_sold`: `float` / `int` (actual non-negative count)
   - `on_promotion`: `bool` / `int`

2. **Calendar & Context Features:**
   - `date`: `str` (YYYY-MM-DD)
   - `day_of_week`: `int` (0-6)
   - `is_weekend`: `int` (0 or 1)
   - `month`: `int` (1-12)
   - `payday_flag`: `int` (1 if near local payday 25th-31st, else 0)
   - `public_holiday_flag`: `int` (1 or 0)

3. **Macro & Economic Features:**
   - `inflation_index`: `float`
   - `fuel_price_index`: `float`

4. **Shock Flags:**
   - `shock_flag`: `int` (1 if local strike, road closure, extreme weather alert, else 0)
   - `shock_type`: `str` (e.g. `"STRIKE"`, `"WEATHER"`, `"NONE"`)

5. **Customer Feedback / Reviews (Component A NLP):**
   - `review_id`: `str`
   - `date`: `str`
   - `store_id`: `str`
   - `text`: `str`
   - `product_or_category_ref`: `str`
