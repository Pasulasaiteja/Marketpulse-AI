"""Decision API tests (task file test table): happy path, budget demo, description edit demo,
failure injection, low confidence, number integrity, latency, audit, CSV, cross-language."""

import copy
import csv
import io

import pytest
from fastapi.testclient import TestClient

from marketpulse import config
from marketpulse.api.app import create_app
from marketpulse.contracts.errors import ModuleFailure
from marketpulse.contracts.models import OptimizerPlan
from marketpulse.contracts.validate import validate_payload
from marketpulse.csvloader import (
    CsvError,
    dump_catalogue_csv,
    load_canonical_data,
    load_catalogue_csv,
)
from marketpulse.mocks.catalogue import sample_catalogue
from marketpulse.mocks.fixtures import make_canonical_data
from marketpulse.registry import default_modules

DESC = "Small shop near a school in Delhi, India."


def to_csv(data):
    p, s = io.StringIO(), io.StringIO()
    pw = csv.writer(p)
    pw.writerow(["product_id", "name", "unit_cost", "unit_price", "current_stock", "on_order",
                 "lead_time_days", "min_order_qty", "category"])
    for x in data.products:
        pw.writerow([x.product_id, x.name, x.unit_cost, x.unit_price, x.current_stock, x.on_order,
                     x.lead_time_days, x.min_order_qty, x.category])
    sw = csv.writer(s)
    sw.writerow(["date", "product_id", "units_sold", "revenue", "stockout"])
    for r in data.sales:
        sw.writerow([r.date, r.product_id, r.units_sold, r.revenue, r.stockout])
    return p.getvalue(), s.getvalue()


def client(modules=None, audit_path=None):
    return TestClient(create_app(modules, audit_path))


def confirmed_profile(c, desc=DESC, edits=None, hint=None):
    r = c.post("/profile/extract", json={"description": desc, "language_hint": hint}).json()
    pid = r["profile"]["profile_id"]
    r = c.post("/profile/confirm", json={"profile_id": pid, "edits": edits or {}}).json()
    assert r["status"] == "confirmed", r
    return pid


@pytest.fixture
def data_json():
    return make_canonical_data().model_dump(mode="json")


def make_plan(c, pid, data_json=None, budget=5000, **kw):
    body = {"profile_id": pid, "budget": budget, **kw}
    if data_json is not None:
        body["data"] = data_json
    return c.post("/plan", json=body)


# ----------------------------------------------------------------------- happy path
def test_happy_path_csv_to_plan_and_explanation():
    c = client()
    pid = confirmed_profile(c)
    products_csv, sales_csv = to_csv(make_canonical_data())
    r = c.post("/plan", json={"profile_id": pid, "budget": 5000, "products_csv": products_csv,
                              "sales_csv": sales_csv})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    validate_payload("OptimizerPlan", body["plan"])
    validate_payload("ForecastOutput", body["forecast"])
    validate_payload("Explanation", body["explanation"])
    assert body["plan"]["total_cost"] <= 5000
    assert body["warnings"] == []


# ----------------------------------------------------------------------- budget demo
def test_budget_change_updates_plan_within_target_and_never_exceeds_budget(data_json):
    c = client()
    pid = confirmed_profile(c)
    a = make_plan(c, pid, data_json, 5000).json()
    b = make_plan(c, pid, budget=3000, dataset_id=a["dataset_id"]).json()
    assert a["plan"]["total_cost"] <= 5000 and b["plan"]["total_cost"] <= 3000
    assert a["plan"]["lines"] != b["plan"]["lines"]
    assert b["plan"]["budget"] == 3000
    assert b["cache"]["forecast_hit"] is True  # same shop, only the budget changed
    assert b["latency"]["within_target"]
    assert b["timings_ms"]["total"] < config.PLAN_LATENCY_WARM_SECONDS * 1000


@pytest.mark.parametrize("budget", [1, 50, 100, 1000, 2500, 3000, 5000, 20000, 1e6])
def test_cost_never_exceeds_budget_across_budgets(data_json, budget):
    c = client()
    pid = confirmed_profile(c)
    r = make_plan(c, pid, data_json, budget).json()
    assert r["plan"]["total_cost"] <= budget


# ------------------------------------------------------------ description edit demo
def test_school_to_market_changes_context_features_and_plan(data_json):
    c = client()
    school = confirmed_profile(c, "Small shop near a school in Delhi, India.")
    market = confirmed_profile(c, "Small shop near a market in Delhi, India.")
    a = make_plan(c, school, data_json).json()
    b = make_plan(c, market, data_json).json()
    assert a["forecast"]["context_features_used"] != b["forecast"]["context_features_used"]
    assert a["plan"]["lines"] != b["plan"]["lines"]
    assert b["cache"]["forecast_hit"] is False  # profile change must invalidate the cache


def test_retailer_edit_of_anchor_propagates(data_json):
    c = client()
    pid = confirmed_profile(c, "Small shop near a school in Delhi, India.",
                            edits={"nearby_anchors": ["market"]})
    r = make_plan(c, pid, data_json).json()
    assert "near_market" in r["forecast"]["context_features_used"]
    assert "near_school" not in r["forecast"]["context_features_used"]


# --------------------------------------------------------------------- low confidence
def test_missing_required_field_asks_follow_up_and_blocks_plan(data_json):
    c = client()
    r = c.post("/profile/extract", json={"description": "I sell rice and soap"}).json()
    fields = {q["field"] for q in r["follow_up_questions"]}
    assert {"country", "currency", "location_type"} <= fields
    pid = r["profile"]["profile_id"]
    blocked = make_plan(c, pid, data_json).json()
    assert blocked["status"] == "needs_confirmation" and "plan" not in blocked
    still = c.post("/profile/confirm", json={"profile_id": pid}).json()
    assert still["status"] == "needs_input" and still["follow_up_questions"]
    done = c.post("/profile/confirm", json={"profile_id": pid, "edits": {
        "country": "IN", "currency": "INR", "location_type": "urban"}}).json()
    assert done["status"] == "confirmed"
    assert make_plan(c, pid, data_json).json()["status"] == "ok"


def test_low_confidence_value_triggers_follow_up_in_retailer_language():
    mods = default_modules()
    real = mods.extractor.extract_profile

    def shaky(desc, hint=None):
        p = real(desc, hint)
        p.fields.location_type.confidence = 0.4
        return p

    mods.extractor.extract_profile = shaky
    c = client(mods)
    r = c.post("/profile/extract", json={"description": "boutique près d'une école à Delhi, India"}).json()
    q = next(q for q in r["follow_up_questions"] if q["field"] == "location_type")
    assert q["reason"] == "low_confidence"
    assert "correct" in q["question"]  # French wording from the API fallback text
    assert r["profile"]["language"] == "fr"


def test_confidence_at_threshold_does_not_ask():
    c = client()
    r = c.post("/profile/extract", json={"description": DESC}).json()
    assert r["follow_up_questions"] == []
    assert config.LOW_CONFIDENCE_THRESHOLD == 0.7


# ------------------------------------------------------------------ failure injection
class Boom:
    """Wraps a mock method so it raises."""

    def __init__(self, exc):
        self.exc = exc

    def __call__(self, *a, **k):
        raise self.exc


def broken(module, method, exc):
    mods = default_modules()
    setattr(getattr(mods, module), method, Boom(exc))
    return mods


HARD = [("extractor", "extract_profile"), ("forecaster", "forecast"), ("optimizer", "optimize")]
SOFT = [("signals", "get_signals", "SIGNALS_UNAVAILABLE"), ("context", "build_context", "CONTEXT_FALLBACK"),
        ("explainer", "explain", "EXPLANATION_UNAVAILABLE")]


@pytest.mark.parametrize("module,method", HARD)
@pytest.mark.parametrize(
    "exc", [ModuleFailure("x", "DOWN", "service down", True), RuntimeError("secret trace")]
)
def test_hard_module_failure_returns_honest_error_no_plan(data_json, module, method, exc):
    c = client(broken(module, method, exc))
    if module == "extractor":
        r = c.post("/profile/extract", json={"description": DESC})
    else:
        pid = confirmed_profile(c)  # extraction is healthy here; only `module` is broken
        r = make_plan(c, pid, data_json)
    assert r.status_code == 502
    err = r.json()["error"]
    assert err["code"] == "MODULE_FAILED"
    assert err["module_error"]["module"] == module
    assert "secret trace" not in r.text and "Traceback" not in r.text
    assert "plan" not in r.json()


@pytest.mark.parametrize("module,method,warning", SOFT)
def test_soft_module_failure_degrades_with_warning(data_json, module, method, warning):
    c = client(broken(module, method, ModuleFailure(module, "DOWN", "down")))
    pid = confirmed_profile(c)
    r = make_plan(c, pid, data_json)
    assert r.status_code == 200
    body = r.json()
    assert warning in {w["code"] for w in body["warnings"]}
    validate_payload("OptimizerPlan", body["plan"])
    if module == "explainer":
        assert body["explanation"] is None


@pytest.mark.filterwarnings("ignore::UserWarning")  # model_construct bypass is deliberate here
def test_module_returning_contract_violation_is_rejected(data_json):
    mods = default_modules()
    real = mods.optimizer.optimize

    def cheat(*a, **k):
        plan = real(*a, **k).model_dump(mode="json")
        plan["total_cost"] = plan["budget"] + 1  # over budget
        return OptimizerPlan.model_construct(**plan)  # bypass validation like a buggy module

    mods.optimizer.optimize = cheat
    c = client(mods)
    r = make_plan(c, confirmed_profile(c), data_json)
    assert r.status_code == 502
    assert r.json()["error"]["module_error"]["code"] == "CONTRACT_VIOLATION"


# ------------------------------------------------------------------- number integrity
def test_api_plan_numbers_equal_optimizer_output_exactly(data_json):
    mods = default_modules()
    captured = {}
    real = mods.optimizer.optimize

    def spy(*a, **k):
        captured["plan"] = real(*a, **k)
        return captured["plan"]

    mods.optimizer.optimize = spy
    c = client(mods)
    r = make_plan(c, confirmed_profile(c), data_json).json()
    assert r["plan"] == captured["plan"].model_dump(mode="json")


def test_ungrounded_explanation_is_withheld(data_json):
    mods = default_modules()
    real = mods.explainer.explain

    def lie(plan, forecast, question=None, language="en"):
        e = real(plan, forecast, question, language)
        return e.model_copy(update={"text": e.text + " Expected profit is 99999.00."})

    mods.explainer.explain = lie
    c = client(mods)
    pid = confirmed_profile(c)
    r = make_plan(c, pid, data_json).json()
    assert r["explanation"] is None
    assert "EXPLANATION_UNGROUNDED" in {w["code"] for w in r["warnings"]}
    ask = c.post("/ask", json={"request_id": r["request_id"], "question": "why?"})
    assert ask.status_code == 502 and "99999" not in ask.text


@pytest.mark.parametrize("lang", config.SUPPORTED_LANGUAGES)
def test_ask_in_every_language_is_grounded(data_json, lang):
    c = client()
    pid = confirmed_profile(c)
    r = make_plan(c, pid, data_json).json()
    a = c.post("/ask", json={"request_id": r["request_id"], "question": "why?", "language": lang})
    assert a.status_code == 200
    exp = a.json()["explanation"]
    assert exp["language"] == lang
    plan_total = f"{r['plan']['total_cost']:.2f}"
    assert plan_total in exp["text"]


# ----------------------------------------------------------------- cross-language (mock)
def test_same_shop_in_four_languages_gives_same_plan(data_json):
    descs = {
        "en": "Small shop near a school in Delhi, India.",
        "fr": "Petite boutique près d'une école à Delhi, India.",
        "es": "Pequeña tienda cerca de una escuela en Delhi, India.",
        "hi": "दिल्ली, भारत में स्कूल के पास छोटी दुकान।",
    }
    totals = {}
    for lang, d in descs.items():
        c = client()
        pid = confirmed_profile(c, d)
        assert c.post("/profile/extract", json={"description": d}).json()["profile"]["language"] == lang
        totals[lang] = make_plan(c, pid, data_json).json()["plan"]["lines"]
    assert all(v == totals["en"] for v in totals.values())  # NOTE: mock extractor only


# ------------------------------------------------------------------------ validation
def test_input_validation_errors(data_json):
    c = client()
    pid = confirmed_profile(c)
    assert make_plan(c, pid, data_json, budget=0).status_code == 422
    assert make_plan(c, pid, data_json, budget=-5).status_code == 422
    assert make_plan(c, pid, data_json, horizon_days=5).status_code == 422
    assert make_plan(c, pid, data_json, language="de").status_code == 422
    assert make_plan(c, "nope", data_json).status_code == 404
    assert make_plan(c, pid).status_code == 422  # no data
    assert c.post("/plan", json={"profile_id": pid, "budget": 1, "oops": 1}).status_code == 422
    assert c.post("/profile/extract", json={"description": "  "}).status_code == 422
    assert c.post("/profile/extract", json={"description": "x", "language_hint": "de"}).status_code == 422
    assert c.post("/profile/confirm", json={"profile_id": pid, "edits": {"bogus": 1}}).status_code == 422
    bad = {"profile_id": pid, "edits": {"payday_day": 99}}
    assert c.post("/profile/confirm", json=bad).status_code == 422
    assert c.post("/ask", json={"request_id": "none", "question": "why?"}).status_code == 404


# ------------------------------------------------------------------------- audit log
def test_audit_log_records_said_extracted_changed_and_steps(tmp_path, data_json):
    path = tmp_path / "audit.jsonl"
    c = client(audit_path=str(path))
    r = c.post("/profile/extract", json={"description": DESC}).json()
    pid = r["profile"]["profile_id"]
    c.post("/profile/confirm", json={"profile_id": pid, "edits": {"location_type": "peri_urban"}})
    make_plan(c, pid, data_json)
    import json
    recs = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
    by = {x["endpoint"]: x for x in recs}
    assert by["/profile/extract"]["said"] == DESC
    assert by["/profile/extract"]["extracted"]["location_type"]["value"] == "urban"
    assert by["/profile/confirm"]["changed"][0]["old_value"] == "urban"
    assert by["/profile/confirm"]["changed"][0]["new_value"] == "peri_urban"
    assert {s["module"] for s in by["/plan"]["steps"]} >= {"forecaster", "optimizer", "explainer"}
    assert all("request_id" in x and "ts" in x for x in recs)


def test_failures_are_audited(tmp_path, data_json):
    path = tmp_path / "audit.jsonl"
    mods = broken("optimizer", "optimize", ModuleFailure("optimizer", "DOWN", "down"))
    c = client(mods, str(path))
    make_plan(c, confirmed_profile(c), data_json)
    import json
    last = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
    assert last["outcome"] == "error" and last["error"]["module"] == "optimizer"


# ------------------------------------------------------------------------- latency
def test_cold_and_warm_latency_meet_targets(data_json):
    c = client()
    pid = confirmed_profile(c)
    cold = make_plan(c, pid, data_json).json()
    warm = make_plan(c, pid, data_json, budget=4000).json()
    assert cold["timings_ms"]["total"] < config.PLAN_LATENCY_COLD_SECONDS * 1000
    assert warm["timings_ms"]["total"] < config.PLAN_LATENCY_WARM_SECONDS * 1000
    assert not cold["cache"]["forecast_hit"] and warm["cache"]["forecast_hit"]


# --------------------------------------------------------------------------- CSV
def test_csv_roundtrip_matches_fixture():
    d = make_canonical_data()
    pc, sc = to_csv(d)
    loaded = load_canonical_data(pc, sc, shop_id=d.shop_id, currency=d.currency)
    assert loaded.as_of == d.as_of and len(loaded.sales) == len(d.sales)
    assert [p.unit_cost for p in loaded.products] == [p.unit_cost for p in d.products]


@pytest.mark.parametrize("mutate,needle", [
    (lambda p, s: (p.replace("unit_price", "price"), s), "missing column"),
    (lambda p, s: (p, s.replace("2026-10-12", "12/10/2026", 1)), "YYYY-MM-DD"),
    (lambda p, s: (p, s.replace(",P001,", ",NOPE,", 1)), "unknown product_id"),
    (lambda p, s: (p.replace("P001,Rice 5kg,60.0", "P001,Rice 5kg,abc", 1), s), "not a number"),
    (lambda p, s: (p, "date,product_id,units_sold\n"), "no data rows"),
])
def test_csv_errors_are_clear(mutate, needle):
    d = make_canonical_data()
    p, s = mutate(*to_csv(d))
    with pytest.raises(CsvError, match=needle):
        load_canonical_data(p, s, shop_id="x", currency="INR")


def test_csv_future_sales_rejected():
    d = make_canonical_data()
    p, s = to_csv(d)
    with pytest.raises(CsvError, match="after as_of"):
        load_canonical_data(p, s, shop_id="x", currency="INR", as_of=d.as_of.replace(day=1))


def test_state_is_not_mutated_by_planning(data_json):
    c = client()
    pid = confirmed_profile(c)
    before = copy.deepcopy(data_json)
    make_plan(c, pid, data_json)
    assert data_json == before


# ------------------------------------------------------------- additions for the UI
def test_demo_files_endpoint_is_synthetic_and_loadable():
    from marketpulse.csvloader import dump_csv

    c = client()
    d = c.get("/demo/files").json()
    assert d["synthetic"] is True and "invented" in d["note"].lower()
    loaded = load_canonical_data(d["products_csv"], d["sales_csv"], shop_id="x", currency="INR")
    ref = make_canonical_data()
    assert loaded.as_of == ref.as_of and len(loaded.sales) == len(ref.sales)
    assert dump_csv(loaded) == dump_csv(ref)  # lossless round trip


def test_plan_response_includes_product_names(data_json):
    c = client()
    r = make_plan(c, confirmed_profile(c), data_json).json()
    assert r["product_names"]["P001"] == "Rice 5kg"
    assert set(r["product_names"]) == {ln["product_id"] for ln in r["plan"]["lines"]}


def test_extract_response_lists_required_fields():
    r = client().post("/profile/extract", json={"description": DESC}).json()
    assert r["required_fields"] == list(config.REQUIRED_PROFILE_FIELDS)


def test_root_redirects_to_ui_and_ui_is_served():
    c = client()
    r = c.get("/", follow_redirects=False)
    assert r.status_code in (302, 307) and r.headers["location"] == "/ui/"
    assert "MarketPulse" in c.get("/ui/").text
    assert c.get("/ui/app.js").status_code == 200


# ------------------------------------------------------------- /opportunities (Component D)
def opp_request(c, pid, data_json=None, **kw):
    body = {"profile_id": pid, "budget": 5000, **kw}
    if data_json is not None:
        body["data"] = data_json
    return c.post("/opportunities", json=body)


def test_opportunities_happy_path_is_labeled_and_never_a_forecast(data_json):
    c = client()
    pid = confirmed_profile(c)
    r = opp_request(c, pid, data_json)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["catalogue_source"] == "sample_synthetic"
    out = validate_payload("OpportunityOutput", body["opportunities"])
    assert out.opportunities and out.trial_orders_available
    assert {o.demand_basis for o in out.opportunities} == {"observed", "hypothesized"}
    assert all(o.is_forecast is False for o in out.opportunities)
    assert body["timings_ms"]["total"] < config.PLAN_LATENCY_WARM_SECONDS * 1000


def test_opportunities_can_reuse_a_plans_dataset(data_json):
    c = client()
    pid = confirmed_profile(c)
    plan = make_plan(c, pid, data_json).json()
    r = opp_request(c, pid, dataset_id=plan["dataset_id"], horizon_days=14).json()
    assert r["dataset_id"] == plan["dataset_id"] and r["status"] == "ok"


def test_opportunities_trial_numbers_equal_optimizer_output(data_json):
    mods = default_modules()
    seen = {}
    real = mods.optimizer.optimize

    def spy(forecast, data, budget, constraints=None):
        plan = real(forecast, data, budget, constraints)
        seen[plan.lines[0].product_id] = plan
        return plan

    mods.optimizer.optimize = spy
    c = client(mods)
    body = opp_request(c, confirmed_profile(c), data_json).json()
    for o in body["opportunities"]["opportunities"]:
        line = seen[o["opportunity_id"]].lines[0]
        assert o["trial_order_qty"] == line.order_qty and o["trial_cost"] == line.line_cost


def test_opportunities_with_dead_optimizer_still_returns_ranges_with_warning(data_json):
    c = client(broken("optimizer", "optimize", ModuleFailure("optimizer", "DOWN", "down")))
    body = opp_request(c, confirmed_profile(c), data_json).json()
    assert body["status"] == "ok"
    assert body["opportunities"]["trial_orders_available"] is False
    assert "TRIAL_ORDERS_UNAVAILABLE" in {w["code"] for w in body["warnings"]}
    assert all(o["trial_order_qty"] is None for o in body["opportunities"]["opportunities"])


def test_opportunities_with_dead_signals_degrades_with_warning(data_json):
    c = client(broken("signals", "get_signals", ModuleFailure("signals", "DOWN", "down")))
    body = opp_request(c, confirmed_profile(c), data_json).json()
    assert body["status"] == "ok"
    assert "SIGNALS_UNAVAILABLE" in {w["code"] for w in body["warnings"]}
    for o in body["opportunities"]["opportunities"]:
        assert o["signal_ids"] == []


def test_opportunities_engine_failure_is_an_honest_502(data_json, monkeypatch):
    from marketpulse.opportunities.discovery import DiscoveryEngine

    def boom(self, *a, **k):
        raise RuntimeError("secret trace")

    monkeypatch.setattr(DiscoveryEngine, "discover", boom)
    c = client()
    r = opp_request(c, confirmed_profile(c), data_json)
    assert r.status_code == 502
    err = r.json()["error"]
    assert err["module_error"]["module"] == "opportunities" and "secret trace" not in r.text


def test_opportunities_with_provided_catalogue(data_json):
    c = client()
    cat = [{"item_id": "Q1", "name": "Mango juice", "category": "beverages", "unit_cost": 30,
            "unit_price": 45, "supplier_min_order_qty": 6, "sellers_count": 3, "source": "test"}]
    body = opp_request(c, confirmed_profile(c), data_json, catalogue=cat).json()
    assert body["catalogue_source"] == "provided"
    assert [o["name"] for o in body["opportunities"]["opportunities"]] == ["Mango juice"]


def test_opportunities_can_skip_trial_orders(data_json):
    c = client()
    body = opp_request(c, confirmed_profile(c), data_json, include_trial_orders=False).json()
    assert body["opportunities"]["trial_orders_available"] is False
    assert "TRIAL_ORDERS_UNAVAILABLE" not in {w["code"] for w in body["warnings"]}


def test_opportunities_input_validation(data_json):
    c = client()
    pid = confirmed_profile(c)
    assert opp_request(c, pid, data_json, budget=0).status_code == 422
    assert opp_request(c, pid, data_json, horizon_days=5).status_code == 422
    assert opp_request(c, "nope", data_json).status_code == 404
    assert opp_request(c, pid).status_code == 422  # no data source
    bad = [{"item_id": "Q", "name": "x", "unit_cost": -1, "unit_price": 1, "source": "s"}]
    assert opp_request(c, pid, data_json, catalogue=bad).status_code == 422
    assert c.post("/opportunities", json={"profile_id": pid, "budget": 5, "oops": 1}).status_code == 422


def test_opportunities_are_audited(tmp_path, data_json):
    import json

    path = tmp_path / "audit.jsonl"
    c = client(audit_path=str(path))
    opp_request(c, confirmed_profile(c), data_json)
    last = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
    assert last["endpoint"] == "/opportunities" and last["outcome"] == "ok"
    assert last["catalogue_source"] == "sample_synthetic" and last["n_opportunities"] >= 1
    assert {s["module"] for s in last["steps"]} >= {"signals", "opportunities"}


def test_demo_catalogue_is_synthetic_and_valid():
    d = client().get("/demo/catalogue").json()
    assert d["synthetic"] is True and len(d["items"]) >= 8
    for it in d["items"]:
        validate_payload("CatalogueItem", it)
        assert "SYNTHETIC" in it["source"]


def test_catalogue_csv_round_trips_through_the_loader():
    items = sample_catalogue()
    back = load_catalogue_csv(dump_catalogue_csv(items))
    assert [c.model_dump(mode="json") for c in back] == [c.model_dump(mode="json") for c in items]


def test_opportunities_accept_a_catalogue_csv(data_json):
    c = client()
    csv_text = ("item_id,name,category,unit_cost,unit_price,supplier_min_order_qty,sellers_count,"
                "requests_count,requests_window_days,requests_source,source\n"
                "Q1,Mango juice,beverages,30,45,6,3,14,28,notebook,test csv\n")
    body = opp_request(c, confirmed_profile(c), data_json, catalogue_csv=csv_text).json()
    assert body["catalogue_source"] == "provided_csv"
    opps = body["opportunities"]["opportunities"]
    assert [o["name"] for o in opps] == ["Mango juice"]
    assert opps[0]["demand_basis"] == "observed"  # 14 logged requests make it observed


def test_opportunities_bad_catalogue_csv_is_a_clear_422(data_json):
    c = client()
    r = opp_request(c, confirmed_profile(c), data_json, catalogue_csv="item_id,name\nX,Widget\n")
    assert r.status_code == 422 and r.json()["error"]["code"] == "CSV_INVALID"
