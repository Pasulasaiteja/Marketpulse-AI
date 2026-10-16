# Architecture & Team Integration Guide

**Module:** Member 2 — Demand Forecasting & Market Signals  
**Role:** Analytical component of MarketPulse AI delivering demand distributions to Member 3 (Optimizer).

---

## 1. Directory Structure

```
Demand Forecasting and Market Signals/
├── CONTRACT.md                     # Input/Output schemas, JSON examples, API signatures
├── ARCHITECTURE.md                 # System overview, component flows, next steps for team/models
├── ASSUMPTIONS.md                  # Explicit mathematical assumptions & calibration rules
├── requirements.txt                # Pinned dependencies
├── mock_data/                      # Member 1 mock provider (isolated from core algorithms)
│   ├── __init__.py
│   ├── schema.py                   # Data schemas (Sales, Context, Macro, Feedback)
│   └── generator.py                # Synthetic generator with ground-truth seasonality, shocks, reviews
├── forecasting/                    # Core forecasting package (Component B)
│   ├── __init__.py
│   ├── api.py                      # Primary forecast() entry-point conforming to CONTRACT.md
│   ├── registry.py                 # Pluggable model registry for Member 5 configuration
│   ├── evaluation.py               # Rolling-origin cross-validation & metrics (MAE, RMSE, WAPE, Pinball)
│   ├── baselines.py                # Seasonal-naive, Moving Average, Exponential Smoothing
│   ├── gb_quantile.py              # Gradient Boosted Quantile Regressor (LightGBM/HistGB)
│   ├── statistical.py              # Statistical ETS / AutoARIMA & Hierarchical Bayes pooling
│   ├── calibration.py              # Conformal prediction & shock interval widening
│   └── ablation.py                 # 4-tier feature ablation runner & effect size calculator
├── market_signals/                 # Market Signal Intelligence (Component A)
│   ├── __init__.py
│   ├── change_point.py             # CUSUM / statistical sales velocity shift detection
│   ├── nlp_classifier.py           # NLP review classifier (Needs, Complaints, Emerging Preferences)
│   └── pipeline.py                 # Structured signal generator conforming to CONTRACT.md
├── tests/                          # Test suite matching task checklist verification criteria
│   ├── test_contract.py            # Validates schema compatibility with Member 3
│   ├── test_baselines.py           # Baseline sanity & metric calculation
│   ├── test_main_models.py         # LightGBM & statistical models beating naive
│   ├── test_uncertainty_calibration.py # 80% coverage check & conformal calibration
│   ├── test_no_leakage.py          # Temporal rolling origin validation
│   ├── test_sparse_and_shocks.py   # Cold-start fallback & shock widening verification
│   ├── test_market_signals.py      # Change-point & NLP pipeline validation
│   └── test_ablation.py            # Feature ablation tier progression
├── reports/                        # Auto-generated markdown reports & evidence
│   ├── BENCHMARK_REPORT.md         # Baselines vs Main Models across 7, 14, 30 days
│   ├── ABLATION_REPORT.md          # Tier 1 to 4 ablation results & feature decisions
│   └── CALIBRATION_REPORT.md       # Empirical coverage tables & interval widths
└── notebooks/
    └── reproduce_results.ipynb     # Reproducibility notebook
```

---

## 2. Component Pipeline & Data Flow

```
+-----------------------------------------------------------------------------------+
| 1. Upstream Data (Member 1 or mock_data/)                                         |
|    - Daily Sales (store_id, product_id, date, units_sold)                         |
|    - Calendar & Context (DOW, payday_flag, holiday_flag)                          |
|    - Macro & Shocks (inflation, fuel_index, shock_flag)                           |
|    - Customer Feedback Reviews (text, date, store_id)                             |
+-----------------------------------------------------------------------------------+
                                     |
                                     v
+-----------------------------------------------------------------------------------+
| 2. Component A: Market Signal Intelligence (market_signals/)                      |
|    - CUSUM Statistical Change-Point Detector -> Persistent sales shifts           |
|    - NLP Feedback Classifier -> Needs, Complaints, Emerging Preferences           |
|    - Output: Structured signals with evidence & confidence                        |
+-----------------------------------------------------------------------------------+
                                     |
                                     v
+-----------------------------------------------------------------------------------+
| 3. Feature Store & 4-Tier Ablation Engine (forecasting/ablation.py)               |
|    - Tier 1: Historical Sales only (Lags: 1, 7, 14, 28; Rolling means)            |
|    - Tier 2: + Calendar Features (Day of week, Month, Payday)                     |
|    - Tier 3: + Economic Features (Inflation, Fuel price)                          |
|    - Tier 4: + Shocks & Verified Market Signals                                   |
|    * Gating Rule: Only features that reduce out-of-sample WAPE enter final model  |
+-----------------------------------------------------------------------------------+
                                     |
                                     v
+-----------------------------------------------------------------------------------+
| 4. Probabilistic Forecasting Engine (forecasting/)                                |
|    - Baseline Models: Seasonal Naive, Moving Average, Exp Smoothing               |
|    - Main Models: Gradient Boosted Quantile Regressor (LightGBM)                  |
|    - Sparse / Cold-Start: Hierarchical Category Prior Pooling                     |
|    - Uncertainty Calibration: Conformal calibration to guarantee 80% coverage     |
|    - Shock Widening: 1.5x interval inflation when shock_flag is active            |
+-----------------------------------------------------------------------------------+
                                     |
                                     v
+-----------------------------------------------------------------------------------+
| 5. Output API (forecasting/api.py) -> Member 3 (Optimizer)                        |
|    forecast(store_id, product_ids, horizon_days=14)                               |
|    Returns DataFrame with: p10, p50, p90, 5% grid quantiles, sample paths,        |
|                            model_name, features_used, shock_active                |
+-----------------------------------------------------------------------------------+
```

---

## 3. Guide for Collaborating AI Models & Team Members

If another model or developer is continuing work on this codebase:
1. **Always verify against `CONTRACT.md`:** Never rename columns or change function parameters in `forecasting/api.py`. Member 3's optimizer imports `forecast()` directly.
2. **Never guess assumptions:** Read `ASSUMPTIONS.md` for parameter rationale (e.g. shock widening factor = 1.5x, cold start threshold = 14 days).
3. **Run tests before marking any task complete:**
   ```bash
   pytest tests/ -v
   ```
4. **Follow temporal safety:** Any new feature must use strictly past information ($t-1$ and earlier). No future target leakage.
