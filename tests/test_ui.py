"""Retailer interface tests, run in real Chromium at a 375x812 phone viewport.

Covers: core flow, edits propagate, budget live re-run, low-confidence follow-up, non-English
chat, failure honesty, number integrity (displayed text == optimizer output), mobile layout.
Skipped automatically if Playwright/Chromium are not installed.
"""

import contextlib
import re
import socket
import threading
import time

import pytest

pytest.importorskip("playwright.sync_api")
import uvicorn  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from marketpulse import config  # noqa: E402
from marketpulse.api.app import create_app  # noqa: E402
from marketpulse.contracts.errors import ModuleFailure  # noqa: E402
from marketpulse.contracts.models import SalesRecord  # noqa: E402
from marketpulse.csvloader import dump_csv  # noqa: E402
from marketpulse.mocks.fixtures import make_canonical_data  # noqa: E402
from marketpulse.registry import default_modules  # noqa: E402

EXAMPLE = "Small shop near a school in Delhi, India. Customers are paid on the 25th."
IS_PLAN = lambda r: r.url.endswith("/plan") and r.request.method == "POST"  # noqa: E731
IS_ASK = lambda r: r.url.endswith("/ask") and r.request.method == "POST"  # noqa: E731


@contextlib.contextmanager
def serve(modules=None):
    app = create_app(modules, audit_path=None)
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.02)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        th.join(5)


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"Chromium not available: {exc}")
        yield b
        b.close()


@pytest.fixture
def base():
    with serve() as url:
        yield url


@pytest.fixture
def page(browser):
    ctx = browser.new_context(viewport={"width": 375, "height": 812}, is_mobile=True, has_touch=True)
    pg = ctx.new_page()
    pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    pg.on("console", lambda m: pg.errors.append(m.text) if m.type == "error" else None)
    yield pg
    ctx.close()


# ------------------------------------------------------------------ helpers
def overflow(pg):
    return pg.evaluate("document.documentElement.scrollWidth - window.innerWidth")


def load_demo(pg):
    pg.click("#btn-demo")
    pg.wait_for_function("document.querySelector('#data-status').textContent.length > 0")


def to_confirm(pg, base, desc=EXAMPLE, demo=True):
    pg.goto(base + "/")
    pg.fill("#description", desc)
    if demo:
        load_demo(pg)
    pg.click("#btn-extract")
    pg.wait_for_selector("#screen-confirm:not([hidden])")


def sync_plan(pg, response):
    body = response.json()
    pg.wait_for_function(f"document.body.dataset.planRequest === '{body['request_id']}'")
    return body


def confirm_to_plan(pg):
    with pg.expect_response(IS_PLAN) as info:
        pg.click("#btn-confirm")
    body = sync_plan(pg, info.value)
    pg.wait_for_selector("#screen-plan:not([hidden])")
    return body


def to_plan(pg, base, desc=EXAMPLE):
    to_confirm(pg, base, desc)
    return confirm_to_plan(pg)


def parse_display(text, lang):
    t = re.sub(r"[\s  ]", "", text)
    if lang in ("fr", "es"):
        t = t.replace(".", "").replace(",", ".")
    else:
        t = t.replace(",", "")
    return float(t.rstrip("%"))


def resolve(doc, pointer):
    cur = doc
    for part in pointer.strip("/").split("/"):
        cur = cur[int(part)] if isinstance(cur, list) else cur[part]
    return cur


def assert_numbers_match(pg, body, lang):
    """Every plan figure on screen: raw data-value AND the displayed text equal the plan."""
    pg.evaluate("document.querySelectorAll('details').forEach(d => { d.open = true; })")
    nodes = pg.query_selector_all("#screen-plan [data-path]")
    assert len(nodes) > 20, "plan figures were not rendered"
    seen = set()
    for n in nodes:
        path, raw, text = n.get_attribute("data-path"), n.get_attribute("data-value"), n.inner_text()
        actual = resolve(body["plan"], path)
        seen.add(path)
        assert float(raw) == pytest.approx(actual), path
        if path.endswith("stockout_probability"):
            assert parse_display(text, lang) == round(actual * 100), (path, text)
        else:
            assert parse_display(text, lang) == pytest.approx(actual, abs=0.005), (path, text)
    assert {"/total_cost", "/budget", "/expected_total_profit"} <= seen


def small_targets(pg):
    sel = "button:visible, select:visible, input[type=text]:visible, input[type=number]:visible"
    return [(e.get_attribute("id") or e.inner_text()[:20], e.bounding_box()["height"])
            for e in pg.query_selector_all(sel) if e.bounding_box()["height"] < 43.5]


# -------------------------------------------------------------------- tests
def test_core_flow_with_csv_upload_on_mobile(page, base, tmp_path):
    pc, sc = dump_csv(make_canonical_data())
    (tmp_path / "products.csv").write_text(pc)
    (tmp_path / "sales.csv").write_text(sc)
    page.goto(base + "/")
    assert overflow(page) == 0
    page.fill("#description", EXAMPLE)
    page.set_input_files("#file-products", str(tmp_path / "products.csv"))
    page.set_input_files("#file-sales", str(tmp_path / "sales.csv"))
    page.fill("#budget", "5000")
    page.click("#btn-extract")
    page.wait_for_selector("#screen-confirm:not([hidden])")
    assert overflow(page) == 0
    assert page.input_value('[data-control="country"]') == "IN"
    assert page.is_checked('input[data-anchor="school"]')
    body = confirm_to_plan(page)
    assert overflow(page) == 0
    assert body["plan"]["total_cost"] <= 5000
    assert page.locator("#buy-list li[data-product]").count() >= 1
    assert page.inner_text("#explanation").strip()
    assert page.get_attribute("#steps li[data-step=plan]", "aria-current") == "step"
    assert page.errors == []


def test_touch_targets_are_large_enough(page, base):
    page.goto(base + "/")
    assert small_targets(page) == []
    to_plan(page, base)
    assert small_targets(page) == []


@pytest.mark.parametrize("lang", config.SUPPORTED_LANGUAGES)
def test_numbers_on_screen_equal_optimizer_output(page, base, lang):
    body = to_plan(page, base)
    if lang != "en":
        with page.expect_response(IS_PLAN) as info:
            page.select_option("#lang", lang)
        body = sync_plan(page, info.value)
    assert page.evaluate("document.documentElement.lang") == lang
    assert_numbers_match(page, body, lang)
    assert body["plan"]["total_cost"] <= body["plan"]["budget"]
    assert overflow(page) == 0


def test_budget_change_updates_live_within_target(page, base):
    first = to_plan(page, base)
    t0 = time.perf_counter()
    with page.expect_response(IS_PLAN) as info:
        page.fill("#budget-num", "3000")
    body = sync_plan(page, info.value)
    elapsed = time.perf_counter() - t0
    assert elapsed < config.PLAN_LATENCY_WARM_SECONDS
    assert body["plan"]["budget"] == 3000 and body["plan"]["total_cost"] <= 3000
    assert body["plan"]["lines"] != first["plan"]["lines"]
    assert body["cache"]["forecast_hit"] is True
    assert_numbers_match(page, body, "en")
    assert page.input_value("#budget-range") == "3000"
    width = float(page.eval_on_selector("#tape-fill", "e => e.style.width").rstrip("%"))
    assert width == pytest.approx(body["plan"]["capital_utilization"] * 100, abs=0.06)


def test_slider_drag_reruns_plan(page, base):
    to_plan(page, base)
    with page.expect_response(IS_PLAN) as info:
        page.eval_on_selector("#budget-range", """e => {
            e.value = '3000'; e.dispatchEvent(new Event('input', {bubbles: true})); }""")
    body = sync_plan(page, info.value)
    assert body["plan"]["budget"] == 3000
    assert page.input_value("#budget-num") == "3000"


def test_rapid_budget_changes_show_only_the_latest(page, base):
    to_plan(page, base)
    with page.expect_response(IS_PLAN) as info:
        for v in ("4500", "4000", "3500", "3000"):
            page.fill("#budget-num", v)
    body = sync_plan(page, info.value)
    page.wait_for_timeout(600)
    assert body["plan"]["budget"] == 3000
    assert page.get_attribute("body", "data-plan-request") == body["request_id"]
    assert parse_display(page.inner_text("#budget-val"), "en") == 3000


def test_description_edit_school_to_market_changes_plan(page, base):
    first = to_plan(page, base)
    page.click("#btn-edit")
    page.wait_for_selector("#screen-describe:not([hidden])")
    page.fill("#description", EXAMPLE.replace("school", "market"))
    page.click("#btn-extract")
    page.wait_for_selector("#screen-confirm:not([hidden])")
    assert page.is_checked('input[data-anchor="market"]')
    assert not page.is_checked('input[data-anchor="school"]')
    second = confirm_to_plan(page)
    assert second["forecast"]["context_features_used"] != first["forecast"]["context_features_used"]
    assert second["plan"]["lines"] != first["plan"]["lines"]
    assert second["cache"]["forecast_hit"] is False
    assert_numbers_match(page, second, "en")


def test_retailer_correction_on_confirm_screen_propagates(page, base):
    to_confirm(page, base)
    page.uncheck('input[data-anchor="school"]')
    page.check('input[data-anchor="market"]')
    body = confirm_to_plan(page)
    used = body["forecast"]["context_features_used"]
    assert "near_market" in used and "near_school" not in used


def test_low_confidence_input_asks_follow_up_questions(page, base):
    to_confirm(page, base, desc="I sell rice and soap")
    flagged = {r.get_attribute("data-field") for r in page.query_selector_all(".cf.check")}
    assert {"country", "currency", "location_type"} <= flagged
    assert page.inner_text('[data-field="country"] .q').strip()
    assert "optional" in page.inner_text('[data-field="place_name"]')
    assert "place_name" not in flagged  # optional + empty must not nag
    page.click("#btn-confirm")  # nothing fixed: must NOT proceed to a plan
    page.wait_for_function("document.querySelectorAll('.cf.check').length > 0")
    assert page.is_visible("#screen-confirm") and page.is_hidden("#screen-plan")
    page.select_option('[data-control="location_type"]', "urban")
    page.fill('[data-control="country"]', "in")
    page.fill('[data-control="currency"]', "inr")
    body = confirm_to_plan(page)
    assert body["status"] == "ok"
    assert page.is_visible("#screen-plan")


def test_why_chat_in_hindi_is_grounded(page, base):
    body = to_plan(page, base)
    with page.expect_response(IS_PLAN):
        page.select_option("#lang", "hi")
    page.wait_for_function("document.documentElement.lang === 'hi'")
    assert re.search(r"[ऀ-ॿ]", page.inner_text("#h-plan"))
    with page.expect_response(IS_ASK) as info:
        page.fill("#chat-input", "चावल की यह मात्रा क्यों?")
        page.click("#btn-ask")
    ans = info.value.json()
    page.wait_for_function(
        "document.querySelector('#chat-log .msg.bot .body').textContent !== '…'")
    shown = page.inner_text("#chat-log .msg.bot .body")
    assert ans["explanation"]["language"] == "hi"
    assert shown == ans["explanation"]["text"]
    assert f"{body['plan']['total_cost']:.2f}" in shown
    assert re.search(r"[ऀ-ॿ]", shown)
    assert page.locator("#chat-log .msg.user").count() == 1


def test_language_switch_keeps_plan_figures_and_translates_labels(page, base):
    body = to_plan(page, base)
    for lang in ("fr", "es", "hi", "en"):
        with page.expect_response(IS_PLAN) as info:
            page.select_option("#lang", lang)
        again = sync_plan(page, info.value)
        assert again["plan"]["lines"] == body["plan"]["lines"]
        text = page.inner_text("#screen-plan")
        assert not re.search(r"\b(reason_|err_|warn_|unc_|flag_)\w+", text), "raw i18n key shown"
    assert page.errors == []


def test_chat_suggestion_buttons_work(page, base):
    to_plan(page, base)
    with page.expect_response(IS_ASK):
        page.click("#suggest button >> nth=0")
    page.wait_for_function(
        "document.querySelector('#chat-log .msg.bot .body').textContent !== '…'")
    assert page.locator("#chat-log .msg").count() == 2


def test_failed_module_shows_honest_error_and_no_plan(page):
    mods = default_modules()

    def down(*a, **k):
        raise ModuleFailure("optimizer", "DOWN", "down")

    mods.optimizer.optimize = down
    with serve(mods) as url:
        to_confirm(page, url)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")  # tap Confirm from the bottom
        page.click("#btn-confirm")
        page.wait_for_selector("#alerts .alert")
        in_view = page.eval_on_selector(
            "#alerts .alert", "e => { const r = e.getBoundingClientRect();"
            " return r.top >= 0 && r.bottom <= window.innerHeight; }")
        assert in_view, "the error must be scrolled into view, not hidden at the top of the page"
        msg = page.inner_text("#alerts .alert")
        assert "optimizer" in msg and "no plan" in msg.lower()
        assert page.is_hidden("#screen-plan")
        assert "Traceback" not in page.content()


def test_explainer_down_still_shows_plan_with_notice(page):
    mods = default_modules()

    def down(*a, **k):
        raise ModuleFailure("explainer", "DOWN", "down")

    mods.explainer.explain = down
    with serve(mods) as url:
        body = to_plan(page, url)
        assert body["explanation"] is None
        assert page.is_visible("#screen-plan")
        assert page.locator("#explanation.missing").count() == 1
        assert page.locator("#plan-flags .flag").count() >= 1
        assert_numbers_match(page, body, "en")


def test_bad_csv_error_is_shown_to_retailer(page, base, tmp_path):
    pc, sc = dump_csv(make_canonical_data())
    (tmp_path / "p.csv").write_text(pc.replace("unit_price", "price"))
    (tmp_path / "s.csv").write_text(sc)
    page.goto(base + "/")
    page.fill("#description", EXAMPLE)
    page.set_input_files("#file-products", str(tmp_path / "p.csv"))
    page.set_input_files("#file-sales", str(tmp_path / "s.csv"))
    page.click("#btn-extract")
    page.wait_for_selector("#screen-confirm:not([hidden])")
    page.click("#btn-confirm")
    page.wait_for_selector("#alerts .alert")
    assert "unit_price" in page.inner_text("#alerts .alert")
    assert page.is_hidden("#screen-plan")


def test_missing_data_is_caught_before_calling_the_server(page, base):
    page.goto(base + "/")
    page.fill("#description", EXAMPLE)
    page.click("#btn-extract")
    page.wait_for_selector("#alerts .alert")
    assert page.is_visible("#screen-describe")


def test_low_data_product_is_flagged_in_ui(page):
    """A product we ARE buying but have little history for gets a row tag and a banner."""
    data = make_canonical_data()
    keep = [s for s in data.sales if s.product_id != "P006"]
    last = [s for s in data.sales if s.product_id == "P006"][-20:]  # 20 days: below the 28-day low-data line
    data = data.model_copy(update={"sales": keep + [SalesRecord(**s.model_dump()) for s in last]})
    pc, sc = dump_csv(data)
    with serve() as url:
        page.goto(url + "/")
        page.fill("#description", EXAMPLE)
        page.evaluate("([p, s]) => { state.productsCsv = p; state.salesCsv = s; }", [pc, sc])
        page.click("#btn-extract")
        page.wait_for_selector("#screen-confirm:not([hidden])")
        body = confirm_to_plan(page)
        line = next(x for x in body["plan"]["lines"] if x["product_id"] == "P006")
        assert line["order_qty"] > 0, "test premise: the low-data product is being ordered"
        row = page.locator('li[data-product="P006"]')
        assert "sales history" in row.inner_text().lower()
        assert page.locator("#plan-flags .flag").count() >= 1


# ------------------------------------------------------- explore (Component D)
IS_OPPS = lambda r: r.url.endswith("/opportunities") and r.request.method == "POST"  # noqa: E731


def to_explore(pg, base):
    to_plan(pg, base)
    with pg.expect_response(IS_OPPS) as info:
        pg.click("#btn-explore")
    pg.wait_for_selector("#screen-explore:not([hidden])")
    pg.wait_for_selector("#explore-body .opp")
    return info.value.json()


def test_explore_labels_observed_vs_hypothesized_and_never_says_forecast(page, base):
    body = to_explore(page, base)
    # the screen groups observed first, then hypothesized; order inside a group is the API's
    opps = sorted(body["opportunities"]["opportunities"], key=lambda o: o["demand_basis"] != "observed")
    cards = page.query_selector_all("#explore-body .opp")
    assert len(cards) == len(opps) > 0
    page.evaluate("document.querySelectorAll('details').forEach(d => { d.open = true; })")
    for c, o in zip(cards, opps, strict=True):
        assert c.get_attribute("data-basis") == o["demand_basis"]
        text = c.inner_text().lower()
        assert ("hypothesized" if o["demand_basis"] == "hypothesized" else "observed") in text
        assert "not a forecast" in text
        assert "forecast" not in text.replace("not a forecast", "")
    assert page.is_visible("#explore-sample")  # sample catalogue is disclosed
    assert overflow(page) == 0
    assert page.errors == []


def test_explore_numbers_equal_api_output(page, base):
    body = to_explore(page, base)
    page.evaluate("document.querySelectorAll('details').forEach(d => { d.open = true; })")
    nodes = page.query_selector_all("#screen-explore [data-path]")
    assert len(nodes) > 10
    seen = set()
    for n in nodes:
        path, raw, text = n.get_attribute("data-path"), n.get_attribute("data-value"), n.inner_text()
        actual = resolve(body["opportunities"], path)
        seen.add(path.split("/")[-1])
        assert float(raw) == pytest.approx(actual), path
        shown = parse_display(text, "en")
        tol = 0.5 if path.endswith(("/low", "/mid", "/high", "trial_order_qty")) else 0.005
        assert shown == pytest.approx(actual, abs=tol), (path, text)
    assert {"low", "mid", "high", "trial_order_qty", "trial_cost"} <= seen


@pytest.mark.parametrize("lang", ["fr", "hi"])
def test_explore_translates_labels_and_keeps_figures(page, base, lang):
    to_explore(page, base)
    before = page.eval_on_selector_all("#screen-explore [data-path]", "e => e.map(x => x.dataset.value)")
    page.select_option("#lang", lang)
    page.wait_for_function(f"document.documentElement.lang === '{lang}'")
    after = page.eval_on_selector_all("#screen-explore [data-path]", "e => e.map(x => x.dataset.value)")
    assert before == after
    assert "Not a forecast" not in page.inner_text("#screen-explore")


def test_explore_failure_is_shown_and_plan_stays(page, monkeypatch):
    from marketpulse.opportunities.discovery import DiscoveryEngine

    def down(self, *a, **k):
        raise ModuleFailure("opportunities", "DOWN", "down")

    with serve() as url:
        to_plan(page, url)
        monkeypatch.setattr(DiscoveryEngine, "discover", down)
        page.click("#btn-explore")
        page.wait_for_selector("#alerts .alert")
        assert "opportunities" in page.inner_text("#alerts .alert")
        assert page.is_visible("#screen-plan")
        assert "Traceback" not in page.content()


def test_explore_touch_targets_and_back(page, base):
    to_explore(page, base)
    assert small_targets(page) == []
    page.click("#btn-explore-back")
    assert page.is_visible("#screen-plan")


# ------------------------------------------------------------------ multi-store
def to_chain_plan(pg, base):
    pg.goto(base + "/")
    pg.fill("#description", EXAMPLE)
    pg.click("#btn-demo-chain")
    pg.wait_for_function("document.querySelector('#data-status').textContent.length > 0")
    pg.click("#btn-extract")
    pg.wait_for_selector("#screen-confirm:not([hidden])")
    return confirm_to_plan(pg)


def test_chain_data_shows_store_selector_and_each_store_has_its_own_plan(page, base):
    body = to_chain_plan(page, base)
    assert page.is_visible("#store-box")
    options = page.eval_on_selector_all("#store-select option", "o => o.map(x => x.textContent)")
    assert options == ["store-a", "store-b", "store-c"]
    assert_numbers_match(page, body, "en")
    first_profit = body["plan"]["expected_total_profit"]
    with page.expect_response(IS_PLAN) as info:
        page.select_option("#store-select", label="store-c")
    other = sync_plan(page, info.value)
    assert other["dataset_id"] != body["dataset_id"]
    assert other["plan"]["expected_total_profit"] != first_profit
    assert_numbers_match(page, other, "en")
    assert small_targets(page) == []
    assert overflow(page) == 0
    assert page.errors == []


def test_single_store_data_hides_the_store_selector(page, base):
    to_plan(page, base)
    assert page.is_hidden("#store-box")
