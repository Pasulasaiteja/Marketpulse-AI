# MarketPulse AI — Inventory Optimization Engine (Component C)

> **Core Principle:** Machine learning estimates demand. Optimization decides purchases. The language model translates and explains. The LLM never forecasts or calculates financial numbers.

Component C converts demand forecast distributions and product cost catalogs into a **budget-constrained, profit-maximizing purchasing plan** for small retailers.

---

## Deliverables Summary

| Deliverable | Location | Description |
| :--- | :--- | :--- |
| **1. Optimization Engine** | [`optimizer/engine.py`](file:///C:/Users/Administrator/.gemini/antigravity/scratch/marketpulse-optimizer/optimizer/engine.py) | `optimize()` and `explain_inputs()` entry points. |
| **2. Cost & Constraints Model** | [`docs/COST_AND_CONSTRAINTS.md`](file:///C:/Users/Administrator/.gemini/antigravity/scratch/marketpulse-optimizer/docs/COST_AND_CONSTRAINTS.md) | Full mathematical formulations and assumptions. |
| **3. Backtest Harness & Report** | [`backtest/harness.py`](file:///C:/Users/Administrator/.gemini/antigravity/scratch/marketpulse-optimizer/backtest/harness.py)<br>[`docs/BACKTEST_REPORT.md`](file:///C:/Users/Administrator/.gemini/antigravity/scratch/marketpulse-optimizer/docs/BACKTEST_REPORT.md) | Multi-period rolling simulation vs. 3 baselines (+13.6% profit). |
| **4. Budget Sensitivity Demo** | [`demo/demo_sensitivity.py`](file:///C:/Users/Administrator/.gemini/antigravity/scratch/marketpulse-optimizer/demo/demo_sensitivity.py)<br>[`demo/output_5k_vs_3k.json`](file:///C:/Users/Administrator/.gemini/antigravity/scratch/marketpulse-optimizer/demo/output_5k_vs_3k.json) | Hackathon demo scenario comparing $5,000 vs. $3,000 budgets. |
| **5. Uncertainty-Flag Rules** | [`docs/UNCERTAINTY_RULES.md`](file:///C:/Users/Administrator/.gemini/antigravity/scratch/marketpulse-optimizer/docs/UNCERTAINTY_RULES.md) | Mathematical rules for relative uncertainty ($RU > 1.25$). |
| **6. Automated Test Suite** | [`tests/`](file:///C:/Users/Administrator/.gemini/antigravity/scratch/marketpulse-optimizer/tests/) | 23 comprehensive tests covering unit, constraint, IP gap, and edge cases. |
| **7. Shared Contract Schema** | [`CONTRACT.md`](file:///C:/Users/Administrator/.gemini/antigravity/scratch/marketpulse-optimizer/CONTRACT.md) | Shared input/output contract for Members 1, 2, 4, and 5. |

---

## Installation & Setup

1. **Activate Virtual Environment:**
```bash
# Windows
.venv\Scripts\activate

# Linux / Mac
source .venv/bin/activate
```

2. **Install Dependencies:**
```bash
pip install -r requirements.txt
```

---

## Quick Start: Using the Optimizer

```python
from optimizer import optimize, explain_inputs
from mocks.mock_data import get_mock_retail_store

# 1. Load data contracts (from Member 1 catalog & Member 2 forecasts)
forecasts, inventory, products = get_mock_retail_store()

# 2. Run optimization under a cash budget constraint (e.g. $3,000)
plan = optimize(
    forecasts=forecasts,
    inventory=inventory,
    products=products,
    budget=3000.0,
    max_storage_volume=None  # Optional storage cap
)

print(f"Total Spend: ${plan.total_cost:,.2f} / ${plan.budget:,.2f}")
print(f"Expected Profit: ${plan.total_expected_profit:,.2f}")
print(f"Total Units: {plan.total_items_ordered}")

# 3. Extract structured facts for Member 4's LLM Explainer
facts = explain_inputs(plan)
print(facts["budget_bottleneck"])
```

---

## Running the Automated Test Suite

Run all unit, property, and edge case tests:

```bash
pytest tests/ -v
```

All 23 tests cover:
- Closed-form Newsvendor quantile verification ($CR = 0.5 \implies y^* = \mu$).
- Theoretical uncertainty response (wider uncertainty lowers order on low-margin goods).
- Hard budget feasibility ($TotalCost \le Budget$ across all test budgets).
- 100% constraint compliance for MOQ, Pack Sizes, and Expiry Caps.
- Budget monotonicity ($Budget_2 > Budget_1 \implies Profit_2 \ge Profit_1$).
- Greedy vs. MILP optimality gap ($\ge 90\%$).
- Backtest outperformance vs. all three baselines.

---

## Running the $5,000 vs. $3,000 Live Demo

To run the interactive comparison for the hackathon presentation:

```bash
python demo/demo_sensitivity.py
```

Outputs a comparison table showing which products are **Protected** (staples), **Trimmed**, or **Dropped** (capital preserved), and exports [`demo/output_5k_vs_3k.json`](file:///C:/Users/Administrator/.gemini/antigravity/scratch/marketpulse-optimizer/demo/output_5k_vs_3k.json).

---

## Running the Backtest Simulation

```bash
python backtest/harness.py
```

Evaluates the optimizer across 6 retail cycles against:
1. Equal Budget Allocation
2. Historical Average Reordering
3. Fixed-Threshold $(s, S)$ Reordering
