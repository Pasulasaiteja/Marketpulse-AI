# Member 2: Demand Forecasting and Market Signals

**Owns:** Component B (Demand Forecasting Engine) and Component A (Market Signal Intelligence), plus the feature ablation study.
**Consumes:** Member 1's datasets and context features.
**Feeds:** Member 3 (optimizer) with demand distributions.

## Description

Build the forecasting engine that estimates demand over 7, 14, and 30 day horizons **with uncertainty**, benchmark several model families, and test whether each tier of context and market signal actually improves accuracy. Component A produces structured market signals (reviews, price shifts, sales-pattern changes) that only enter the forecast if they prove predictive. A null result is a valid finding.

## Shared Contracts

- **Forecast output** (per store, product, horizon): `p10, p50, p90` plus quantiles on a grid (e.g. 5% steps) or sample paths, and `model_name`, `features_used`
- **Signal output:** `signal_id, product_or_category, type, evidence, confidence, date`
- Provide: `forecast(store_id, product_ids, horizon_days) -> DataFrame` in the format Member 3 needs

## Task List

### A. Baselines
- [ ] Seasonal-naive
- [ ] Moving average and exponential smoothing

### B. Main models
- [ ] Gradient-boosted regression with lagged sales and calendar features, using quantile loss
- [ ] A statistical model (e.g. ETS/ARIMA or a hierarchical/Bayesian model for sparse data)
- [ ] Optional: an advanced time-series model if data supports it
- [ ] Hierarchical pooling or cold-start prior use for sparse products and new shops (using Member 1's priors)

### C. Uncertainty
- [ ] Produce full prediction intervals / quantiles, not only point estimates
- [ ] Calibrate intervals (conformal prediction or similar)
- [ ] Widen intervals when shock flags are active, with the widening rule written down as an explicit assumption

### D. Ablation study
- [ ] Run: (1) sales only, (2) + calendar, (3) + economic, (4) + shocks
- [ ] Keep a feature tier only if it lowers error out-of-sample
- [ ] Report effect sizes with uncertainty; flag any hand-set assumptions as such

### E. Market Signal Intelligence (Component A)
- [ ] Statistical pipeline: detect shifts/change points in sales patterns
- [ ] NLP pipeline: classify review/feedback text into needs, complaints, emerging preferences (start with a small labeled set)
- [ ] Output structured signals with evidence and confidence
- [ ] Test each signal's predictive value in the ablation before letting it influence forecasts

### F. Packaging
- [ ] Model registry/config so Member 5 can swap models
- [ ] Runtime under a defined limit for a single store forecast

## Tests

| Test | Pass condition |
|---|---|
| Baseline sanity | Main models beat or match seasonal-naive on held-out data, or the gap is documented |
| Metrics | Report MAE, RMSE, WAPE or MASE, and pinball loss per model and horizon |
| Interval calibration | 80% interval covers roughly 80% of actuals (within tolerance) |
| Synthetic recovery | On Member 1's synthetic data, the model recovers known seasonal and payday effects |
| No leakage | Rolling-origin backtest only; no future data in features |
| Sparse data | Forecast still produced (with wide intervals) for products with little history |
| Shock widening | Active shock flag widens intervals measurably |
| Signal test | Each market signal has a documented predictive-value result (helps / no effect) |
| Output contract | Output schema validated against what the optimizer consumes |

## Deliverables

1. `forecasting/` module with baselines, main models, and the `forecast()` API
2. Benchmark report comparing all models across horizons
3. Ablation report with tier-by-tier results and conclusions
4. Calibration plots and coverage table
5. Market signal pipeline (change-point detection + NLP classifier) with output schema
6. Documented assumptions (shock widening, priors)
7. Notebook reproducing key results
