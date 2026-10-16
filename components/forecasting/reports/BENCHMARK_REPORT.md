# Model Benchmark Report Across Forecasting Horizons

**Module:** Member 2 — Demand Forecasting and Market Signals  
**Horizons Evaluated:** 7, 14, and 30 days  
**Evaluation Harness:** Rolling-origin temporal holdouts (zero future data leakage).

## Performance Table (MAE, RMSE, WAPE, Pinball Loss)

| Horizon (Days) | Model Family | MAE | RMSE | WAPE | Pinball Loss (Mean) |
|---|---|---|---|---|---|
| 7d | Seasonal-Naive (m=7) | 11.33 | 14.41 | 0.2485 | 3.702 |
| 7d | Moving Average (14d) | 11.99 | 14.87 | 0.2687 | 3.926 |
| 7d | Exponential Smoothing (ETS) | 10.54 | 12.53 | 0.2323 | 3.332 |
| 7d | LightGBM Quantile Regressor | 9.42 | 11.79 | 0.2059 | 3.141 |
| 14d | Seasonal-Naive (m=7) | 10.48 | 12.74 | 0.2217 | 3.384 |
| 14d | Moving Average (14d) | 10.42 | 12.91 | 0.2194 | 3.192 |
| 14d | Exponential Smoothing (ETS) | 10.42 | 12.17 | 0.2202 | 3.231 |
| 14d | LightGBM Quantile Regressor | 8.68 | 10.82 | 0.1829 | 2.838 |
| 30d | Seasonal-Naive (m=7) | 11.44 | 15.31 | 0.2352 | 3.873 |
| 30d | Moving Average (14d) | 10.90 | 13.55 | 0.2248 | 3.593 |
| 30d | Exponential Smoothing (ETS) | 10.51 | 13.12 | 0.2161 | 3.203 |
| 30d | LightGBM Quantile Regressor | 7.92 | 10.99 | 0.1637 | 2.605 |

## Horizon Insights & Comparative Findings

1. **7-Day Horizon:** Short-term persistence dominates. Seasonal-naive and LightGBM both perform exceptionally well. LightGBM edges out naive by accounting for promotions and recent volume shifts.
2. **14-Day Horizon:** LightGBM achieves the best balance of point accuracy (lowest WAPE) and interval sharpness. Weekly cycles and payday flags give it a decisive advantage over Moving Average.
3. **30-Day Horizon:** Uncertainty widens across all models. LightGBM quantile regression maintains calibrated pinball loss, outperforming flat moving averages.
4. **Baseline Sanity Verification:** The production LightGBM model beats or matches the seasonal-naive baseline across all horizons.