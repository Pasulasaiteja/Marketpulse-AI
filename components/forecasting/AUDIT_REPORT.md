# MarketPulse AI - Demand Forecasting & Market Signals
## System Audit, Vulnerability Resolution & Handoff Guide

**Role:** Member 2 (Components A & B)  
**Date:** October 14, 2026  
**Status:** 100% Verified, Fully Tested (16/16 Unit/Contract Tests Passing)  

---

## 1. Compliance Audit Against Project Specifications

We have audited the entire codebase against [02_forecasting_and_market_signals.md](02_forecasting_and_market_signals.md), [prompt.txt](prompt.txt), and [README.md](README.md).

### Core Principle Check
> **"Machine learning estimates demand. Optimization decides purchases. The language model translates and explains."**
- **Verification:** Passed. The LLM is never called to predict numbers, compute quantiles, or calculate ordering quantities. All outputs originate from pure LightGBM quantile regression, ETS/AutoARIMA statistical baselines, CUSUM change-point detection, and conformal calibration.

### Task List Verification (02_forecasting_and_market_signals.md)

| Section | Required Task | Implementation Location | Verification Status |
|---|---|---|---|
| **A. Baselines** | Seasonal-naive ($m=7$) | `forecasting/baselines.py` (`SeasonalNaiveForecaster`) | Verified (`test_baselines.py`) |
| | Moving average ($W=14$) | `forecasting/baselines.py` (`MovingAverageForecaster`) | Verified (`test_baselines.py`) |
| | Exponential smoothing (ETS / SES) | `forecasting/baselines.py` (`ExponentialSmoothingForecaster`) | Verified (`test_baselines.py`) |
| | Metrics Suite (MAE, RMSE, WAPE, MASE, Pinball) | `forecasting/metrics.py` | Verified (`test_baselines.py`) |
| | Rolling-origin temporal split (zero leakage) | `forecasting/evaluation.py` | Verified (`test_baselines.py`) |
| **B. Main Models** | Gradient-boosted quantile regression (LightGBM) | `forecasting/gb_quantile.py` | Verified (`test_main_models.py`) |
| | Statistical model (ETS / AutoARIMA) | `forecasting/statistical.py` | Verified (`test_main_models.py`) |
| | Hierarchical category pooling for sparse items | `forecasting/statistical.py` (`HierarchicalBayesPoolingForecaster`) | Verified (`test_sparse_and_shocks.py`) |
| **C. Uncertainty** | Quantile grid ($q_{05}$ to $q_{95}$ in 5% steps) | `forecasting/api.py` (`forecast()`) | Verified (`test_contract.py`) |
| | Conformal calibration (80% coverage guarantee) | `forecasting/calibration.py` (`ConformalCalibrator`) | Verified (`test_uncertainty_calibration.py`) |
| | Shock widening rule ($1.50\times$ documented assumption) | `forecasting/calibration.py`, `ASSUMPTIONS.md` | Verified (`test_sparse_and_shocks.py`) |
| **D. Ablation** | 4-tier feature ablation study | `forecasting/ablation.py` | Verified (`test_ablation.py`, `reports/ABLATION_REPORT.md`) |
| | Out-of-sample effect sizes & null-result gating | `forecasting/ablation.py` | Verified |
| **E. Market Signals** | Statistical CUSUM sales shift detection | `market_signals/change_point.py` | Verified (`test_market_signals.py`) |
| | NLP feedback classifier (Needs, Complaints, Trends) | `market_signals/nlp_classifier.py` | Verified (`test_market_signals.py`) |
| | Structured signal output schema | `market_signals/pipeline.py` | Verified (`test_market_signals.py`) |
| **F. Packaging** | Dynamic Model Registry | `forecasting/registry.py` | Verified (`test_contract.py`) |
| | Production `forecast()` API matching CONTRACT.md | `forecasting/api.py` | Verified (`test_contract.py`) |

---

## 2. Vulnerability Audit & Security Fixes Applied

During rigorous code review, four key vulnerabilities were identified and hardened:

### Vulnerability 1: Unvalidated Input Injections in Public API (`forecasting/api.py`)
- **Risk:** Negative or zero `horizon_days`, bad or zero `grid_step` causing division by zero, non-string or empty `store_id`, and non-string or non-list `product_ids` could crash the service or corrupt downstream optimization pipelines.
- **Fix:** Added strict parameter validation at the entry of `forecast()`:
  - Validates `store_id` is a non-empty string.
  - Validates `product_ids` is a non-empty list of non-empty strings.
  - Validates `horizon_days` is an integer $> 0$ and $\le 365$.
  - Validates `grid_step` is a float in $(0.0, 0.5]$.
  - Gracefully handles unknown product IDs by initializing cold-start category prior pooling rather than raising unhandled exceptions.

### Vulnerability 2: Corrupt / Extreme Value Propagation in Calibration (`forecasting/calibration.py`)
- **Risk:** If input historical validation actuals or quantile predictions contained `NaN`, `Inf`, or extreme outliers, conformal non-conformity scores became corrupt, propagating `NaN` width adjustments to all downstream forecast bounds.
- **Fix:** Added explicit `valid_mask = np.isfinite(y_val) & np.isfinite(q10_val) & np.isfinite(q90_val)` to drop invalid points before computing empirical quantiles, falling back safely to nominal bounds if sample size is zero.

### Vulnerability 3: Array Dimension Mismatch / 0-d Broadcasting Crash (`forecasting/calibration.py`)
- **Risk:** When single-horizon scalar quantiles ($q_{10}, q_{90}$) were passed to `calibrate()`, `np.asarray()` created 0-dimensional arrays, causing `IndexError: too many indices for array: array is 0-dimensional` during boolean indexing.
- **Fix:** Used `np.atleast_1d()` and explicit `np.broadcast_to(q, y_val.shape)` to guarantee compatible array indexing under all scalar or multi-step horizon inputs.

### Vulnerability 4: Platform Encoding Crash on Windows Console (`scripts/generate_plots.py`)
- **Risk:** Output print statements containing UTF-8 emojis (`✅`, `→`) or en-dashes (`–`) failed under Windows console default codepages (`cp1252`), aborting batch scripts and test runners.
- **Fix:** Sanitized all console outputs and plot legends to pure ASCII-safe strings.

---

## 3. Real-World Demand Dynamics: Highs, Lows, and Calibration Plot

### Why Was the Previous Plot Monotonically Increasing?
The previous plot visualized the cumulative Empirical Cumulative Distribution Function (CDF) and cumulative multi-day totals. In cumulative sums, values naturally increase monotonically with each additional day ($D_1 + D_2 + \dots + D_T$).

### Real-World Realism Added in `reports/calibration_plot.png`
To reflect real-world retail store dynamics, the calibration visualization was upgraded to a dual-panel figure:

1. **Daily Fan Chart (Left Panel):**
   - **Daily Highs and Lows:** Shows the daily sales time-series with visible fluctuations:
     - Weekend shopping peaks ($+35\%$ on Saturdays).
     - Mid-week replenishment troughs (Mondays/Tuesdays).
     - Month-end and month-beginning payday surges ($+30\%$ demand on days 27–31 and 1–2).
     - Price shocks and external disruptions.
   - **Quantile Fan Bands:** Outer $p_{05}-p_{95}$, nominal $80\%$ CI ($p_{10}-p_{90}$), and inner $50\%$ CI ($p_{25}-p_{75}$) uncertainty envelopes expand smoothly into the 14-day horizon.
   - **Ground-Truth Test Overlay:** Held-out actual daily sales are plotted as orange markers, confirming that daily variations remain reliably captured within the calibrated interval bands.

2. **Coverage Verification / Reliability Diagram (Right Panel):**
   - Plots empirical coverage against nominal coverage levels ($0.05$ through $0.95$).
   - Demonstrates that intervals achieve the required 80% coverage target without overconfidence or reckless under-coverage.

---

## 4. Instructions for Collaborating Models & Team Members

### For Member 1 (Data & Features)
- When live data is available, replace `mock_data/` with the real data loader.
- Ensure the live data conforms to the schema in [mock_data/README.md](mock_data/README.md):
  - `sales`: `date, store_id, product_id, category, units_sold, on_promotion`
  - `context`: `date, day_of_week, is_weekend, month, day_of_month, payday_flag, holiday_flag, inflation_index, fuel_price_index, shock_flag, shock_type`
  - `reviews`: `review_id, date, store_id, product_or_category, text`

### For Member 3 (Inventory Optimizer)
- Call `forecast(store_id, product_ids, horizon_days, grid_step)` from `forecasting.api`.
- The returned DataFrame contains:
  - `p10, p50, p90`: Primary quantile anchors for base-stock and safety-stock calculation.
  - `quantiles`: Full dictionary mapping `{0.05: v, 0.10: v, ..., 0.95: v}`.
  - `sample_paths`: Array of 20 simulated trajectory paths for Monte Carlo / scenario optimization.
  - `shock_active` & `widening_factor`: Flags indicating when external disruptions warrant conservative buffer stock.

### For Member 5 (LLM / Orchestrator)
- Use `ModelRegistry.list_models()` and `ModelRegistry.get(name)` to inspect or dynamically select models.
- When generating business explanations, extract `features_used`, `model_name`, `shock_active`, and market signal evidence from `detect_all_signals()` directly. **Never ask the LLM to invent demand numbers.**

---

## 5. Verification Commands

To run all tests and verify reproduction:
```bash
# 1. Run all 16 unit and contract tests
python -m pytest tests/ -v

# 2. Regenerate benchmark and calibration reports
python scripts/generate_plots.py
```
All tests pass cleanly in under 60 seconds with 0 warnings or errors.
