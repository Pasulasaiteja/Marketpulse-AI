# Member 5: Integration, Opportunity Discovery, Interface and Evaluation

**Owns:** Component D (Opportunity Discovery), the Decision API, the retailer interface, end-to-end evaluation, demo, and final assembly.
**Consumes:** every other member's module.

## Description

This member turns four separate modules into one working product. They build the Decision API that chains extraction, forecasting, optimization, and explanation; the retailer-facing interface; and the exploratory Opportunity Discovery component. They also run the end-to-end evaluation and prepare the demo. Component D is the ambitious part: it must always label hypothesized demand as hypothesized, never as a forecast.

## Shared Contracts (owned by this member; enforce them in week 1)

- Write and publish a single **interface spec** (JSON schemas) for: canonical data, forecast output, optimizer plan, extraction profile, signal output
- Maintain a shared repo layout, CI, and mock implementations so members can develop against stubs
- **Pipeline order:** profile extraction -> data/context -> forecast -> optimize -> explain

## Task List

### A. Integration foundations (do first)
- [ ] Repo structure, linting, CI, environment setup, shared config
- [ ] Mock/stub versions of each module so nobody is blocked
- [ ] Interface spec document and schema validation at module boundaries

### B. Decision API
- [ ] Endpoints: `/profile/extract`, `/profile/confirm`, `/plan`, `/ask`, `/opportunities`
- [ ] Orchestration with clear error handling when any module fails or returns low confidence
- [ ] Audit log across the whole request
- [ ] Caching and reasonable response times

### C. Retailer interface
- [ ] Input: shop description (free text), CSV upload for sales/stock/costs, budget
- [ ] Parsed-field confirmation screen (edit any field)
- [ ] Plan view: what to buy, how much, why, expected profit/cost, what could go wrong
- [ ] Budget slider/field that re-runs the plan live (5,000 to 3,000 demo)
- [ ] Chat box for "why?" questions in any supported language
- [ ] Clear uncertainty indicators and "not enough confidence" flags
- [ ] Mobile-friendly layout (target users are small retailers)

### D. Opportunity Discovery (Component D)
- [ ] Candidate generation: unmet-demand signals, category growth, catalogue gaps, comparable products
- [ ] Score each on demand potential, competition, profitability, capital requirement, uncertainty
- [ ] **Observed vs hypothesized** labeling in data model and UI
- [ ] Hypothesized demand estimated from comparables with explicit wide intervals
- [ ] Optionally pass a small trial order to Member 3's optimizer

### E. End-to-end evaluation
- [ ] Cross-language consistency run (same shop, multiple languages)
- [ ] Full-pipeline backtest combining Members 2 and 3 results
- [ ] Collect and present all reports: forecast accuracy, ablation, optimizer backtest, extraction accuracy
- [ ] Failure-mode review: sparse data, missing sources, low-confidence extraction

### F. Demo and documentation
- [ ] Script the three demo scenarios: budget change, shop description edit, non-English "why?"
- [ ] Prepare fallback demo data in case live sources fail
- [ ] Final README, architecture diagram, setup guide, limitations and risks section

## Tests

| Test | Pass condition |
|---|---|
| Contract tests | Every module boundary validates against the JSON schemas; mismatches fail CI |
| End-to-end happy path | Free-text description + CSV + budget produces a full plan and explanation |
| Budget demo | Changing 5,000 to 3,000 updates plan within target time, cost never exceeds budget |
| Description edit demo | "near a school" to "near a market" changes context features and plan |
| Failure injection | Kill each module in turn; API returns a graceful, honest error or fallback |
| Low confidence | Ambiguous input produces a follow-up question in UI |
| Opportunity labeling | Every opportunity output is tagged observed or hypothesized; none presented as a forecast |
| Cross-language consistency | Same shop in different languages gives nearly the same plan |
| UI testing | Core flows work on mobile screen size; edits propagate |
| Load/latency | Meets agreed response time for single-user demo |
| Number integrity | Numbers shown in UI and chat match optimizer output exactly |

## Deliverables

1. Interface specification and schemas (week 1)
2. Repo, CI, and stub modules (week 1)
3. Working Decision API
4. Retailer web interface
5. Opportunity Discovery module with observed/hypothesized labeling
6. Consolidated evaluation report combining all members' results
7. Demo script, backup data, and recorded walkthrough
8. Final documentation: README, architecture, setup, limitations
9. Integrated, tagged release

## Suggested Timeline (adjust once deadline is known)

| Phase | Focus |
|---|---|
| 1 | Contracts, stubs, datasets, model hosting setup |
| 2 | Each member builds and tests their module against stubs |
| 3 | Swap stubs for real modules, integrate, fix boundaries |
| 4 | Evaluation, ablations, demo polish, documentation |
