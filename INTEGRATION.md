# MarketPulse AI: integration layer (Member 5)

Status: contracts, mocks, CSV loader, audit log, Decision API, the retailer web interface and
Opportunity Discovery (task D: `POST /opportunities`, `GET /demo/catalogue`, "New products to try"
screen) are built and tested (165 tests).
Multi-store: `POST /stores` splits multi-store CSVs (a `store_id` column) into one dataset per store; the UI
shows a store selector and an "All stores (chain)" aggregate view (`POST /chain/plan`);
`adapters.data_layer.load_all_stores` does the same for Member 1's files. The shared
contract is unchanged (one store = one `shop_id`).
Also built: `src/marketpulse/adapters/data_layer.py` (Member 1's data layer -> one-store CanonicalData; the
mapping and assumptions are in its docstring) and `scripts/evaluate_e2e.py` (task E, writes
`reports/e2e_metrics.json`; all modules are mocks, so the backtest checks the harness, not Member 2's model).
Run: `python scripts/evaluate_e2e.py .` (the shared datasets live in `data/processed/`).
Not built yet: demo script, backup data, walkthrough and final docs (F).
Open decisions for the team are in `CONTRACT.md` section 8 (Q-A to Q-K). Trial-order sizing (Q-I)
is a default chosen by the developer, not yet agreed.
The team-wide design is in `README.md`; the interface everyone builds against is `CONTRACT.md`.

## Install
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt     # pinned versions
```

## Run the checks
```bash
ruff check src tests scripts    # always pass paths: never lint the home directory
pytest                                  # contract tests; a mismatch fails the build
```

## Run the Decision API
```bash
uvicorn --app-dir src marketpulse.api.app:app --reload        # http://127.0.0.1:8000/docs
```
```bash
curl -s localhost:8000/profile/extract -H 'content-type: application/json' \
  -d '{"description": "Small shop near a school in Delhi, India."}'
# then /profile/confirm, then /plan (see CONTRACT.md section 6b)
```
Audit log: `logs/audit.jsonl` (one JSON line per request: what was said, extracted, changed, which steps ran).

## Retailer interface
Start the API (above) and open http://127.0.0.1:8000/ on a laptop or phone (same network).
Flow: describe the shop (or "Use an example") -> add the two CSVs (or "Use sample shop data")
-> confirm the parsed fields -> plan. Change the budget with the slider; ask "why?" in any of
English, French, Spanish, Hindi. See `docs/UI_DESIGN.md` for design notes and known limits.
Tests run in real Chromium at 375px width (`pytest tests/test_ui.py`; needs
`playwright install chromium` once; they skip automatically if Chromium is missing).

## Swap a mock for a real module
Edit one line in `src/marketpulse/registry.py` (`default_modules()`). Contract tests and API tests
then run against the real module unchanged.

## Use a contract in your module
```python
from marketpulse.contracts.validate import validate_payload
plan = validate_payload("OptimizerPlan", my_output)   # raises ContractViolation on mismatch
```
Develop against `src/marketpulse/mocks/*` (clearly separated; swap for the real module later).

## Regenerate generated files
```bash
python scripts/export_schemas.py        # JSON Schemas from the models
python scripts/build_contract_md.py     # CONTRACT.md from docs/CONTRACT.template.md
```
(The scripts add `src/` to the import path themselves; no `PYTHONPATH` needed.)
Tests fail if either is stale.

## Layout
- `src/marketpulse/`: the integration package
  - `contracts/`: models, JSON Schemas, validation, interfaces, number-integrity check
  - `mocks/`: stand-ins for extractor, context, forecaster, optimizer, explainer, signals
  - `service.py`, `api/app.py`: orchestration and endpoints
  - `ui/`: `index.html`, `app.js`, `i18n.js`, `style.css` (no build step)
  - `registry.py`, `csvloader.py`, `audit.py`
  - `config.py`: every hand-set value, registered as an ASSUMPTION
- `components/`: the four team component repositories (`data-layer/`, `forecasting/`,
  `optimizer/`, `llm/`), loaded by `src/marketpulse/adapters/team_modules.py`
- `data/`: shared datasets — `raw/` (Member 1 inputs) and `processed/` (the joint tables)
- `tests/`, `scripts/`, `docs/`, `.github/workflows/ci.yml`
