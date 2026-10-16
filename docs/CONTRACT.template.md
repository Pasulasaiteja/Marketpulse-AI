# MarketPulse AI: Interface Contract (v1.0, DRAFT for team review)

> **Generated file.** Edit `docs/CONTRACT.template.md`, then run
> `python scripts/build_contract_md.py`. Every JSON example below is produced by the
> mock modules and validated against the real schemas, so it cannot drift from the code.
> A test fails if this file is stale.

**Owner:** Member 5 (integration). **Status:** draft, nobody else has reviewed it yet.
Sections marked **DECISION NEEDED** are things I could not settle alone.

## 0. How to use this

- Machine-readable schemas: `src/marketpulse/contracts/schemas/<Name>.schema.json`
  (generated from `src/marketpulse/contracts/models.py`).
- Python: `from marketpulse.contracts.validate import validate_payload`;
  `validate_payload("ForecastOutput", obj)` checks structure (JSON Schema) **and** the
  semantic rules in section 5. Run it on your own output before returning it.
- Mocks of every module live in `src/marketpulse/mocks/`. Develop against them.
- All objects reject unknown fields (`extra="forbid"`). Misspelled or extra fields fail.
- `schema_version` is `"1.0"` on every top-level object. Any breaking change bumps it.

## 1. Pipeline order and module ownership

```
description -> [1 extractor] -> profile (retailer confirms/edits)
CSV -> [API loader] -> CanonicalData
(optional) [signals] -> SignalOutput
profile + as_of -> [2 context] -> ContextFeatures
CanonicalData + profile + context (+ signals) -> [3 forecaster] -> ForecastOutput
ForecastOutput + CanonicalData + budget -> [4 optimizer] -> OptimizerPlan
OptimizerPlan + ForecastOutput + question + language -> [5 explainer] -> Explanation
```

| Step | Module | Assumed owner | Notes |
|---|---|---|---|
| 1 | `Extractor` | extraction / LLM member | **DECISION NEEDED** (Q-A) |
| 2 | `ContextBuilder` | **unassigned** | **DECISION NEEDED** (Q-B) |
| 3 | `Forecaster` | Member 2 | task file says "Members 2 and 3" results |
| 4 | `Optimizer` | Member 3 | task file says "Member 3's optimizer" |
| 5 | `Explainer` | extraction / LLM member | **DECISION NEEDED** (Q-A) |
| - | `SignalProvider` | Member 1 (Component A) | optional input |
| - | CSV loader, API, UI, Component D (`DiscoveryEngine`) | Member 5 | |
| - | Catalogue data (`CatalogueItem`): supplier prices, public prices, customer requests | **unassigned** | **DECISION NEEDED** (Q-H); a synthetic sample is used until then |

## 2. Function signatures

Python entry points. Real modules and mocks must expose exactly these (see
`src/marketpulse/contracts/interfaces.py`). Types are the models in section 4.

```python
extract_profile(description: str, language_hint: str | None = None) -> ExtractionProfile

build_context(profile: ExtractionProfile, as_of: date, horizon_days: int,
              signals: SignalOutput | None = None) -> ContextFeatures

forecast(data: CanonicalData, profile: ExtractionProfile, context: ContextFeatures,
         horizon_days: int, signals: SignalOutput | None = None) -> ForecastOutput

optimize(forecast: ForecastOutput, data: CanonicalData, budget: float,
         constraints: OptimizerConstraints | None = None) -> OptimizerPlan

explain(plan: OptimizerPlan, forecast: ForecastOutput, question: str | None = None,
        language: str = "en") -> Explanation

get_signals(data: CanonicalData | None, as_of: date) -> SignalOutput

# Component D (Member 5). `optimizer` is only used to size trial orders.
DiscoveryEngine(optimizer: Optimizer | None).discover(
    data: CanonicalData, catalogue: list[CatalogueItem], signals: SignalOutput | None,
    budget: float, horizon_days: int, include_trial_orders: bool = True) -> OpportunityOutput
```

Rules for every module:

- Pure with respect to arguments (no hidden global state affecting the result).
- On failure raise `marketpulse.contracts.errors.ModuleFailure(module, code, message, retryable)`.
  Never return partial or invented output.
- Only use data dated `<= as_of`. No future information (no leakage).
- The explainer must not compute or change any number (core principle).

## 3. Core principle as it applies here

Machine learning estimates demand (forecaster). Optimization decides purchases (optimizer).
The LLM translates and explains (extractor, explainer). Therefore: no field in
`Explanation` may introduce a number that is not in the `OptimizerPlan`
(checked by `check_explanation_numbers`), and opportunities are never forecasts
(`is_forecast` is always `false`).

## 4. Schemas

### 4.1 ExtractionProfile (extractor -> API, context, forecaster)

One language-neutral schema for every language. Each field carries `value`, `confidence`
(0..1), `source` (`llm` / `retailer` / `default`) and optional `evidence`. `value` is `null`
when unknown. After the retailer confirms, `status` becomes `confirmed`, edited fields get
`source: "retailer"` and `confidence: 1.0`, and each change is listed in `edits`.
`payday_day` normalizes informal dates ("end of the month" -> 28).
**`profile_id` is assigned by the API** (the extractor's value is replaced), so two shops with
identical text never collide and re-extraction never overwrites a confirmed profile.

{{example:ExtractionProfile}}

### 4.2 CanonicalData (API loader -> forecaster, optimizer)

Built from the retailer's CSV upload. One row per product per day in `sales`; a day with
no row is treated by the mock as zero sales (**DECISION NEEDED** Q-C: or missing?).
`stockout: true` marks censored demand.

{{example:CanonicalData}}

### 4.3 SignalOutput (Component A -> context, Component D)

Signals move forecasts only when `predictive_value_established` is `true`.

{{example:SignalOutput}}

### 4.4 ContextFeatures (context builder -> forecaster)

Horizon-level features with a tier. `is_assumption` is `true` when the value is hand-set.
If a source is down: `source_available: false`, `fallback_used: true`.
`alerts[].widen_interval_factor >= 1` must be applied to forecast intervals.

{{example:ContextFeatures}}

### 4.5 ForecastOutput (forecaster -> optimizer, explainer)

Quantiles are on a **fixed grid** (`config.QUANTILE_GRID`) so the optimizer can read any
service level by linear interpolation (`ProductForecast.quantile(p)` does this).
Demand is in units over `horizon_days`. Example shows one product of the real output.

{{example:ForecastOutput}}

### 4.6 OptimizerPlan (optimizer -> API, explainer, UI)

All money in the shop currency, 2 decimals. The plan must satisfy the semantic rules in
section 5 (cost never exceeds budget; sums consistent). `reason_codes` are a closed
vocabulary so the explainer can speak about each line without inventing reasons.
`budget_sensitivity` is optional and answers "what happens under a different budget".

{{example:OptimizerPlan}}

### 4.7 Explanation (explainer -> API, UI)

`text` is in `language`. Every standalone number in `text` must appear in
`cited_figures` with a JSON Pointer into the plan and the exact plan value.
Text uses ASCII digits and `.` as the decimal separator with no thousands separators;
the UI localizes display separately. Identifiers (e.g. `P002`) contain a letter.

{{example:Explanation}}

### 4.8 OpportunityOutput (Component D, Member 5)

Products the retailer does **not** stock. Nothing here is a forecast (`is_forecast` is always
`false`), and every opportunity is exactly one of:

- **`observed`**: the shop's own data shows people asking for this exact item (logged customer
  requests). Range = 95% Poisson interval on the request count, scaled to the horizon. Requests are a
  **lower bound** on demand (most customers never ask); 1 request is taken as 1 unit wanted.
- **`hypothesized`**: never sold here. Estimated from comparable products the shop does sell
  (similarity-weighted mean of their units over the last `horizon_days`, times a new-product
  discount), with a deliberately **wide** range (`high/low >= 2.0`, wider with few comparables).
  Signals can move this number only if `predictive_value_established` is true.

Scores (each 0..1): `demand_potential` (mid relative to the median current product, capped at 1),
`competition` (sellers / 10, neutral 0.5 if unknown), `profitability` (margin / 40%),
`capital_requirement` (min order cost / budget), `uncertainty` (relative width of the range).
`notes` is a closed vocabulary (e.g. `FEW_COMPARABLES`, `SIGNALS_NOT_VALIDATED`). `excluded` lists
catalogue items that were not assessed and why. `trial_order_qty` / `trial_cost` are copied from the
optimizer (never computed here); they are `null` and `trial_orders_available` is `false` if the
optimizer was unavailable.

{{example:OpportunityOutput}}

### 4.9 CatalogueItem (catalogue source -> Component D) **DRAFT INPUT, needs an owner (Q-H)**

One candidate product from a supplier catalogue and public price data. `requests` is the count of
customer requests logged by the retailer (reviews, messages, a notebook) for an item they do not stock.

`POST /opportunities` also accepts the same rows as CSV text (`catalogue_csv`). Columns:
`item_id,name,unit_cost,unit_price` (required) and
`category,supplier_min_order_qty,supplier_available,sellers_count,requests_count,requests_window_days,requests_source,source`
(optional; blank `sellers_count` = unknown; `requests_count` requires `requests_window_days`).
`marketpulse.csvloader.load_catalogue_csv` / `dump_catalogue_csv` read and write this format.

{{example:CatalogueItem}}

### 4.10 ModuleError (API -> UI when a module fails)

{{example:ModuleError}}

## 5. Semantic rules (enforced by Pydantic, not expressible in JSON Schema)

If you validate with a plain JSON Schema library in another language, also check these.

1. `CanonicalData`: unique `product_id`; every sales `product_id` exists; no sales `date > as_of`.
2. `ProductForecast.quantiles`: exactly the grid `0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95`, values non-decreasing.
3. `horizon_days` is one of 7, 14, 30 (`ContextFeatures`, `ForecastOutput`).
4. `OptimizerPlan`: `line_cost == order_qty * unit_cost` (+/- 0.01); `total_cost == sum(line_cost)` (+/- 0.01);
   `total_cost <= budget`; `capital_utilization == total_cost / budget`; unique `product_id` per line.
5. `Opportunity`: `is_forecast` is always false; `demand.low <= mid <= high`; hypothesized requires
   `high/low >= 2.0`, at least one comparable, and no `observed_requests`; observed requires
   `observed_requests` or `evidence`; `trial_order_qty` and `trial_cost` are given together or not at all.
6. `Explanation`: numbers grounded in the plan (`marketpulse.contracts.integrity`).
7. Low-confidence rule (applied by the API, not the extractor): a profile field with a value
   and `confidence < 0.7`, or a missing required field (`location_type`, `country`,
   `currency`), blocks `/plan` and produces a follow-up question.

## 6. Failure handling

A module raises `ModuleFailure`. The API never hides it: it returns a `ModuleError` and, where a
documented fallback exists, sets `fallback_used: true` and says so to the retailer.
No module may silently substitute a guess.

## 6b. Decision API (what the UI and the demo call)

`uvicorn marketpulse.api.app:app`. All bodies are JSON; unknown request fields are rejected (422).
Every error has the shape `{"status": "error", "request_id": ..., "error": {"code", "message", "module_error"?}}`.

| Endpoint | Request | Success response |
|---|---|---|
| `POST /profile/extract` | `description`, `language_hint?` | `status: "needs_confirmation"`, `profile`, `follow_up_questions`, `low_confidence_threshold`, `required_fields` |
| `POST /profile/confirm` | `profile_id`, `edits?` (`{field: new_value}`) | `status: "confirmed"` or `"needs_input"` (required field still missing) |
| `POST /plan` | `profile_id`, `budget`, `horizon_days?` (7/14/30, default 14), `language?`, and ONE data source: `data` (CanonicalData) / `dataset_id` / `products_csv`+`sales_csv` | `status: "ok"`, `plan`, `forecast`, `explanation` (may be `null`), `warnings`, `timings_ms`, `cache.forecast_hit`, `latency`, `dataset_id`, `request_id`, `product_names` (`{product_id: name}`, display only) |
| `POST /ask` | `request_id` (of a plan), `question`, `language?` | `explanation` (grounded) |
| `POST /opportunities` | `profile_id`, `budget`, `horizon_days?`, ONE data source (as `/plan`), and a catalogue source: `catalogue?` (list of `CatalogueItem`) or `catalogue_csv?` (CSV text; columns in 4.9); omitted = invented sample catalogue, `include_trial_orders?` (default true) | `status: "ok"`, `opportunities` (OpportunityOutput), `catalogue_source` (`sample_synthetic`/`provided`/`provided_csv`), `warnings`, `timings_ms`, `dataset_id` |
| `GET /demo/catalogue` | none | `items` (CatalogueItem list), `synthetic: true`: invented sample catalogue |
| `POST /stores` | `profile_id`, `products_csv`, `sales_csv` (sales has a `store_id` column; products may have one, blank = shared by all stores), `as_of?` | `status: "ok"`, `currency`, `stores`: list of `{store_id, dataset_id, products, history_days, as_of}`. Use each `dataset_id` with `/plan` and `/opportunities`; stores never share rows. `CanonicalData` is unchanged: one store = one `shop_id`. |
| `POST /chain/plan` | `profile_id`, `budget` (default per-store budget), `dataset_ids` (from `/stores`, >= 1), `horizon_days?`, `language?`, `store_budgets?` (`{dataset_id: budget}` overrides), `constraints?` | `status: "ok"`, `chain` (aggregate: `total_budget`, `total_cost`, `expected_total_profit`, `expected_profit_interval?`, `capital_utilization`, `stores_planned`, `stores_failed`, `allocation: "independent"`), `stores` (per-store `plan`, `forecast`, `explanation`, `warnings`, `timings_ms`, `cache`, `request_id`, `store_id`, `dataset_id`), `failures`, `warnings`, `timings_ms`. Each store is optimised with its **own** budget; no money moves between stores. A store that fails is listed in `failures` and the others still plan; if none can be planned -> 502. All stores must share one currency (else 422 `MIXED_CURRENCY`). |
| `GET /demo/chain` | none | `products_csv`, `sales_csv` for 3 invented stores, `synthetic: true` |
| `GET /demo/files` | none | `products_csv`, `sales_csv`, `synthetic: true`: invented sample shop (demo + fallback data) |
| `GET /ui/` | none | the retailer web interface (`/` redirects here) |

Behaviour you can rely on:

- `/plan` returns `status: "needs_confirmation"` (HTTP 200, no plan) until the profile is confirmed
  and every required field is present. Confirming means the retailer accepted every value shown.
- Changing only `budget` (with `dataset_id`) reuses the cached forecast; changing the profile,
  data or horizon does not.
- Hard failures (extractor, forecaster, optimizer) -> HTTP 502 `MODULE_FAILED`, with `module_error`,
  and no plan. Soft failures degrade with a `warnings[]` entry: `SIGNALS_UNAVAILABLE`,
  `CONTEXT_FALLBACK`, `TRIAL_ORDERS_UNAVAILABLE`, `EXPLANATION_UNAVAILABLE`, `EXPLANATION_UNGROUNDED`, `CURRENCY_MISMATCH`, and, on `/chain/plan`, `STORE_FAILED` (one store skipped, the rest still plan).
- An explanation with any figure not in the plan is withheld (`explanation: null`), never shown.
- CSV formats: see `src/marketpulse/csvloader.py`. Errors name the row (HTTP 422 `CSV_INVALID`).
- State (profiles, datasets, plans, cache) is in memory and is lost on restart (local demo only).

## 7. Assumptions (hand-set, not learned from data)

{{assumptions}}

The mocks also contain hand-set effect sizes (for example +5% demand "near a school");
those are labeled `ASSUMPTION` in `src/marketpulse/mocks/forecaster.py` and are **not**
results of any analysis.

## 8. Decisions and open questions

Each item records the decision **in force in the code today** (with a pointer to where it lives) and,
where a teammate could still change it, what the integration layer needs from them. Change the code
and this section together.

- **Q-A. Owner of the extractor and explainer.** *In force:* one LLM owner (Member 4); the
  integration layer reaches it through `src/marketpulse/adapters/team_modules.py`. *Needs:* Member 4 to
  confirm.
- **Q-B. Owner of the context step.** *In force:* Member 1's regional context engine, adapted by
  `TeamContextBuilder` (`src/marketpulse/adapters/team_modules.py`); the contract stays horizon-level.
  *Needs:* Member 1 to confirm the `ContextFeatures` shape.
- **Q-C. Missing day in `CanonicalData.sales`.** *In force:* a day with no row is zero sales, not
  "unknown". The forecaster adapter reindexes to continuous dates
  (`data.pipeline.reindex_continuous_dates`) so gaps become explicit zero rows; a flagged stockout
  day is censored, not zero demand. `DiscoveryEngine._observed_units` reads gaps the same way.
  *Needs:* Member 2 to confirm.
- **Q-D. Daily calendar features.** *In force:* the contract exposes horizon-level `ContextFeatures`;
  the forecaster adapter derives its own daily payday/holiday/shock flags internally. No per-date
  section is added to the contract. *Needs:* Member 2 to confirm it does not need a daily contract.
- **Q-E. `SignalOutput` fields.** *In force:* `SignalOutput`/`Signal` as defined in 4.3, produced by
  `TeamSignalProvider` from Member 2's pipeline; `predictive_value_established` stays `false` until an
  ablation proves value. *Needs:* Member 1/Member 2 to confirm they can produce it.
- **Q-F. "Observed" vs "hypothesized" (Component D).** *In force:* observed = measured in the
  retailer's own data (their sales, or logged customer requests); hypothesized = inferred from
  comparables/priors and always shown with a wide range. *Confirmed by:* the `Opportunity` validator
  in `src/marketpulse/contracts/models.py`.
- **Q-G. Explanation number format.** *In force:* explanation and chat text use `.` decimals and no
  thousands separators (see `docs/UI_DESIGN.md`). Same values as the localized table.
- **Q-H. Catalogue data source.** *In force:* `CatalogueItem` is the input to Component D;
  `POST /opportunities` accepts a `catalogue` list **or** `catalogue_csv` (columns in 4.9), and falls
  back to an invented sample only when neither is given. *Still open:* a live supplier/price feed is
  unassigned; whoever owns reviews and price data should provide it in this shape.
- **Q-I. Trial-order sizing.** *In force:* the optimizer sizes a one-product order under
  `TRIAL_BUDGET_FRACTION` (10%) of the retailer's budget, using the labelled opportunity range as the
  demand input (a cold-start forecast; `history_days = 0`, `cold_start = true`).
  *Needs:* Member 3 to confirm it is sensible and that their optimizer handles `history_days = 0`.
- **Q-J. "Observed" for a never-stocked item.** *In force:* it means logged customer requests (or
  other explicit evidence of asking); narrowed by Q-F. Confirm with the team.
- **Q-K. `UNITS_PER_REQUEST`.** *In force:* 1 logged request = 1 unit, treated as a lower bound
  (`src/marketpulse/config.py`). *Needs:* team confirmation.
