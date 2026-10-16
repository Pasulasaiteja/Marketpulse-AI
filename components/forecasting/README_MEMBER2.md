# Member 2: Demand Forecasting & Market Signals

This folder contains the complete, tested implementation of **Component B (Demand Forecasting Engine)** and **Component A (Market Signal Intelligence)** for MarketPulse AI.

---

## 1. Quickstart

### Installation
Ensure Python 3.10+ is installed, then install dependencies:
```bash
pip install -r requirements.txt
```

### Running Tests
Run all 16 unit and contract tests:
```bash
pytest tests/ -v
```

---

## 2. Shared Contracts & Primary API

### For Member 3 (Inventory Optimizer)
Call the primary entry-point `forecast()` to retrieve probabilistic demand distributions:

```python
from forecasting.api import forecast

# Generate 14-day cumulative demand forecast with full quantiles
df_forecast = forecast(
    store_id="STORE_001",
    product_ids=["PROD_MILK_1L", "PROD_BREAD", "PROD_COOKING_OIL_1L"],
    horizon_days=14,
    grid_step=0.05
)

# Output contains:
# store_id, product_id, horizon_days, forecast_date,
# p10, p50, p90, quantiles (dict q05..q95), sample_paths (20 trajectories),
# shock_active, widening_factor, model_name, features_used
print(df_forecast[["product_id", "p10", "p50", "p90", "shock_active"]])
```

### For Member 5 (Model Swapping & Pipeline Config)
Swap underlying models dynamically using the model registry:

```python
from forecasting.registry import ModelRegistry, get_model
from forecasting.api import forecast

# List available registered models
print(ModelRegistry.list_models())

# Run forecast with a specific baseline or model family
df_naive = forecast(
    store_id="STORE_001",
    product_ids=["PROD_MILK_1L"],
    horizon_days=7,
    model_name="seasonal_naive" # or "gb_quantile", "moving_average", "exponential_smoothing"
)
```

### Component A: Market Signal Intelligence
Extract structured pattern shifts and review intents:

```python
from mock_data.generator import load_or_generate_mock_dataset
from market_signals.pipeline import detect_all_signals

data = load_or_generate_mock_dataset()
signals_df = detect_all_signals(data["sales"], data["reviews"], store_id="STORE_001")

# Output schema conforming to CONTRACT.md:
# signal_id, product_or_category, type, evidence, confidence, date
print(signals_df.head())
```

---

## 3. Deliverables & Documentation Index

- **Shared Contracts:** [CONTRACT.md](CONTRACT.md) — Exact input/output schemas, JSON examples, function signatures.
- **Architecture Guide:** [ARCHITECTURE.md](ARCHITECTURE.md) — System flow, component interaction, and handoff guide for collaborating agents.
- **Documented Assumptions:** [ASSUMPTIONS.md](ASSUMPTIONS.md) — Shock widening factor ($1.50\times$), cold-start shrinkage threshold, calibration parameters.
- **Progress Log:** [PROGRESS.md](PROGRESS.md) — Phase-by-phase implementation log and test pass reports.
- **Benchmark Report:** [reports/BENCHMARK_REPORT.md](reports/BENCHMARK_REPORT.md) — Model comparison across 7, 14, and 30-day horizons.
- **Ablation Report:** [reports/ABLATION_REPORT.md](reports/ABLATION_REPORT.md) — 4-tier feature ablation results and null-result gating.
- **Calibration Report:** [reports/CALIBRATION_REPORT.md](reports/CALIBRATION_REPORT.md) — 80% coverage verification and interval width tables.
- **Reproduction Notebook:** [notebooks/reproduce_results.ipynb](notebooks/reproduce_results.ipynb) — Executable walkthrough reproducing key results.
- **Mock Data Provider:** [mock_data/README.md](mock_data/README.md) — Isolated Member 1 data mock with ground-truth signals.
