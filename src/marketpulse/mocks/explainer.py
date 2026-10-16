"""MOCK explainer (stands in for the LLM explainer).

Template text per language. EVERY number is copied from the OptimizerPlan and
listed in ``cited_figures`` with its JSON Pointer. ASCII digits, '.' decimal.
"""

from __future__ import annotations

from marketpulse.contracts.models import CitedFigure, Explanation, ForecastOutput, OptimizerPlan

_T = {
    "en": ("Spend {cost} of {budget} {cur}. Expected profit: {profit} {cur}.",
           "Order {qty} units of {pid} (cost {lc} {cur})."),
    "fr": ("Dépensez {cost} sur {budget} {cur}. Profit attendu : {profit} {cur}.",
           "Commandez {qty} unités de {pid} (coût {lc} {cur})."),
    "es": ("Gaste {cost} de {budget} {cur}. Ganancia esperada: {profit} {cur}.",
           "Pida {qty} unidades de {pid} (costo {lc} {cur})."),
    "hi": ("{budget} {cur} में से {cost} खर्च करें। अपेक्षित लाभ: {profit} {cur}।",
           "{pid} की {qty} इकाइयाँ मँगाएँ (लागत {lc} {cur})।"),
}


def _fmt(v: float) -> str:
    return f"{v:.2f}"


class MockExplainer:
    def explain(
        self,
        plan: OptimizerPlan,
        forecast: ForecastOutput,
        question: str | None = None,
        language: str = "en",
    ) -> Explanation:
        lang = language if language in _T else "en"
        head, line_t = _T[lang]
        figs = [
            CitedFigure(path="/total_cost", value=plan.total_cost),
            CitedFigure(path="/budget", value=plan.budget),
            CitedFigure(path="/expected_total_profit", value=plan.expected_total_profit),
        ]
        parts = [head.format(cost=_fmt(plan.total_cost), budget=_fmt(plan.budget),
                             profit=_fmt(plan.expected_total_profit), cur=plan.currency)]
        for i, ln in enumerate(plan.lines):
            if question and ln.product_id.lower() not in question.lower() and any(
                x.product_id.lower() in question.lower() for x in plan.lines
            ):
                continue
            if ln.order_qty == 0:
                continue
            parts.append(line_t.format(qty=ln.order_qty, pid=ln.product_id,
                                       lc=_fmt(ln.line_cost), cur=plan.currency))
            figs += [CitedFigure(path=f"/lines/{i}/order_qty", value=ln.order_qty),
                     CitedFigure(path=f"/lines/{i}/line_cost", value=ln.line_cost)]
        return Explanation(language=lang, text=" ".join(parts), cited_figures=figs)
