# Mock Data Provider (Member 1 Interface)

**Purpose:** Isolated mock module that implements the contract with Member 1. When Member 1 completes their data processing pipeline, this entire directory can be cleanly swapped with the live data connector without touching the forecasting algorithms.

---

## Datasets Provided

1. **`sales` (Daily Sales Data)**
   - Schema: `date`, `store_id`, `product_id`, `category`, `units_sold`, `on_promotion`
   - Span: 2025-01-01 to 2026-10-14 (653 days)
   - Stores: `STORE_001` (Supermarket), `STORE_002` (Small Kiosk)
   - Products: 6 items (Staples, fast-moving, price-shock sensitive, sparse tea, and cold-start energy drink)

2. **`context` (Calendar, Macro, Shock Data)**
   - Calendar: `day_of_week`, `is_weekend`, `month`, `day_of_month`, `payday_flag`, `holiday_flag`
   - Economic: `inflation_index`, `fuel_price_index`
   - Shock: `shock_flag` (0 or 1), `shock_type` (`"TRANSPORT_STRIKE"`, `"EXTREME_WEATHER"`, `"SUPPLY_CHAIN_ALERT"`)

3. **`reviews` (Customer Text Reviews for Component A)**
   - Schema: `review_id`, `date`, `store_id`, `product_or_category`, `text`, `ground_truth_intent`
   - Labeled classes: `NEED`, `COMPLAINT`, `PREFERENCE`, `NEUTRAL`

---

## Known Ground-Truth Signals (For Verification Tests)

- **Weekly Seasonality:** Saturday multiplier $1.35\times$, Monday $0.85\times$.
- **Payday Effect:** $+30\%$ demand surge on days 27-31 and 1-2.
- **Sparse Products:** `PROD_SPECIALTY_TEA` (< 10 total sales).
- **Cold-Start:** `PROD_NEW_ENERGY_DRINK` (0 historical sales, tests prior pooling).
- **Shock Events:** High volatility and widened prediction intervals during active shock periods.
