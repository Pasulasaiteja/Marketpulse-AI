"""Build CONTRACT.md from docs/CONTRACT.template.md.

Examples are produced by running the mocks and validating them against the
real contracts, so the document cannot drift from the code.
Run:  python scripts/build_contract_md.py
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from marketpulse import config
from marketpulse.contracts.validate import validate_payload
from marketpulse.mocks.catalogue import sample_catalogue
from marketpulse.mocks.context import MockContextBuilder
from marketpulse.mocks.explainer import MockExplainer
from marketpulse.mocks.extractor import MockExtractor
from marketpulse.mocks.fixtures import make_canonical_data
from marketpulse.mocks.forecaster import MockForecaster
from marketpulse.mocks.optimizer import MockOptimizer
from marketpulse.mocks.signals import MockSignalProvider
from marketpulse.opportunities.discovery import DiscoveryEngine

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "docs" / "CONTRACT.template.md"
OUT = ROOT / "CONTRACT.md"


def build_examples() -> dict[str, dict]:
    data = make_canonical_data()
    sig = MockSignalProvider().get_signals(data, data.as_of)
    prof = MockExtractor().extract_profile(
        "Small shop near a school in Delhi, India. Paid on the 25th."
    )
    ctx = MockContextBuilder().build_context(prof, data.as_of, 14, sig)
    fc = MockForecaster().forecast(data, prof, ctx, 14, sig)
    plan = MockOptimizer().optimize(fc, data, 5000)

    # Trim for readability while keeping every cross-field rule true.
    keep = [p for p in data.products][:2]
    ids = {p.product_id for p in keep}
    small_data = data.model_copy(update={
        "products": keep,
        "sales": [s for s in data.sales if s.product_id in ids][-3:],
    })
    small_fc = fc.model_copy(update={"forecasts": fc.forecasts[:1]})
    lines = [ln for ln in plan.lines if ln.order_qty > 0][:2]
    total = round(sum(ln.line_cost for ln in lines), 2)
    small_plan = plan.model_copy(update={
        "lines": lines, "total_cost": total,
        "capital_utilization": round(total / plan.budget, 4),
        "expected_total_profit": round(sum(ln.expected_profit for ln in lines), 2),
        "binding_constraints": [], "risks": [], "budget_sensitivity": plan.budget_sensitivity[:2],
    })
    exp = MockExplainer().explain(small_plan, small_fc, None, "en")
    small_sig = sig.model_copy(update={"signals": sig.signals[:2]})

    opp_all = DiscoveryEngine(MockOptimizer()).discover(
        data, sample_catalogue(), sig, 5000, 14)
    hyp = next(o for o in opp_all.opportunities if o.demand_basis == "hypothesized")
    obs = next(o for o in opp_all.opportunities if o.demand_basis == "observed")
    opp = opp_all.model_copy(update={"opportunities": [hyp, obs], "excluded": opp_all.excluded[:2]})
    out = {
        "ExtractionProfile": prof, "CanonicalData": small_data, "SignalOutput": small_sig,
        "ContextFeatures": ctx, "ForecastOutput": small_fc, "OptimizerPlan": small_plan,
        "Explanation": exp, "OpportunityOutput": opp,
        "CatalogueItem": next(c for c in sample_catalogue() if c.requests),
    }
    result = {}
    for name, obj in out.items():
        model = validate_payload(name, obj)  # examples must satisfy the real contract
        result[name] = model.model_dump(mode="json")
    result["ModuleError"] = validate_payload("ModuleError", {
        "module": "forecaster", "code": "TIMEOUT", "message": "forecaster exceeded 10s",
        "retryable": True, "fallback_used": False}).model_dump(mode="json")
    return result


def assumptions_table() -> str:
    rows = ["| Name | Value | Rationale | Owner |", "|---|---|---|---|"]
    for a in config.ASSUMPTIONS.values():
        rows.append(f"| `{a.name}` | `{a.value}` | {a.rationale} | {a.owner} |")
    return "\n".join(rows)


def render() -> str:
    ex = build_examples()
    text = TEMPLATE.read_text(encoding="utf-8")
    text = re.sub(
        r"\{\{example:(\w+)\}\}",
        lambda m: "```json\n" + json.dumps(ex[m.group(1)], indent=2, ensure_ascii=False) + "\n```",
        text,
    )
    text = text.replace("{{assumptions}}", assumptions_table())
    text = text.replace("{{generated_on}}", "see git history")
    return text


if __name__ == "__main__":
    OUT.write_text(render(), encoding="utf-8")
    print("wrote", OUT, dt.date.today())
