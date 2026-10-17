# MarketPulse AI

An AI-powered market intelligence and inventory decision system for small retailers, anywhere in the world.

MarketPulse AI turns market and local context into a budget-constrained purchasing plan. A retailer can ask, for example: *"I have a budget of 5,000 (in my local currency). Which products should I prioritize next month, and how much should I order?"* The system answers with a purchasing plan, its assumptions, the expected financial consequences, and a clear flag wherever uncertainty is too high for a confident recommendation.

> All figures in this document are illustrative. They are not predictions from an existing model.

## The Problem

Small retailers face two connected questions that are usually answered separately, often from intuition:

- **What should I sell?** Which products are gaining demand, which categories are underserved, and what will customers want next?
- **How much should I stock?** Given limited capital, supplier lead times, and uncertain demand, how much should I buy?

A retailer might spot a promising product but over-order it, or forecast existing products well while missing a new opportunity. MarketPulse AI combines market intelligence, demand forecasting, and inventory optimization into one decision pipeline.

## Core Principle

**Machine learning estimates demand. Optimization decides purchases. The language model translates and explains.**

The LLM never performs forecasting or financial calculations through free-form reasoning. Every quantity and recommendation comes from the underlying analytical systems, and each component can be tested independently.

## Architecture

```
                    RETAIL DATA
                        |
          +-------------+-------------+
          |                           |
    Internal Data               Market Signals
  (sales, stock, costs)      (reviews, prices, context)
          |                           |
          +-------------+-------------+
                        |
                 Data Processing
                        |
          +-------------+-------------+
          |                           |
   Demand Forecasting         Opportunity Mining
          |                           |
          +-------------+-------------+
                        |
                Inventory Optimizer
                        |
                Decision API / Tools
                        |
                AMD-hosted LLM
                        |
          +-------------+-------------+
          |                           |
    Recommendations              Explanations
          |                           |
          +-------------+-------------+
                        |
                Retailer Interface
```

## How It Works

1. **Retailer input.** The retailer describes their shop and location in their own language, and provides sales, stock, costs, and budget.
2. **LLM extraction.** The LLM converts the description into a fixed, language-neutral schema (location type, income band, payday, nearby anchors, and so on) with a confidence score per field. The retailer confirms or corrects the parsed fields.
3. **Forecasting.** Expected demand and prediction intervals are computed per product.
4. **Optimization.** Order quantities are chosen under budget, lead time, minimum order, storage, and expiry constraints.
5. **Explanation.** The LLM explains the plan in the retailer's language, using only the optimizer's outputs.

## Components

### A. Market Signal Intelligence
Identifies changes in demand and potential opportunities from historical sales, catalogue data, reviews, public price information, seasonality, and regional indicators where reliable. An NLP pipeline classifies feedback into needs, complaints, and emerging preferences; a statistical pipeline detects shifts in sales patterns. Output is a set of structured signals with evidence and confidence.

> Online attention does not necessarily mean local sales. Signals influence demand estimates only once their predictive value has been established.

### B. Demand Forecasting Engine
Estimates demand over a planning horizon (7, 14, or 30 days) with uncertainty. Approaches to benchmark:

- Seasonal-naive forecasting
- Moving averages and exponential smoothing
- Gradient-boosted regression with lagged sales and calendar features
- A suitable statistical forecasting model
- A more advanced time-series model, if the data supports it

Uncertainty matters: ordering 120 units when demand ranges from 95 to 150 is a different risk from ordering 120 when it could range from 20 to 250.

### C. Inventory Optimization Engine
Converts forecasts into purchasing decisions, considering current inventory, expected demand, lead times, minimum order quantities, purchase prices, working capital, storage, expiry, and expected margins.

Baseline order quantity:

```
Q_i = max(0, D_i + SS_i - I_i - P_i)
```

- `Q_i`: recommended order quantity for product *i*
- `D_i`: forecast demand over the replenishment period
- `SS_i`: safety stock
- `I_i`: usable inventory on hand
- `P_i`: inventory already on order

This is a starting point. The stronger formulation treats each product as a **newsvendor problem**, so the optimal order is a quantile of the demand distribution set by margin versus stockout and holding cost. Uncertainty then directly changes the quantity. The budget is allocated to the products with the highest expected profit per unit of currency spent (greedy or a small integer program). The system may recommend fewer units of a high-uncertainty product even when predicted demand is high, because excess stock ties up capital.

### D. Opportunity Discovery
Identifies products the retailer does not yet stock, using unmet demand signals, category growth, review analysis, catalogue gaps, supplier availability and margins, and comparable products. Each opportunity is assessed on demand potential, competition, profitability, capital requirements, and uncertainty.

The system distinguishes **observed demand** from **hypothesized demand**. A product the retailer has never sold cannot be honestly forecast from that retailer's history alone; it needs external data, comparable products, or an explicitly uncertain estimate.

### E. AI Decision Assistant
A natural-language interface to the analytical system. A retailer can ask, *"Why are you recommending fewer units of Product A even though demand is increasing?"* The assistant retrieves the actual forecasts, inventory data, supplier constraints, and optimizer results, then explains them. It never invents financial figures.

## Context Layer

Real-time and local context feeds the math as model inputs.

| Tier | Examples | How it is used |
|---|---|---|
| Calendar and place | Paydays, public holidays, school terms, religious and cultural festivals, seasons, market days, location type | Forecast features |
| Economic | Inflation, exchange rates, fuel prices, supplier prices | Margins and purchasing power |
| Political and shocks | Strikes, unrest, road closures, shortages | Alerts that widen intervals and raise safety stock |

- **Cold start.** For a new retailer, location and population class pull priors from similar stores through clustering or a hierarchical model.
- **Effect sizes** are learned from data where possible. Otherwise they are explicit assumptions with wide intervals, labeled as such. The LLM never silently picks a multiplier.
- **Guardrails.** Schema validation, bounded adjustments, an audit trail (what was said, what was extracted, what changed), and retailer correction of any field.
- **Fallbacks.** Every real-time feature needs a fallback for when the data source is unavailable.
- **Regional adapters.** Calendars, currencies, and data sources are pluggable per region, so the core pipeline stays the same everywhere.

## Multilingual Support

Retailers describe their shop in the language they use every day, and one schema serves all of them.

- **Code-switching.** Mixed-language text, dialects, and informal registers are tested explicitly.
- **Normalizers.** Informal money, quantities, and dates ("30k", "5,000", "end of the month", "the 25th") are parsed according to locale and shown back for confirmation.
- **Local geography.** A geocoding service or a small regional gazetteer maps neighborhoods, markets, and landmarks to location types, with a follow-up question as fallback.
- **Replies** come back in the retailer's language, while all numbers come from the optimizer.
- **Low confidence** triggers a short follow-up question rather than a guess.
- **Model.** An open-weight multilingual model hosted on AMD hardware, selected by testing on our own examples. Low-resource languages and dialects are scoped explicitly per release.

## What Makes It Competitive

1. **Capital-aware purchasing.** Given limited capital, which combination of products maximizes expected profit while controlling stockout risk? The optimizer is compared against equal budget allocation, reorder from historical averages, and fixed-threshold reordering.
2. **Market signals that earn their place.** An ablation tests sales only, then adds calendar features, economic indicators, and shock flags, keeping only what lowers forecast error. A null result is still a valid, credible finding.
3. **Explainable recommendations under uncertainty.** Each plan states what to buy, how much, why, expected profit or cost, what could make it wrong, and what happens under a different budget.

## Evaluation Plan

- **Optimizer backtest** against the baselines above on a public retail dataset (M5 or Favorita), then on local or synthetic data. Metrics: profit, stockouts, excess inventory, capital utilization.
- **Forecast accuracy and interval calibration** for each feature tier.
- **Extraction accuracy** on about 100 hand-labeled shop descriptions, split across the supported languages and code-switched text, reported per language.
- **Cross-language consistency.** The same shop described in different languages should produce nearly the same forecast.

## Demo Scenarios

- Change the budget from 5,000 to 3,000 and watch the purchasing plan change.
- Edit the shop description (for example, "near a school" to "near a market") and watch the forecast and plan update.
- Ask "why?" in a non-English language and receive an answer grounded in the optimizer's output.

## Scope and Priorities

The demoable core is **B + C + E** (forecast with intervals, budget-constrained optimizer, LLM explainer), plus the extraction layer. Component D is the ambitious, exploratory part and must always label hypothesized demand as such.

## Risks

- Sparse, informal, or paper-based local sales data
- Overfitting when many features meet little data
- Patchy real-time data sources, which vary by region
- Weak LLM performance on low-resource languages and local geography
- Scope creep across five components

## Open Questions

- Project deadline and team size
- Availability of real retailer data
- Which regions and data sources to support first
- Which languages to officially support

## System Integration & Architecture Status

**Status:** Fully integrated, connected end-to-end, and verified across all team member components without relying on mock data for the production execution flow.

### Integrated Components Map

| Component | Repository Folder | Core Responsibility & Technologies | Integration Adapter |
|---|---|---|---|
| **Member 1: Data Layer & Context** | `components/data-layer/` | Catalog processing, continuous date reindexing, real store sales extraction (`STORE_001`–`STORE_010`), regional context engine (calendar, paydays, economic indicators). | `src/marketpulse/adapters/data_layer.py`, `TeamContextBuilder` |
| **Member 2: Demand Forecasting & Signals** | `components/forecasting/` | Statistical signal pipeline (change point spikes, trend shifts), multi-model quantile forecasting (LightGBM, Hierarchical Sparse Pooling, Seasonal-Naive, Moving Average). | `TeamForecaster`, `TeamSignalProvider` |
| **Member 3: Inventory Optimization** | `components/optimizer/` | Newsvendor quantile optimization, integer budget allocation, minimum order quantities (MOQ), pack sizes, shelf-life caps, budget sensitivity analysis. | `TeamOptimizer` |
| **Member 4: LLM Layer & Explanations** | `components/llm/` | OpenAI-compatible AMD LLM client, multilingual profile extractor with Karachi gazetteer, RFC 6901 number guard, grounded natural language decision explanations. | `TeamExtractor`, `TeamExplainer` |
| **Member 5: Orchestration, API & UI** | `src/marketpulse/` | Contract boundary validation (`validate_payload`), structured audit log (`logs/audit.jsonl`), FastAPI endpoints (`/profile/*`, `/plan`, `/ask`, `/stores`, `/opportunities`), zero-build responsive retailer interface (`src/marketpulse/ui`). | `src/marketpulse/service.py`, `src/marketpulse/api/app.py` |

---

## Setup & Installation

### 1. Prerequisites
- Python 3.10+ (tested on Python 3.10 – 3.13)
- Virtual environment tool (`venv` or `conda`)

### 2. Environment Setup
```bash
# Clone and enter the workspace
cd Marketpulse-AI

# Create and activate a virtual environment
python -m venv .venv
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1
# On Linux / macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

---

## Required Environment Variables

Configure these variables according to your deployment target:

| Variable | Default Value | Description |
|---|---|---|
| `MARKETPULSE_LLM_BACKEND` | `amd` (if credentials present) / `mock` | Selects LLM backend: `amd` for live AMD/OpenAI-compatible LLM endpoint, `mock` for deterministic offline rule-based extraction & templating. |
| `AMD_BASE_URL` | `https://api.amd.com/v1` | Base URL of the AMD-hosted inference endpoint (OpenAI chat completions compatible). |
| `AMD_API_KEY` | *(None)* | API authentication key for the AMD LLM service. |
| `AMD_MODEL` | `meta-llama/Llama-3-70b-instruct` | Model identifier deployed on the AMD cluster. |
| `MARKETPULSE_USE_MOCKS` | `false` | When `false` (default), the application loads live team modules (`TeamExtractor`, `TeamForecaster`, `TeamOptimizer`, `TeamExplainer`, `TeamContextBuilder`, `TeamSignalProvider`). Set to `true` only to isolate unit tests to synthetic mock modules. |
| `MARKETPULSE_FORECAST_MODEL` | *(Auto-selected)* | Optional override for forecasting model: `lightgbm`, `hierarchical_sparse_pooling`, `seasonal_naive`, or `moving_average`. |

Example `.env` configuration:
```bash
# Live AMD LLM Deployment
MARKETPULSE_LLM_BACKEND=amd
AMD_BASE_URL=https://your-amd-cluster-endpoint.com/v1
AMD_API_KEY=your_live_api_key_here
AMD_MODEL=meta-llama/Llama-3-70b-instruct
MARKETPULSE_USE_MOCKS=false
```

---

## How to Run the Application

### 1. Launch the Decision API & Retailer UI
Start the FastAPI server:
```bash
uvicorn --app-dir src marketpulse.api.app:app --host 0.0.0.0 --port 8000 --reload
```
Once started, access:
- **Retailer Web Interface:** [http://localhost:8000/ui](http://localhost:8000/ui) (or [http://localhost:8000/](http://localhost:8000/))
- **Interactive Swagger Documentation:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **OpenAPI Schema:** [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)

### 2. Run End-to-End Evaluation on Real Retailer Data
Execute the evaluation harness across real multi-store processed datasets from Member 1:
```bash
python scripts/evaluate_e2e.py . --stores 3 --out reports/e2e_metrics.json
```

---

## Verification & Test Results

All individual component test suites and the root integrated system test suite have been executed and verified passing (total: **332 passed tests**):

| Test Suite | Path | Tests Passed | Duration | Status |
|---|---|---|---|---|
| **Root System & Integration** | `tests/` | **154 passed** (2 skipped) | 200s | **PASS** |
| **Member 1 (Data Layer & Context)** | `components/data-layer/tests/` | **14 passed** | 191s | **PASS** |
| **Member 2 (Forecasting & Signals)** | `components/forecasting/tests/` | **20 passed** | 63s | **PASS** |
| **Member 3 (Optimizer)** | `components/optimizer/tests/` | **23 passed** | 16s | **PASS** |
| **Member 4 (LLM Layer)** | `components/llm/tests/` | **121 passed** | 1.1s | **PASS** |
| **Total** | | **332 passed** | | **100% PASS** |

### Commands to Run Tests
```bash
# Run root integration tests
python -m pytest tests

# Run Member 1 tests
cd components/data-layer && python -m pytest tests && cd ../..

# Run Member 2 tests
cd components/forecasting && python -m pytest tests && cd ../..

# Run Member 3 tests
cd components/optimizer && python -m pytest tests && cd ../..

# Run Member 4 tests
python -m pytest components/llm/tests
```

---

## Key Integration Highlights

1. **Non-Fabrication & Strict Number Grounding:**
   The AI Explainer strictly enforces RFC 6901 JSON pointer citations (`/total_cost`, `/budget`, `/expected_total_profit`, `/lines/{i}/order_qty`, etc.). If an ungrounded or hallucinated number is detected, the number guard safely rejects the response and provides a verified grounded fallback.
2. **Deterministic Multilingual Support:**
   Full extraction and grounded explanation support across English (`en`), French (`fr`), Spanish (`es`), Hindi (`hi`), Urdu (`ur`), Arabic (`ar`), and Swahili (`sw`).
3. **Continuous Real-World Date Alignment:**
   Integrated Member 1's continuous date reindexer with Member 2's time-series forecasting, ensuring zero pandas datetime/date comparison type mismatches.
4. **Context-Sensitive Optimization:**
   Local context (nearby schools, markets, paydays, holidays) is converted into validated context features that guide demand estimations and adjust safety stock allocations.

---

## Remaining Considerations & Operational Notes

- **Network Availability for Live AMD Host:** If network connectivity to the AMD LLM cluster is interrupted or rate limits are reached, the system gracefully falls back to deterministic rule-based extractions and verified templates with audit logging.
- **Cold-Start Products:** Products with zero sales history rely on hierarchical category pooling and regional priors; the system explicitly flags low data confidence on these items.
- **Multi-Store Scope:** Optimization is performed on a per-store basis with independent budget constraints; chain-level global budget redistribution across stores remains a candidate for future extension.
