"""Component D: Opportunity Discovery.

Finds products the retailer does NOT stock and says how much demand there might be, always
labelled either:

  observed      the retailer's own data shows people asking for this exact item
                (logged customer requests). Reported as a range with a Poisson interval.
  hypothesized  never sold here; estimated from comparable products the shop does sell, with an
                explicitly WIDE range (see config.HYPOTHESIZED_*).

Nothing produced here is a forecast (``is_forecast`` is always False).

Core principle: this module estimates; it never asks an LLM for a number. A trial order is sized by
the OPTIMIZER (Member 3) under a small trial budget; this module only copies the optimizer's
``order_qty`` and ``line_cost``.

All hand-set constants live in ``marketpulse/config.py`` and are labelled ASSUMPTION.
Time rule: only sales dated <= data.as_of are read (no leakage).
"""

from __future__ import annotations

import datetime as dt
import math
from collections import defaultdict

from marketpulse import config
from marketpulse.contracts.errors import ModuleFailure
from marketpulse.contracts.interfaces import Optimizer
from marketpulse.contracts.models import (
    CanonicalData,
    CatalogueItem,
    Comparable,
    DemandRange,
    Evidence,
    ExcludedCandidate,
    ForecastOutput,
    Opportunity,
    OpportunityNote,
    OpportunityOutput,
    OpportunityScores,
    OpportunitySource,
    Product,
    ProductForecast,
    QuantilePoint,
    Signal,
    SignalOutput,
)
from marketpulse.contracts.validate import validate_payload


def _norm(text: str | None) -> str:
    return " ".join((text or "").casefold().split())


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _r(x: float, nd: int = 2) -> float:
    return round(x, nd)


class DiscoveryEngine:
    """``optimizer`` is used only to size trial orders; pass None to skip them."""

    def __init__(self, optimizer: Optimizer | None = None):
        self.optimizer = optimizer

    # ------------------------------------------------------------------ public
    def discover(
        self,
        data: CanonicalData,
        catalogue: list[CatalogueItem],
        signals: SignalOutput | None,
        budget: float,
        horizon_days: int,
        include_trial_orders: bool = True,
    ) -> OpportunityOutput:
        if horizon_days not in config.HORIZONS_DAYS:
            raise ModuleFailure(
                "opportunities", "INVALID_HORIZON", f"horizon must be in {config.HORIZONS_DAYS}")
        if budget <= 0:
            raise ModuleFailure("opportunities", "INVALID_BUDGET", "budget must be > 0")

        units = self._observed_units(data, horizon_days)  # product_id -> units in the last horizon
        stocked_ids = {p.product_id for p in data.products}
        stocked_names = {_norm(p.name) for p in data.products}
        trial_budget = _r(budget * config.TRIAL_BUDGET_FRACTION)

        opps: list[Opportunity] = []
        excluded: list[ExcludedCandidate] = []
        for item in sorted(catalogue, key=lambda c: c.item_id):
            reason = None
            if item.item_id in stocked_ids or _norm(item.name) in stocked_names:
                reason = "ALREADY_STOCKED"
            elif not item.supplier_available:
                reason = "SUPPLIER_UNAVAILABLE"
            if reason:
                excluded.append(ExcludedCandidate(item_id=item.item_id, name=item.name, reason=reason))
                continue
            built = self._assess(item, data, units, signals, budget, horizon_days)
            if isinstance(built, str):
                excluded.append(ExcludedCandidate(item_id=item.item_id, name=item.name, reason=built))
            else:
                opps.append(built)

        trial_ok = False
        if include_trial_orders and self.optimizer is not None and opps:
            trial_ok = self._attach_trials(opps, data, trial_budget, horizon_days)

        # Ranking is deliberately simple and transparent (no hidden composite weights):
        # strongest demand-potential x profitability first, then least uncertain.
        opps.sort(key=lambda o: (-(o.scores.demand_potential * o.scores.profitability),
                                 o.scores.uncertainty, o.opportunity_id))
        return OpportunityOutput(
            as_of=data.as_of, horizon_days=horizon_days, currency=data.currency, budget=budget,
            trial_budget=trial_budget, trial_orders_available=trial_ok,
            opportunities=opps, excluded=excluded)

    # --------------------------------------------------------------- own sales
    @staticmethod
    def _observed_units(data: CanonicalData, horizon: int) -> dict[str, float]:
        """Units sold in the last ``horizon`` days up to as_of, for products with >= horizon days
        of history. Products with less history are not used (no scaling tricks).
        A day with no row counts as zero sales (CONTRACT.md open question Q-C)."""
        start = data.as_of - dt.timedelta(days=horizon - 1)
        days: dict[str, set[dt.date]] = defaultdict(set)
        total: dict[str, float] = defaultdict(float)
        for s in data.sales:
            if s.date > data.as_of:  # defensive: contract already forbids this
                continue
            days[s.product_id].add(s.date)
            if s.date >= start:
                total[s.product_id] += s.units_sold
        return {pid: total[pid] for pid in days if len(days[pid]) >= horizon}

    # ---------------------------------------------------------------- one item
    def _assess(self, item: CatalogueItem, data: CanonicalData, units: dict[str, float],
                signals: SignalOutput | None, budget: float, horizon: int) -> Opportunity | str:
        sources: list[OpportunitySource] = ["catalogue_gap"]
        notes: list[OpportunityNote] = []
        matched = self._match_signals(item, signals)
        for s in matched:
            if s.direction == "up":
                if s.type == "unmet_demand" and "unmet_demand" not in sources:
                    sources.append("unmet_demand")
                if s.type == "category_growth" and "category_growth" not in sources:
                    sources.append("category_growth")
        if matched and not any(s.predictive_value_established for s in matched):
            notes.append("SIGNALS_NOT_VALIDATED")

        comparables: list[Comparable] = []
        evidence: list[Evidence] = []
        observed_requests = None
        req = item.requests

        if req is not None and req.count > 0:
            basis, observed_requests = "observed", req
            sources.append("customer_requests")
            scale = horizon / req.window_days
            n = req.count
            half = config.REQUEST_INTERVAL_Z * math.sqrt(n)
            mid = n * scale * config.UNITS_PER_REQUEST
            low = max(0.0, n - half) * scale * config.UNITS_PER_REQUEST
            high = (n + half) * scale * config.UNITS_PER_REQUEST
            if n < config.LOW_REQUEST_COUNT:
                notes.append("LOW_REQUEST_COUNT")
            evidence.append(Evidence(source=req.source, summary=(
                f"{n} customer request(s) logged over {req.window_days} days "
                "(a lower bound: most customers never ask)")))
            how = (f"Observed: {n} customer request(s) in {req.window_days} days, scaled to "
                   f"{horizon} days with a 95% Poisson interval. A lower bound, not a forecast.")
        else:
            basis = "hypothesized"
            comparables = self._comparables(item, data, units)
            if not comparables:
                return "NO_COMPARABLES"
            wsum = sum(c.similarity for c in comparables)
            base = sum(c.similarity * c.observed_units_per_horizon for c in comparables) / wsum
            mid = base * config.NEW_PRODUCT_DISCOUNT
            if mid <= 0:
                return "COMPARABLES_NO_SALES"
            tilt = [min(s.magnitude, config.SIGNAL_TILT_CAP) for s in matched
                    if s.predictive_value_established and s.direction == "up"
                    and s.magnitude is not None and s.magnitude > 0]
            if tilt:  # only signals with ESTABLISHED predictive value may move a number
                mid *= 1.0 + max(tilt)
            lo_f, hi_f = config.HYPOTHESIZED_LOW_FACTOR, config.HYPOTHESIZED_HIGH_FACTOR
            if len(comparables) < config.FEW_COMPARABLES_COUNT:
                notes.append("FEW_COMPARABLES")
                lo_f *= config.FEW_COMPARABLES_LOW_MULT
                hi_f *= config.FEW_COMPARABLES_HIGH_MULT
            low, high = mid * lo_f, mid * hi_f
            sources.append("comparable")
            how = (f"Hypothesized: this item has never been sold here. Estimated from "
                   f"{len(comparables)} comparable product(s) you sell, discounted for being new, "
                   f"with a deliberately wide range. Not a forecast.")

        mid_r, low_r, high_r = _r(mid), _r(low), _r(high)
        demand = DemandRange(low=min(low_r, mid_r), mid=mid_r, high=max(high_r, mid_r),
                             horizon_days=horizon)

        # ---- scores (all documented in config.py; each is 0..1)
        qualified = sorted(units.values())
        median = 0.0
        if qualified:
            k = len(qualified)
            median = qualified[k // 2] if k % 2 else (qualified[k // 2 - 1] + qualified[k // 2]) / 2
        if median > 0:
            dp = _clamp01(demand.mid / median)  # relative to the shop's typical current product
        else:
            dp = 0.5
            notes.append("DEMAND_POTENTIAL_UNKNOWN")
        if item.sellers_count is None:
            comp = config.UNKNOWN_COMPETITION_SCORE
            notes.append("COMPETITION_UNKNOWN")
        else:
            comp = _clamp01(item.sellers_count / config.SELLERS_SATURATION)
        margin = (item.unit_price - item.unit_cost) / item.unit_price if item.unit_price > 0 else 0.0
        prof = _clamp01(margin / config.TARGET_MARGIN)
        cap = _clamp01(item.supplier_min_order_qty * item.unit_cost / budget)
        denom = demand.high + demand.low
        unc = _clamp01((demand.high - demand.low) / denom) if denom > 0 else 1.0
        scores = OpportunityScores(
            demand_potential=_r(dp, 4), competition=_r(comp, 4), profitability=_r(prof, 4),
            capital_requirement=_r(cap, 4), uncertainty=_r(unc, 4))

        return Opportunity(
            opportunity_id="opp-" + item.item_id, name=item.name, category=item.category,
            demand_basis=basis, demand=demand, basis_description=how, sources=sources,
            comparables=comparables, signal_ids=[s.signal_id for s in matched], evidence=evidence,
            observed_requests=observed_requests, scores=scores, unit_cost=item.unit_cost,
            unit_price=item.unit_price, supplier_min_order_qty=item.supplier_min_order_qty,
            notes=notes)

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def _match_signals(item: CatalogueItem, signals: SignalOutput | None) -> list[Signal]:
        if signals is None:
            return []
        cat = _norm(item.category)
        out = []
        for s in signals.signals:
            if s.product_id == item.item_id or (s.category and cat and _norm(s.category) == cat):
                out.append(s)
        return out

    @staticmethod
    def _comparables(item: CatalogueItem, data: CanonicalData, units: dict[str, float]) -> list[Comparable]:
        found: list[Comparable] = []
        cat = _norm(item.category)
        for p in data.products:
            if p.product_id not in units or p.unit_price <= 0 or item.unit_price <= 0:
                continue
            same = bool(cat) and _norm(p.category) == cat
            ratio = min(p.unit_price, item.unit_price) / max(p.unit_price, item.unit_price)
            sim = (1.0 if same else config.DIFFERENT_CATEGORY_FACTOR) * ratio
            if sim >= config.MIN_COMPARABLE_SIMILARITY:
                found.append(Comparable(product_id=p.product_id, name=p.name, similarity=_r(sim, 4),
                                        observed_units_per_horizon=_r(units[p.product_id])))
        found.sort(key=lambda c: (-c.similarity, c.product_id))
        return found[: config.MAX_COMPARABLES]

    # ------------------------------------------------------------ trial orders
    def _attach_trials(self, opps: list[Opportunity], data: CanonicalData, trial_budget: float,
                       horizon: int) -> bool:
        """Ask the OPTIMIZER how many units a small trial should be. We copy its answer."""
        ok = True
        for o in opps:
            try:
                plan = self.optimizer.optimize(*self._trial_inputs(o, data, horizon), trial_budget)
                validate_payload("OptimizerPlan", plan)
                line = plan.lines[0]
            except Exception:  # noqa: BLE001 - any optimizer problem: show no trial order, say so
                ok = False
                continue
            o.trial_order_qty, o.trial_cost = line.order_qty, line.line_cost
            if line.order_qty == 0 and "MIN_ORDER_EXCEEDS_TRIAL_BUDGET" not in o.notes:
                o.notes.append("MIN_ORDER_EXCEEDS_TRIAL_BUDGET")
            if line.order_qty > o.demand.high and "MIN_ORDER_ABOVE_DEMAND_RANGE" not in o.notes:
                o.notes.append("MIN_ORDER_ABOVE_DEMAND_RANGE")  # minimum > what we expect to sell
        return ok

    @staticmethod
    def _trial_inputs(
        o: Opportunity, data: CanonicalData, horizon: int
    ) -> tuple[ForecastOutput, CanonicalData]:
        """A one-product problem for the optimizer. The demand 'distribution' is the labelled range
        (piecewise-linear through p5=low, p50=mid, p95=high): an ASSUMPTION used ONLY to size a
        trial, never shown as a forecast. history_days=0 / cold_start=True say so honestly."""
        lo, mid, hi = o.demand.low, o.demand.mid, o.demand.high

        def q(p: float) -> float:
            if p <= 0.5:
                return lo + (mid - lo) * (p - 0.05) / 0.45
            return mid + (hi - mid) * (p - 0.5) / 0.45

        pid = o.opportunity_id
        fc = ForecastOutput(
            as_of=data.as_of, horizon_days=horizon, model_name="D-trial-sizing-from-range",
            forecasts=[ProductForecast(
                product_id=pid, mean=mid,
                quantiles=[QuantilePoint(p=p, value=_r(max(0.0, q(p)))) for p in config.QUANTILE_GRID],
                history_days=0, low_data=True, cold_start=True)])
        d = CanonicalData(
            shop_id=data.shop_id, currency=data.currency, as_of=data.as_of,
            products=[Product(product_id=pid, name=o.name, unit_cost=o.unit_cost,
                              unit_price=o.unit_price, current_stock=0, on_order=0,
                              min_order_qty=o.supplier_min_order_qty)],
            sales=[])
        return fc, d
