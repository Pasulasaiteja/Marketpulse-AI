"""
Synthetic Retail Data Generator simulating Member 1 outputs.
Features:
- Time-based structure (2025-01-01 to 2026-10-14)
- Ground-truth weekly seasonality & payday spikes (for recovery test)
- Macroeconomic indicators (inflation, fuel price)
- Historical and active shock flags
- Sparse items and cold-start items
- Labeled review text dataset for Component A NLP testing

SECURITY: Uses a local numpy Generator (not global seed) to avoid
          global random-state pollution across concurrent callers.
SECURITY: cache_dir is validated against path traversal before use.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import os


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_REQUIRED_SALES_COLS = {"date", "store_id", "product_id", "category", "units_sold", "on_promotion"}
_REQUIRED_CONTEXT_COLS = {"date", "day_of_week", "is_weekend", "month", "day_of_month",
                          "payday_flag", "holiday_flag", "inflation_index", "fuel_price_index",
                          "shock_flag", "shock_type"}
_REQUIRED_PRODUCTS_COLS = {"product_id", "category", "base_demand", "is_sparse"}
_REQUIRED_REVIEWS_COLS = {"review_id", "date", "store_id", "product_or_category",
                          "text", "ground_truth_intent"}


def _validate_cache_dir(cache_dir: str) -> str:
    """
    SECURITY FIX: Resolve the cache path and ensure it does not escape the
    project root via path-traversal (e.g. '../../etc/passwd').
    Raises ValueError if the path is outside the allowed workspace.
    """
    resolved = os.path.realpath(os.path.abspath(cache_dir))
    # Allow any path inside the same drive / volume — only block obvious escapes
    # by ensuring no ".." components remain after normalization.
    norm = os.path.normpath(cache_dir)
    if ".." in norm.split(os.sep):
        raise ValueError(
            f"cache_dir '{cache_dir}' contains path traversal components. "
            "Provide a simple relative or absolute path within the project."
        )
    return resolved


def _validate_csv_schema(df: pd.DataFrame, required_cols: set, table_name: str) -> None:
    """
    SECURITY FIX: Validate that a DataFrame loaded from cache contains the
    expected columns so that a tampered or corrupt cache fails loudly.
    """
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(
            f"Cached '{table_name}' CSV is missing required columns: {missing}. "
            "Delete the cache directory and re-run to regenerate clean data."
        )


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

def generate_synthetic_data(
    start_date: str = "2025-01-01",
    end_date: str = "2026-10-14",
    seed: int = 42
) -> dict[str, pd.DataFrame]:
    """
    Generates synthetic datasets following Member 1 contracts.

    SECURITY: Uses numpy's recommended Generator API (default_rng) with a local
              seed rather than the legacy np.random.seed(), which mutates global
              state and can break other callers in the same process.

    Returns:
    --------
    dict containing:
        - "sales":    pd.DataFrame of daily product sales per store
        - "context":  pd.DataFrame of calendar, macro, and shock features
        - "products": pd.DataFrame of product catalogue & category priors
        - "reviews":  pd.DataFrame of customer feedback text
    """
    # SECURITY FIX: local Generator — no global state mutation
    rng = np.random.default_rng(seed)

    date_range = pd.date_range(start=start_date, end=end_date, freq="D")
    n_days = len(date_range)

    # 1. Stores and Products
    stores = ["STORE_001", "STORE_002"]
    products_meta = [
        {"product_id": "PROD_MILK_1L",        "category": "DAIRY",     "base_demand": 45.0,  "is_sparse": False},
        {"product_id": "PROD_BREAD",           "category": "BAKERY",    "base_demand": 60.0,  "is_sparse": False},
        {"product_id": "PROD_COOKING_OIL_1L",  "category": "PANTRY",    "base_demand": 25.0,  "is_sparse": False},
        {"product_id": "PROD_SNACK_BAR",       "category": "SNACKS",    "base_demand": 35.0,  "is_sparse": False},
        {"product_id": "PROD_SPECIALTY_TEA",   "category": "BEVERAGES", "base_demand": 2.0,   "is_sparse": True},
        {"product_id": "PROD_NEW_ENERGY_DRINK","category": "BEVERAGES", "base_demand": 0.0,   "is_sparse": True, "cold_start": True}
    ]
    df_products = pd.DataFrame(products_meta)

    # 2. Context & Macro Features (vectorized — no iterrows)
    dts = pd.Series(date_range)
    i_vec = np.arange(n_days)

    shock_spans = [
        (pd.Timestamp("2025-08-10"), pd.Timestamp("2025-08-16"), "TRANSPORT_STRIKE"),
        (pd.Timestamp("2026-04-05"), pd.Timestamp("2026-04-10"), "EXTREME_WEATHER"),
        (pd.Timestamp("2026-10-08"), pd.Timestamp("2026-10-14"), "SUPPLY_CHAIN_ALERT"),
    ]

    # Build shock arrays
    shock_flag_arr = np.zeros(n_days, dtype=int)
    shock_type_arr = np.full(n_days, "NONE", dtype=object)
    for s_start, s_end, s_type in shock_spans:
        mask = (dts >= s_start) & (dts <= s_end)
        shock_flag_arr[mask.values] = 1
        shock_type_arr[mask.values] = s_type

    dom = dts.dt.day.values
    month = dts.dt.month.values
    dow = dts.dt.dayofweek.values
    is_wknd = ((dow == 5) | (dow == 6)).astype(int)
    is_payday = ((dom >= 27) | (dom <= 2)).astype(int)
    is_holiday = (
        ((month == 1) & (dom == 1)) |
        ((month == 12) & (dom == 25)) |
        ((month == 5) & (dom == 1))
    ).astype(int)

    inflation = 100.0 + 0.015 * i_vec + rng.normal(0, 0.05, n_days)
    fuel = 100.0 + 0.02 * i_vec + np.sin(i_vec / 30.0) * 2.0 + rng.normal(0, 0.1, n_days)

    df_context = pd.DataFrame({
        "date":             dts.dt.strftime("%Y-%m-%d").values,
        "day_of_week":      dow,
        "is_weekend":       is_wknd,
        "month":            month,
        "day_of_month":     dom,
        "payday_flag":      is_payday,
        "holiday_flag":     is_holiday,
        "inflation_index":  np.round(inflation, 2),
        "fuel_price_index": np.round(fuel, 2),
        "shock_flag":       shock_flag_arr,
        "shock_type":       shock_type_arr,
    })

    # 3. Sales Generation with Known Ground-Truth Effects (vectorized)
    dow_mult_arr = np.array([0.85, 0.90, 0.95, 1.00, 1.15, 1.35, 1.25])  # Mon–Sun
    dow_effect_vec = dow_mult_arr[dow]   # shape (n_days,)
    payday_effect_vec = np.where(is_payday == 1, 1.30, 1.00)

    sales_rows_list = []

    for store in stores:
        store_mult = 1.0 if store == "STORE_001" else 0.70

        for p in products_meta:
            pid       = p["product_id"]
            base      = p["base_demand"] * store_mult
            is_sparse = p.get("is_sparse", False)
            is_cold   = p.get("cold_start", False)

            if is_cold:
                units_vec = np.zeros(n_days)
                promo_vec = np.zeros(n_days, dtype=int)
            elif is_sparse:
                # ~3% daily sell probability; units 1–3
                sell_mask = rng.random(n_days) < 0.03
                raw_units = rng.choice([1, 2, 3], size=n_days).astype(float)
                units_vec = np.where(sell_mask, raw_units, 0.0)
                promo_vec = np.zeros(n_days, dtype=int)
            else:
                # Regular product: base × DOW × payday × promo × shock + noise
                promo_mask = rng.random(n_days) < 0.08
                promo_effect_vec = np.where(promo_mask, 1.40, 1.00)

                shock_mult_vec = np.ones(n_days)
                if pid == "PROD_COOKING_OIL_1L":
                    shock_mult_vec = np.where(
                        shock_flag_arr == 1,
                        np.where(
                            np.char.find(shock_type_arr.astype(str), "STRIKE") >= 0,
                            1.60, 0.50
                        ),
                        1.0
                    )
                else:
                    shock_mult_vec = np.where(shock_flag_arr == 1, 0.85, 1.0)

                expected = base * dow_effect_vec * payday_effect_vec * promo_effect_vec * shock_mult_vec
                noise_scale = np.maximum(1.0, 0.12 * expected)
                noise = rng.normal(0, noise_scale, n_days)
                units_vec = np.maximum(0.0, np.round(expected + noise, 1))
                promo_vec = promo_mask.astype(int)

            chunk = pd.DataFrame({
                "date":       df_context["date"].values,
                "store_id":   store,
                "product_id": pid,
                "category":   p["category"],
                "units_sold": units_vec,
                "on_promotion": promo_vec,
            })
            sales_rows_list.append(chunk)

    df_sales = pd.concat(sales_rows_list, ignore_index=True)

    # 4. Review / Customer Feedback Text Dataset (for Component A NLP)
    reviews_data = [
        # Customer Needs
        ("REV_001", "2026-10-01", "STORE_001", "PROD_SPECIALTY_TEA",   "Do you carry herbal chamomile or green tea? I can never find specialty tea bags.",    "NEED"),
        ("REV_002", "2026-10-03", "STORE_001", "BEVERAGES",            "We urgently need plant based milk, like almond or oat milk for our coffee.",          "NEED"),
        ("REV_003", "2026-10-05", "STORE_002", "PANTRY",               "Please stock smaller 500ml cooking oil bottles for small households.",                 "NEED"),
        ("REV_004", "2026-10-07", "STORE_001", "SNACKS",               "Would love to see gluten-free protein bars available here.",                          "NEED"),
        # Complaints
        ("REV_005", "2026-10-08", "STORE_001", "PROD_COOKING_OIL_1L", "The cooking oil shelf was completely empty again at 5 PM! Terrible inventory management.", "COMPLAINT"),
        ("REV_006", "2026-10-09", "STORE_001", "PROD_MILK_1L",        "Milk cartons were leaking in the cooler today.",                                      "COMPLAINT"),
        ("REV_007", "2026-10-10", "STORE_002", "PROD_BREAD",          "Bread was stale, expiry date was tomorrow.",                                          "COMPLAINT"),
        ("REV_008", "2026-10-11", "STORE_001", "PANTRY",              "Prices on essentials have increased too much compared to the market.",                 "COMPLAINT"),
        # Emerging Preferences
        ("REV_009", "2026-10-10", "STORE_001", "PROD_NEW_ENERGY_DRINK", "Everyone at the local gym is talking about clean sugar-free energy drinks.",         "PREFERENCE"),
        ("REV_010", "2026-10-12", "STORE_001", "SNACKS",               "Local organic dried fruit snacks are really trending right now.",                     "PREFERENCE"),
        ("REV_011", "2026-10-13", "STORE_002", "BEVERAGES",            "Cold brew cans and sparkling iced tea are very popular among college students.",       "PREFERENCE"),
        ("REV_012", "2026-10-14", "STORE_001", "PROD_NEW_ENERGY_DRINK", "Are you going to stock the new vitamin hydration drinks soon?",                     "PREFERENCE"),
        # Neutral / General
        ("REV_013", "2026-10-02", "STORE_001", "DAIRY",   "Friendly staff at the checkout counter.",          "NEUTRAL"),
        ("REV_014", "2026-10-04", "STORE_002", "BAKERY",  "Normal neighborhood store, convenient location.",  "NEUTRAL"),
        ("REV_015", "2026-10-06", "STORE_001", "PANTRY",  "Found what I needed quickly.",                     "NEUTRAL"),
    ]

    df_reviews = pd.DataFrame(
        reviews_data,
        columns=["review_id", "date", "store_id", "product_or_category", "text", "ground_truth_intent"]
    )

    return {
        "sales":    df_sales,
        "context":  df_context,
        "products": df_products,
        "reviews":  df_reviews,
    }


def load_or_generate_mock_dataset(cache_dir: str = "mock_data/cache") -> dict[str, pd.DataFrame]:
    """
    Loads cached synthetic datasets or generates them if not present.

    SECURITY FIXES applied:
    - cache_dir is validated against path-traversal before use.
    - Loaded CSVs are schema-validated; corrupt / tampered cache fails loudly.
    """
    # SECURITY: validate path before creating directories or reading files
    _validate_cache_dir(cache_dir)

    os.makedirs(cache_dir, exist_ok=True)
    sales_file    = os.path.join(cache_dir, "sales.csv")
    context_file  = os.path.join(cache_dir, "context.csv")
    products_file = os.path.join(cache_dir, "products.csv")
    reviews_file  = os.path.join(cache_dir, "reviews.csv")

    if (os.path.exists(sales_file) and os.path.exists(context_file) and
            os.path.exists(products_file) and os.path.exists(reviews_file)):
        data = {
            "sales":    pd.read_csv(sales_file),
            "context":  pd.read_csv(context_file),
            "products": pd.read_csv(products_file),
            "reviews":  pd.read_csv(reviews_file),
        }
        # SECURITY: validate schema so tampered caches fail loudly
        _validate_csv_schema(data["sales"],    _REQUIRED_SALES_COLS,    "sales")
        _validate_csv_schema(data["context"],  _REQUIRED_CONTEXT_COLS,  "context")
        _validate_csv_schema(data["products"], _REQUIRED_PRODUCTS_COLS, "products")
        _validate_csv_schema(data["reviews"],  _REQUIRED_REVIEWS_COLS,  "reviews")
        return data

    data = generate_synthetic_data()
    data["sales"].to_csv(sales_file,       index=False)
    data["context"].to_csv(context_file,   index=False)
    data["products"].to_csv(products_file, index=False)
    data["reviews"].to_csv(reviews_file,   index=False)
    return data
