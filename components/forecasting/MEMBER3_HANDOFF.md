# Member 3 (Inventory Optimizer) Integration Guide

This guide describes how **Member 3 (Inventory Optimizer)** consumes demand distributions from **Member 2 (Demand Forecasting and Market Signals)**.

---

## 1. Quick Integration

You can import and call `forecast()` directly:

```python
from forecasting import forecast

# 14-day cumulative demand distribution for replenishment planning
df_forecast = forecast(
    store_id="STORE_001",
    product_ids=["PROD_MILK_1L", "PROD_BREAD", "PROD_COOKING_OIL_1L"],
    horizon_days=14,
    grid_step=0.05
)
```

If linking this folder inside a shared team repository or monorepo, you can also install it in editable mode:
```bash
pip install -e .
```

---

## 2. Output Schema Received by Member 3

Every row returned by `forecast()` represents one `(store_id, product_id, horizon_days)` with cumulative distributions:

| Field | Type | How Member 3 Uses It |
|---|---|---|
| `store_id` | `str` | Store identifier |
| `product_id` | `str` | Product identifier |
| `horizon_days` | `int` | Planning/replenishment horizon (e.g. 7, 14, 30 days) |
| `forecast_date` | `str` | Start date of forecast window ($T+1$) |
| `p10` | `float` | 10th percentile cumulative demand (pessimistic / low bound) |
| `p50` | `float` | Median expected cumulative demand ($D_i$) |
| `p90` | `float` | 90th percentile cumulative demand ($SS_i$ derivation) |
| `quantiles` | `dict[str, float]` | Full 5% grid (`q05`, `q10`, ..., `q95`) for exact **Newsvendor fractile matching** |
| `sample_paths` | `list[float]` | 20 Monte Carlo trajectories for stochastic budget optimization |
| `shock_active` | `bool` | Alert flag indicating external disruption (strikes, weather, supply alerts) |
| `widening_factor` | `float` | Multiplier applied to interval width ($1.50\times$ during shocks) |
| `model_name` | `str` | Name of underlying model used |
| `features_used` | `list[str]` | Explanatory features used (passed to Member 5 LLM explainer) |

---

## 3. Recommended Optimization Formulations

### A. Newsvendor Critical Fractile
For each product $i$, calculate critical ratio:
$$\text{Critical Fractile} = \frac{c_u}{c_u + c_o} = \frac{\text{Price} - \text{Cost}}{\text{Price} - \text{Cost} + \text{Holding/Overage Cost}}$$
Lookup the closest quantile key in `row["quantiles"]` (e.g., `q75` for 0.75 target service level) to obtain $Q_i^*$. Then:
$$Q_i = \max(0, Q_i^* - I_i - P_i)$$

### B. Safety Stock Baseline
$$SS_i = p_{90} - p_{50}$$
$$Q_i = \max(0, p_{50} + SS_i - I_i - P_i)$$

### C. Shock-Aware Buffering
When `row["shock_active"] == True`, interval widths are widened by `row["widening_factor"]` ($1.50\times$). The optimizer can increase buffer stock or flag conservative purchase limits to avoid capital lockup during high-uncertainty disruptions.

---

## 4. Working Example Script
A complete working example script is provided in:
[`examples/optimizer_integration_demo.py`](examples/optimizer_integration_demo.py)

Run it with:
```bash
python examples/optimizer_integration_demo.py
```
