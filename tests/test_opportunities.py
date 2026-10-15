"""Component D tests: labeling, wide intervals, honest evidence use, trial orders from the optimizer."""

import datetime as dt
import math

import pytest

from marketpulse import config
from marketpulse.contracts.errors import ModuleFailure
from marketpulse.contracts.models import (
    CanonicalData,
    CatalogueItem,
    Opportunity,
    RequestStats,
    SalesRecord,
    Signal,
    SignalOutput,
)
from marketpulse.contracts.validate import ContractViolation, validate_payload
from marketpulse.mocks.catalogue import sample_catalogue
from marketpulse.mocks.fixtures import make_canonical_data
from marketpulse.mocks.optimizer import MockOptimizer
from marketpulse.mocks.signals import MockSignalProvider
from marketpulse.opportunities.discovery import DiscoveryEngine


@pytest.fixture(scope="module")
def data():
    return make_canonical_data()


@pytest.fixture(scope="module")
def signals(data):
    return MockSignalProvider().get_signals(data, data.as_of)


@pytest.fixture(scope="module")
def out(data, signals):
    return DiscoveryEngine(MockOptimizer()).discover(data, sample_catalogue(), signals, 5000, 14)


def by_name(out):
    return {o.name: o for o in out.opportunities}


def item(item_id="X1", name="Widget", category="grocery", cost=30, price=45, moq=10, sellers=5,
         requests=None, available=True):
    return CatalogueItem(item_id=item_id, name=name, category=category, unit_cost=cost,
                         unit_price=price, supplier_min_order_qty=moq, sellers_count=sellers,
                         requests=requests, supplier_available=available, source="test")


def run(data, catalogue, signals=None, budget=5000, horizon=14, trial=True, optimizer=None):
    eng = DiscoveryEngine(optimizer or MockOptimizer())
    return eng.discover(data, catalogue, signals, budget, horizon, include_trial_orders=trial)


# --------------------------------------------------------------- labeling (task-file test)
def test_every_opportunity_is_labeled_and_none_is_a_forecast(out):
    assert out.opportunities
    for o in out.opportunities:
        assert o.demand_basis in ("observed", "hypothesized")
        assert o.is_forecast is False
        assert o.demand.low <= o.demand.mid <= o.demand.high
    dumped = out.model_dump(mode="json")
    assert all(x["is_forecast"] is False for x in dumped["opportunities"])


def test_output_validates_against_contract(out):
    validate_payload("OpportunityOutput", out)


def test_contract_rejects_is_forecast_true(out):
    bad = out.model_dump(mode="json")
    bad["opportunities"][0]["is_forecast"] = True
    with pytest.raises(ContractViolation):
        validate_payload("OpportunityOutput", bad)


def test_contract_rejects_unlabeled_opportunity(out):
    bad = out.model_dump(mode="json")
    del bad["opportunities"][0]["demand_basis"]
    with pytest.raises(ContractViolation):
        validate_payload("OpportunityOutput", bad)


def test_contract_rejects_narrow_hypothesized_range(out):
    bad = out.model_dump(mode="json")
    o = next(x for x in bad["opportunities"] if x["demand_basis"] == "hypothesized")
    o["demand"]["low"] = o["demand"]["mid"]
    o["demand"]["high"] = o["demand"]["mid"]
    with pytest.raises(ContractViolation):
        validate_payload("OpportunityOutput", bad)


def test_contract_rejects_hypothesized_without_comparables(out):
    bad = out.model_dump(mode="json")
    o = next(x for x in bad["opportunities"] if x["demand_basis"] == "hypothesized")
    o["comparables"] = []
    with pytest.raises(ContractViolation):
        validate_payload("OpportunityOutput", bad)


def test_contract_rejects_hypothesized_that_claims_observed_requests(out):
    bad = out.model_dump(mode="json")
    o = next(x for x in bad["opportunities"] if x["demand_basis"] == "hypothesized")
    o["observed_requests"] = {"count": 5, "window_days": 28, "source": "x"}
    with pytest.raises(ContractViolation):
        validate_payload("OpportunityOutput", bad)


def test_contract_rejects_observed_without_evidence(out):
    bad = out.model_dump(mode="json")
    o = next(x for x in bad["opportunities"] if x["demand_basis"] == "observed")
    o["observed_requests"] = None
    o["evidence"] = []
    with pytest.raises(ContractViolation):
        validate_payload("OpportunityOutput", bad)


def test_trial_fields_must_come_together(out):
    bad = out.model_dump(mode="json")
    bad["opportunities"][0]["trial_cost"] = None
    bad["opportunities"][0]["trial_order_qty"] = 5
    with pytest.raises(ContractViolation):
        validate_payload("OpportunityOutput", bad)


# ------------------------------------------------------- hypothesized: wide, from comparables
def test_hypothesized_ranges_are_wide_and_use_comparables(out):
    hyp = [o for o in out.opportunities if o.demand_basis == "hypothesized"]
    assert len(hyp) >= 3
    for o in hyp:
        assert o.demand.high / o.demand.low >= config.HYPOTHESIZED_MIN_INTERVAL_RATIO
        assert o.comparables and "comparable" in o.sources
        assert o.observed_requests is None
        assert "not a forecast" in o.basis_description.lower()
        assert o.scores.uncertainty > 0.8  # visibly uncertain


def test_hypothesized_mid_is_discounted_similarity_weighted_comparable_mean(data):
    it = item(category="grocery", price=60)
    o = run(data, [it], trial=False).opportunities[0]
    assert o.demand_basis == "hypothesized"
    w = sum(c.similarity for c in o.comparables)
    base = sum(c.similarity * c.observed_units_per_horizon for c in o.comparables) / w
    assert o.demand.mid == pytest.approx(base * config.NEW_PRODUCT_DISCOUNT, abs=0.02)


def test_few_comparables_widens_the_interval(data):
    many = run(data, [item("A", "A", "grocery", 20, 30)], trial=False).opportunities[0]
    few = run(data, [item("B", "B", "electronics", 70, 120)], trial=False).opportunities[0]
    assert len(many.comparables) >= config.FEW_COMPARABLES_COUNT
    assert "FEW_COMPARABLES" not in many.notes
    assert len(few.comparables) < config.FEW_COMPARABLES_COUNT and "FEW_COMPARABLES" in few.notes
    plain = config.HYPOTHESIZED_HIGH_FACTOR / config.HYPOTHESIZED_LOW_FACTOR
    widened = plain * config.FEW_COMPARABLES_HIGH_MULT / config.FEW_COMPARABLES_LOW_MULT
    assert many.demand.high / many.demand.low == pytest.approx(plain, rel=0.02)
    assert few.demand.high / few.demand.low == pytest.approx(widened, rel=0.02)


def test_comparables_only_use_data_up_to_as_of(data):
    # A sales row dated after as_of can't exist in valid data; a shorter as_of must change the numbers
    earlier = data.model_copy(update={"as_of": data.as_of - dt.timedelta(days=30)})
    earlier = earlier.model_copy(update={"sales": [s for s in data.sales if s.date <= earlier.as_of]})
    it = item(category="grocery", price=60)
    a = run(data, [it], trial=False).opportunities[0]
    b = run(earlier, [it], trial=False).opportunities[0]
    assert a.comparables != b.comparables or a.demand != b.demand


def test_future_sales_cannot_be_smuggled_in(data):
    bad = data.model_dump(mode="json")
    bad["sales"][0]["date"] = (data.as_of + dt.timedelta(days=3)).isoformat()
    with pytest.raises(ContractViolation):
        validate_payload("CanonicalData", bad)


# --------------------------------------------------------------- observed: requests only
def test_observed_comes_from_requests_with_poisson_interval(data):
    it = item(requests=RequestStats(count=14, window_days=28, source="notebook"))
    o = run(data, [it], trial=False).opportunities[0]
    assert o.demand_basis == "observed" and "customer_requests" in o.sources
    assert o.comparables == [] and o.observed_requests.count == 14
    scale = 14 / 28
    half = config.REQUEST_INTERVAL_Z * math.sqrt(14)
    assert o.demand.mid == pytest.approx(14 * scale, abs=0.01)
    assert o.demand.low == pytest.approx((14 - half) * scale, abs=0.01)
    assert o.demand.high == pytest.approx((14 + half) * scale, abs=0.01)
    assert "lower bound" in o.evidence[0].summary


def test_few_requests_get_flag_and_wide_interval(data):
    it = item(requests=RequestStats(count=3, window_days=28, source="notebook"))
    o = run(data, [it], trial=False).opportunities[0]
    assert "LOW_REQUEST_COUNT" in o.notes and o.demand.low == 0.0 and o.scores.uncertainty == 1.0


def test_zero_requests_means_hypothesized_not_observed(data):
    it = item(requests=RequestStats(count=0, window_days=28, source="notebook"))
    assert run(data, [it], trial=False).opportunities[0].demand_basis == "hypothesized"


# ------------------------------------------------------------------ signals
def _sig(established, magnitude=0.3, category="grocery"):
    return SignalOutput(generated_at=dt.date(2026, 10, 12), signals=[Signal(
        signal_id="S-X", type="category_growth", category=category, direction="up",
        magnitude=magnitude, confidence=0.9, predictive_value_established=established, observed=True)])


def test_unvalidated_signals_change_no_number(data):
    it = item(category="grocery", price=60)
    base = run(data, [it], None, trial=False).opportunities[0]
    withsig = run(data, [it], _sig(False, 0.9), trial=False).opportunities[0]
    assert withsig.demand == base.demand and withsig.scores == base.scores
    assert "SIGNALS_NOT_VALIDATED" in withsig.notes and withsig.signal_ids == ["S-X"]
    assert "category_growth" in withsig.sources  # it still explains where the candidate came from


def test_established_signal_tilts_mid_within_cap(data):
    it = item(category="grocery", price=60)
    base = run(data, [it], None, trial=False).opportunities[0]
    tilted = run(data, [it], _sig(True, 0.3), trial=False).opportunities[0]
    assert tilted.demand.mid == pytest.approx(base.demand.mid * 1.3, rel=0.01)
    capped = run(data, [it], _sig(True, 5.0), trial=False).opportunities[0]
    cap = 1 + config.SIGNAL_TILT_CAP
    assert capped.demand.mid == pytest.approx(base.demand.mid * cap, rel=0.01)
    assert "SIGNALS_NOT_VALIDATED" not in tilted.notes


def test_down_signal_does_not_raise_demand(data):
    s = _sig(True, 0.3)
    s.signals[0].direction = "down"
    it = item(category="grocery", price=60)
    base = run(data, [it], None, trial=False).opportunities[0]
    assert run(data, [it], s, trial=False).opportunities[0].demand == base.demand


# ------------------------------------------------------------------ exclusions
def test_exclusions_are_reported_with_reasons(out):
    reasons = {e.name: e.reason for e in out.excluded}
    assert reasons["Rice 5kg"] == "ALREADY_STOCKED"
    assert reasons["Desk lamp"] == "SUPPLIER_UNAVAILABLE"
    assert reasons["School bag"] == "NO_COMPARABLES"
    assert not {e.name for e in out.excluded} & {o.name for o in out.opportunities}


def test_item_with_no_comparable_sales_is_excluded_not_invented(data):
    quiet = data.model_copy(update={"sales": [
        s.model_copy(update={"units_sold": 0}) if s.product_id == "P001" else s for s in data.sales]})
    # P001 (rice) is the only comparable at this price and sold nothing
    out = run(quiet, [item("Z", "Pricey", "electronics", 70, 120)], trial=False)
    assert out.opportunities == [] and out.excluded[0].reason == "COMPARABLES_NO_SALES"


def test_product_with_short_history_is_not_a_comparable(data):
    short = [s for s in data.sales if s.product_id != "P001"] + [
        s for s in data.sales if s.product_id == "P001"][-5:]
    d2 = data.model_copy(update={"sales": short})
    out = run(d2, [item("Z", "Pricey", "electronics", 70, 120)], trial=False)
    assert out.opportunities == [] and out.excluded[0].reason == "NO_COMPARABLES"


def test_same_name_different_case_counts_as_already_stocked(data):
    out = run(data, [item("N1", "  rice 5KG ")], trial=False)
    assert out.excluded[0].reason == "ALREADY_STOCKED"


# ------------------------------------------------------------------ scores
def test_scores_follow_documented_formulas(data):
    req = RequestStats(count=14, window_days=28, source="s")
    it = item(cost=30, price=45, moq=12, sellers=6, requests=req)
    o = run(data, [it], trial=False, budget=5000).opportunities[0]
    s = o.scores
    assert s.competition == pytest.approx(6 / config.SELLERS_SATURATION)
    assert s.profitability == pytest.approx(min(1, ((45 - 30) / 45) / config.TARGET_MARGIN), abs=1e-3)
    assert s.capital_requirement == pytest.approx(12 * 30 / 5000, abs=1e-3)
    width = (o.demand.high - o.demand.low) / (o.demand.high + o.demand.low)
    assert s.uncertainty == pytest.approx(width, abs=2e-3)
    for v in s.model_dump().values():
        assert 0 <= v <= 1


def test_unknown_competition_is_flagged_not_silently_guessed(data):
    o = run(data, [item(sellers=None)], trial=False).opportunities[0]
    assert o.scores.competition == config.UNKNOWN_COMPETITION_SCORE and "COMPETITION_UNKNOWN" in o.notes


def test_capital_requirement_grows_as_budget_shrinks(data):
    big = run(data, [item()], trial=False, budget=50000).opportunities[0].scores.capital_requirement
    small = run(data, [item()], trial=False, budget=1000).opportunities[0].scores.capital_requirement
    assert small > big


def test_negative_margin_item_scores_zero_profitability(data):
    o = run(data, [item(cost=60, price=45)], trial=False).opportunities[0]
    assert o.scores.profitability == 0.0


# ------------------------------------------------------------- trial orders (optimizer)
def test_trial_order_numbers_are_the_optimizers_exactly(data, signals):
    seen = {}

    class Spy(MockOptimizer):
        def optimize(self, forecast, d, budget, constraints=None):
            plan = super().optimize(forecast, d, budget, constraints)
            seen[plan.lines[0].product_id] = (plan, budget)
            return plan

    out = run(data, sample_catalogue(), signals, optimizer=Spy())
    assert out.trial_orders_available
    for o in out.opportunities:
        plan, budget = seen[o.opportunity_id]
        assert o.trial_order_qty == plan.lines[0].order_qty
        assert o.trial_cost == plan.lines[0].line_cost
        assert o.trial_cost <= budget == out.trial_budget


def test_trial_budget_is_a_small_fraction_of_budget(out):
    assert out.trial_budget == pytest.approx(out.budget * config.TRIAL_BUDGET_FRACTION)
    assert all((o.trial_cost or 0) <= out.trial_budget for o in out.opportunities)


def test_min_order_above_trial_budget_gives_zero_and_a_note(out):
    choc = by_name(out)["Premium chocolate bar"]
    assert choc.trial_order_qty == 0 and "MIN_ORDER_EXCEEDS_TRIAL_BUDGET" in choc.notes


def test_min_order_above_demand_range_is_flagged(out):
    bis = by_name(out)["Biscuits pack"]
    assert bis.trial_order_qty > bis.demand.high and "MIN_ORDER_ABOVE_DEMAND_RANGE" in bis.notes


def test_dead_optimizer_still_gives_opportunities_without_trials(data, signals):
    class Dead(MockOptimizer):
        def optimize(self, *a, **k):
            raise ModuleFailure("optimizer", "DOWN", "down")

    out = run(data, sample_catalogue(), signals, optimizer=Dead())
    assert out.opportunities and out.trial_orders_available is False
    assert all(o.trial_order_qty is None and o.trial_cost is None for o in out.opportunities)
    validate_payload("OpportunityOutput", out)


def test_optimizer_returning_garbage_is_not_trusted(data, signals):
    class Liar(MockOptimizer):
        def optimize(self, forecast, d, budget, constraints=None):
            plan = super().optimize(forecast, d, budget, constraints)
            return plan.model_copy(update={"total_cost": plan.budget + 1})  # violates the contract

    out = run(data, sample_catalogue(), signals, optimizer=Liar())
    assert out.trial_orders_available is False
    assert all(o.trial_order_qty is None for o in out.opportunities)


def test_trials_can_be_skipped(data):
    out = run(data, sample_catalogue(), None, trial=False)
    assert out.trial_orders_available is False
    assert all(o.trial_order_qty is None for o in out.opportunities)


# ----------------------------------------------------------- misc robustness
def test_deterministic(data, signals):
    a = run(data, sample_catalogue(), signals).model_dump(mode="json")
    b = run(data, sample_catalogue(), signals).model_dump(mode="json")
    assert a == b


def test_ranking_is_demand_potential_times_profitability(out):
    keys = [o.scores.demand_potential * o.scores.profitability for o in out.opportunities]
    assert keys == sorted(keys, reverse=True)


def test_empty_catalogue_gives_empty_output(data):
    out = run(data, [])
    assert out.opportunities == [] and out.excluded == [] and out.trial_orders_available is False


@pytest.mark.parametrize("budget,horizon", [(0, 14), (-1, 14), (5000, 5)])
def test_invalid_inputs_raise_module_failure(data, budget, horizon):
    with pytest.raises(ModuleFailure):
        run(data, sample_catalogue(), budget=budget, horizon=horizon)


def test_inputs_are_not_mutated(data, signals):
    cat = sample_catalogue()
    before = ([c.model_dump() for c in cat], data.model_dump(), signals.model_dump())
    run(data, cat, signals)
    assert before == ([c.model_dump() for c in cat], data.model_dump(), signals.model_dump())


def test_catalogue_item_contract_rejects_bad_rows():
    with pytest.raises(ContractViolation):
        validate_payload("CatalogueItem", {"item_id": "x", "name": "y", "unit_cost": -1,
                                           "unit_price": 1, "source": "s"})
    with pytest.raises(ContractViolation):
        validate_payload("CatalogueItem", {"item_id": "x", "name": "y", "unit_cost": 1,
                                           "unit_price": 1})  # source missing


def test_opportunity_model_direct_construction_enforces_rules():
    with pytest.raises(ValueError):
        Opportunity.model_validate({
            "opportunity_id": "o", "name": "n", "demand_basis": "hypothesized",
            "demand": {"low": 5, "mid": 6, "high": 7, "horizon_days": 14},
            "basis_description": "x", "scores": dict(demand_potential=.1, competition=.1,
            profitability=.1, capital_requirement=.1, uncertainty=.1),
            "unit_cost": 1, "unit_price": 2, "supplier_min_order_qty": 1,
            "comparables": [{"product_id": "p", "name": "p", "similarity": .5,
                             "observed_units_per_horizon": 10}]})


def test_a_dataset_without_enough_history_flags_unknown_demand_potential(data):
    short = CanonicalData(
        shop_id="s", currency="INR", as_of=data.as_of, products=data.products[:1],
        sales=[SalesRecord(date=data.as_of, product_id="P001", units_sold=3)])
    it = item(requests=RequestStats(count=10, window_days=28, source="s"))
    o = run(short, [it], trial=False).opportunities[0]
    assert "DEMAND_POTENTIAL_UNKNOWN" in o.notes and o.scores.demand_potential == 0.5
