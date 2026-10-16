"""MOCK optimizer (stands in for Member 3's module).

Newsvendor target quantile per product, then greedy allocation by expected
profit per currency spent. Simplifications (ASSUMPTIONS): storage and expiry
constraints are ignored; no salvage value; lead time not modelled.
"""

from __future__ import annotations

import math

from marketpulse import config
from marketpulse.contracts.errors import ModuleFailure
from marketpulse.contracts.models import (
    BudgetPoint,
    CanonicalData,
    ForecastOutput,
    OptimizerConstraints,
    OptimizerPlan,
    PlanLine,
    ProductForecast,
    Risk,
)

_GRID = [(i + 0.5) / 100 for i in range(100)]  # integration grid over demand quantiles


def _supply_stats(fc: ProductForecast, supply: float) -> tuple[float, float]:
    qs = [fc.quantile(p) for p in _GRID]
    sales = sum(min(q, supply) for q in qs) / len(qs)
    stockout = sum(1 for q in qs if q > supply) / len(qs)
    return sales, stockout


def _uncertainty(fc: ProductForecast) -> str:
    if fc.mean <= 0:
        return "high"
    spread = (fc.quantile(0.9) - fc.quantile(0.1)) / fc.mean
    return "low" if spread < 0.5 else "medium" if spread < 1.0 else "high"


class MockOptimizer:
    def optimize(
        self,
        forecast: ForecastOutput,
        data: CanonicalData,
        budget: float,
        constraints: OptimizerConstraints | None = None,
    ) -> OptimizerPlan:
        if budget < 0:
            raise ModuleFailure("optimizer", "INVALID_BUDGET", "budget must be >= 0")
        prods = {p.product_id: p for p in data.products}
        fcs = {f.product_id: f for f in forecast.forecasts}
        if set(prods) != set(fcs):
            raise ModuleFailure("optimizer", "PRODUCT_MISMATCH", "forecast/data products differ")

        def build(b: float) -> list[PlanLine]:
            cands = []
            for pid, p in prods.items():
                fc = fcs[pid]
                cr = (p.unit_price - p.unit_cost) / p.unit_price if p.unit_price > 0 else 0.0
                cr = min(max(cr, 0.05), 0.95)
                held = p.current_stock + p.on_order
                need = max(0.0, fc.quantile(cr) - held)
                qty = math.ceil(need)
                if 0 < qty < p.min_order_qty:
                    qty = p.min_order_qty
                cands.append((pid, p, fc, cr, held, qty))

            def profit(p, fc, held, qty):
                s1, _ = _supply_stats(fc, held + qty)
                s0, _ = _supply_stats(fc, held)
                return p.unit_price * (s1 - s0) - p.unit_cost * qty

            ranked = sorted(
                cands,
                key=lambda c: -(profit(c[1], c[2], c[4], c[5]) / (c[5] * c[1].unit_cost))
                if c[5] * c[1].unit_cost > 0 else 0,
            )
            remaining, lines = b, []
            for pid, p, fc, cr, held, qty in ranked:
                reasons = []
                unc = _uncertainty(fc)
                full_qty = qty
                if qty > 0 and qty * p.unit_cost > remaining + 1e-9:
                    qty = math.floor(remaining / p.unit_cost) if p.unit_cost > 0 else 0
                    if qty < p.min_order_qty:
                        qty = 0
                        reasons.append("NOT_AFFORDABLE")
                    else:
                        reasons.append("BUDGET_BINDING")
                if qty == 0 and full_qty == 0:
                    reasons.append("ALREADY_STOCKED")
                if qty > 0 and qty == p.min_order_qty:
                    reasons.append("MIN_ORDER_QTY_APPLIED")
                if cr < 0.25:
                    reasons.append("LOW_MARGIN")
                if unc == "high" and qty > 0:
                    reasons.append("HIGH_UNCERTAINTY_REDUCED_QTY")
                if fc.low_data:
                    reasons.append("LOW_DATA_CAUTION")
                if qty > 0 and not reasons:
                    reasons.append("HIGH_PROFIT_PER_CURRENCY")
                line_cost = round(qty * p.unit_cost, 2)
                remaining = round(remaining - line_cost, 2)
                sales, so = _supply_stats(fc, held + qty)
                lines.append(
                    PlanLine(
                        product_id=pid, order_qty=qty, unit_cost=p.unit_cost,
                        line_cost=line_cost, expected_demand=fc.mean, target_quantile=round(cr, 4),
                        expected_sales_units=round(sales, 2),
                        expected_profit=round(profit(p, fc, held, qty), 2),
                        stockout_probability=round(so, 4), uncertainty=unc,
                        reason_codes=reasons,
                    )
                )
            return sorted(lines, key=lambda ln: ln.product_id)

        lines = build(budget)
        total = round(sum(ln.line_cost for ln in lines), 2)
        profit_total = round(sum(ln.expected_profit for ln in lines), 2)
        binding = ["budget"] if any("BUDGET_BINDING" in ln.reason_codes for ln in lines) else []
        risks = [
            Risk(code="HIGH_UNCERTAINTY", product_id=ln.product_id, severity="high",
                 description=f"Demand for {ln.product_id} is highly uncertain.")
            for ln in lines if ln.uncertainty == "high" and ln.order_qty > 0
        ]
        sens = []
        for k in (0.6, 1.0, 1.4):
            bl = build(round(budget * k, 2))
            sens.append(BudgetPoint(
                budget=round(budget * k, 2),
                total_cost=round(sum(x.line_cost for x in bl), 2),
                expected_total_profit=round(sum(x.expected_profit for x in bl), 2),
            ))
        return OptimizerPlan(
            as_of=forecast.as_of, horizon_days=forecast.horizon_days, currency=data.currency,
            budget=budget, total_cost=total,
            capital_utilization=round(total / budget, 4) if budget > 0 else 0.0,
            expected_total_profit=profit_total, lines=lines,
            binding_constraints=binding, risks=risks, budget_sensitivity=sens,
        )


_ = config  # config imported for assumption visibility in code search
