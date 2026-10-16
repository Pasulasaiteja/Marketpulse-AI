# Data Quality & Governance Report

## 1. Executive Summary
This report documents the cleaning procedures, anomaly handling, and known limitations of the datasets processed by the **Member 1: Data Foundation and Context Layer** workstream for MarketPulse AI.

---

## 2. Cleaning & Transformation Pipeline

### A. Deduplication & Integrity
* **Composite Keys:** Enforced uniqueness on `(date, store_id, item_id)` across sales records.
* **Non-Negativity Constraints:** Truncated negative `sales_quantity` records to 0.0 using floor clipping (`clip(lower=0.0)`).

### B. Continuous Date Reindexing & Stockout Disambiguation
* **Calendar Continuity:** Reindexed store-product time series across the entire date range (2025-01-01 to 2025-12-31) to fill logging gaps.
* **Censored Demand Disambiguation:** Flagged zero-sales days (`is_stockout = True`) to distinguish true zero demand from inventory stockouts.

### C. Outlier Winsorization
* **IQR Spikes:** Applied Interquartile Range (IQR) upper-bound capping ($Q3 + 3.0 \times IQR$) per product to prevent non-stockout extreme bulk purchases from polluting rolling lag statistics.

---

## 3. Context Layer Resilience & Fallback Auditing

* **Primary Sources:** Regional Adapters (`SouthAsiaAdapter`, `EcuadorAdapterStub`).
* **Fallback Triggering:** When external context signals fail or time series are incomplete, `ContextEngine` injects default baseline features marked with `is_fallback = True`.
* **Audit Trail:** Every record logs `source`, `is_fallback`, and `fetch_timestamp` for system traceability.

---

## 4. Known Limitations

1. **Synthetic Data Realism:** The synthetic generator models demand using Poisson distributions with linear drift; extreme macroeconomic shocks (e.g., hyperinflation) are simplified.
2. **Static Price Baselines:** Item list prices remain fixed across the time window unless promotional overrides are applied.
3. **Regional Stub Coverage:** `EcuadorAdapterStub` provides static dollarization markers; real-time web scraping for Ecuador economic indices is intentionally stubbed.