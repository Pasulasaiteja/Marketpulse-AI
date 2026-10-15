/* MarketPulse retailer interface (vanilla JS, no build step).
 *
 * Core principle: this file NEVER computes a forecast or a money figure. Every number shown in
 * the plan is copied from the API response and tagged with data-path (a JSON Pointer into the
 * plan) and data-value (the raw value), so tests can prove displayed == optimizer output.
 * Display formatting (separators, 2 decimals) is the only transformation.
 */
"use strict";

const LANGS = ["en", "fr", "es", "hi"];
const LOCALE = { en: "en-US", fr: "fr-FR", es: "es-ES", hi: "hi-IN" };
const FIELD_ORDER = ["location_type", "income_band", "payday_day", "nearby_anchors",
  "shop_category", "place_name", "country", "currency"];
const OPTIONS = {
  location_type: ["urban_dense", "urban", "peri_urban", "rural", "unknown"],
  income_band: ["low", "lower_middle", "middle", "upper", "unknown"],
  nearby_anchors: ["school", "market", "transport_hub", "place_of_worship", "hospital",
    "university", "office_district", "factory", "other"],
  shop_category: ["grocery", "pharmacy", "general_store", "clothing", "electronics", "hardware", "other"],
};
const OPTION_PREFIX = { location_type: "location_", income_band: "income_",
  nearby_anchors: "anchor_", shop_category: "cat_" };

const CURRENCY_MAP = {
  "$": "USD", "USD": "USD", "DOLLAR": "USD", "DOLLARS": "USD", "US DOLLAR": "USD", "US DOLLARS": "USD",
  "€": "EUR", "EUR": "EUR", "EURO": "EUR", "EUROS": "EUR",
  "£": "GBP", "GBP": "GBP", "POUND": "GBP", "POUNDS": "GBP", "QUID": "GBP",
  "₹": "INR", "INR": "INR", "RS": "INR", "RS.": "INR", "RUPEE": "INR", "RUPEES": "INR",
  "C$": "CAD", "CAD": "CAD", "CANADIAN DOLLAR": "CAD", "CANADIAN DOLLARS": "CAD",
  "A$": "AUD", "AUD": "AUD", "AUSTRALIAN DOLLAR": "AUD", "AUSTRALIAN DOLLARS": "AUD",
  "¥": "JPY", "JPY": "JPY", "YEN": "JPY",
  "PKR": "PKR", "PAKISTANI RUPEE": "PKR", "PAKISTANI RUPEES": "PKR", "₨": "PKR",
  "KES": "KES", "KSH": "KES", "SHILLING": "KES", "SHILLINGS": "KES",
  "SAR": "SAR", "RIYAL": "SAR", "RIYALS": "SAR",
  "AED": "AED", "DIRHAM": "AED", "DIRHAMS": "AED",
  "BRL": "BRL", "R$": "BRL", "REAL": "BRL", "REAIS": "BRL",
  "MXN": "MXN", "PESO": "MXN", "PESOS": "MXN", "MEXICAN PESO": "MXN",
  "CHF": "CHF", "FRANC": "CHF", "FRANCS": "CHF", "SWISS FRANC": "CHF",
  "CNY": "CNY", "RMB": "CNY", "YUAN": "CNY",
  "SGD": "SGD", "SINGAPORE DOLLAR": "SGD",
  "XAF": "XAF", "CFA": "XAF",
};

const COUNTRY_MAP = {
  "USA": "US", "UNITED STATES": "US", "UNITED STATES OF AMERICA": "US", "AMERICA": "US", "US": "US",
  "UK": "GB", "UNITED KINGDOM": "GB", "GREAT BRITAIN": "GB", "BRITAIN": "GB", "ENGLAND": "GB", "GB": "GB",
  "INDIA": "IN", "BHARAT": "IN", "HINDUSTAN": "IN", "IN": "IN",
  "FRANCE": "FR", "FR": "FR",
  "SPAIN": "ES", "ESPAÑA": "ES", "ESPANA": "ES", "ES": "ES",
  "GERMANY": "DE", "DEUTSCHLAND": "DE", "DE": "DE",
  "ITALY": "IT", "ITALIA": "IT", "IT": "IT",
  "CANADA": "CA", "CA": "CA",
  "AUSTRALIA": "AU", "AU": "AU",
  "JAPAN": "JP", "JP": "JP",
  "KENYA": "KE", "KE": "KE",
  "PAKISTAN": "PK", "PK": "PK",
  "ECUADOR": "EC", "EC": "EC",
  "NIGERIA": "NG", "NG": "NG",
  "SOUTH AFRICA": "ZA", "ZA": "ZA",
  "BRAZIL": "BR", "BRASIL": "BR", "BR": "BR",
  "MEXICO": "MX", "MÉXICO": "MX", "MX": "MX",
  "UAE": "AE", "UNITED ARAB EMIRATES": "AE", "AE": "AE",
  "SAUDI ARABIA": "SA", "SA": "SA",
  "SINGAPORE": "SG", "SG": "SG",
  "SWITZERLAND": "CH", "CH": "CH",
  "CAMEROON": "CM", "CAMEROUN": "CM", "CM": "CM",
};

const POPULAR_CURRENCIES = ["USD", "EUR", "GBP", "INR", "CAD", "AUD", "JPY", "KES", "PKR", "SAR", "AED", "CHF", "BRL", "MXN", "XAF"];
const POPULAR_COUNTRIES = ["US", "GB", "IN", "FR", "ES", "DE", "IT", "CA", "AU", "JP", "KE", "PK", "EC", "NG", "ZA", "BR", "MX", "AE", "SA", "SG", "CH", "CM"];

const state = {
  lang: "en", screen: "describe", profile: null, followUps: [], threshold: 0.7, required: [],
  productsCsv: null, salesCsv: null, datasetId: null, stores: null, opps: null,
  budget: 5000, horizon: 14, step: 100, resp: null, seq: 0, timer: null,
};

/* ---------- helpers ---------- */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

function el(tag, attrs = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") n.className = v;
    else if (k === "text") n.textContent = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? "" : v);
  }
  for (const c of kids.flat()) if (c != null) n.append(c.nodeType ? c : document.createTextNode(c));
  return n;
}

function t(key, vars = {}) {
  const table = window.I18N[state.lang] || {};
  let s = table[key] ?? window.I18N.en[key] ?? key;
  for (const [k, v] of Object.entries(vars)) s = s.replaceAll("{" + k + "}", v);
  return s;
}
const hasKey = (key) => (window.I18N[state.lang] && key in window.I18N[state.lang]) || key in window.I18N.en;

const nf = (opts) => new Intl.NumberFormat(LOCALE[state.lang] + "-u-nu-latn", opts);
const fmt = {
  money: (v) => nf({ minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(v),
  qty: (v) => nf({ maximumFractionDigits: 0 }).format(v),
  dec: (v) => nf({ maximumFractionDigits: 2 }).format(v),
  pct: (v) => nf({ style: "percent", maximumFractionDigits: 0 }).format(v),
};

/** A displayed plan figure: exact raw value + JSON Pointer travel with the text. */
function num(value, kind, path, extra = "") {
  return el("span", { class: ("num " + extra).trim(), "data-value": String(value),
    "data-path": path || null, text: fmt[kind](value) });
}

function storeLang() { try { localStorage.setItem("mp_lang", state.lang); } catch (_) { /* private mode */ } }
function loadLang() {
  let l = null;
  try { l = localStorage.getItem("mp_lang"); } catch (_) { /* ignore */ }
  l = l || (navigator.language || "en").slice(0, 2);
  return LANGS.includes(l) ? l : "en";
}

/* ---------- alerts ---------- */
function errMsg(e) {
  const key = "err_" + e.code;
  if (e.code === "MODULE_FAILED") return t(key, { module: e.module || "?" });
  if (e.code && hasKey(key)) return t(key);
  if (e.message) return e.message; // server text (English); shown as-is rather than guessed
  return t("err_generic");
}
function showError(e) {
  const box = $("#alerts");
  box.replaceChildren(el("div", { class: "alert" },
    el("span", { text: errMsg(e) }),
    el("button", { type: "button", text: t("dismiss"), onclick: clearAlerts })));
  // The alert sits at the top of the page; the retailer may have tapped a button far below it.
  box.scrollIntoView({ block: "start", behavior: "auto" });
}
function clearAlerts() { $("#alerts").replaceChildren(); }

/* ---------- API ---------- */
async function api(path, body, method = "POST") {
  let res;
  try {
    res = await fetch(path, { method, headers: { "content-type": "application/json" },
      body: method === "POST" ? JSON.stringify(body) : undefined });
  } catch (_) { throw { code: "NETWORK", message: t("err_network") }; }
  let json = null;
  try { json = await res.json(); } catch (_) { /* non-JSON */ }
  if (!res.ok) {
    const e = (json && json.error) || {};
    throw { code: e.code || "HTTP_" + res.status, message: e.message,
      module: e.module_error && e.module_error.module };
  }
  return json;
}

function busy(btn, on) {
  if (!btn) return;
  btn.disabled = on;
  btn.setAttribute("aria-busy", on ? "true" : "false");
}

/* ---------- static i18n ---------- */
function applyStatic() {
  document.documentElement.lang = state.lang;
  $$("[data-i18n]").forEach((n) => { n.textContent = t(n.dataset.i18n); });
  $$("[data-i18n-ph]").forEach((n) => { n.setAttribute("placeholder", t(n.dataset.i18nPh)); });
  $$("#horizon option").forEach((o) => { o.textContent = o.value + " " + t("days"); });
  $("#chat-input").setAttribute("aria-label", t("chat_title"));
  $("#budget-num").setAttribute("aria-label", t("budget_label"));
  $("#steps").setAttribute("aria-label", t("step_plan"));
  renderSuggestions();
}

function show(name, focus = true) {
  state.screen = name;
  $$("[data-screen]").forEach((s) => { s.hidden = s.dataset.screen !== name; });
  const order = ["describe", "confirm", "plan"];
  const cur = name === "explore" ? "plan" : name;
  $$("#steps li").forEach((li) => {
    const i = order.indexOf(li.dataset.step);
    li.classList.toggle("done", i < order.indexOf(cur));
    if (li.dataset.step === cur) li.setAttribute("aria-current", "step");
    else li.removeAttribute("aria-current");
  });
  if (focus) $("#screen-" + name + " h2").focus({ preventScroll: false });
  window.scrollTo(0, 0);
}

/* ---------- screen 1: describe ---------- */
function setDataStatus(text) { $("#data-status").textContent = text; }

async function readFile(input) {
  const f = input.files && input.files[0];
  return f ? await f.text() : null;
}

async function onExtract(ev) {
  ev.preventDefault();
  clearAlerts();
  const description = $("#description").value.trim();
  const budget = Number($("#budget").value);
  if (!description) return showError({ code: "EMPTY_DESCRIPTION" });
  if (!(budget > 0)) return showError({ code: "INVALID_BUDGET" });
  if (!state.datasetId && !(state.productsCsv && state.salesCsv)) {
    return showError({ code: "NO_DATA", message: t("no_data") });
  }
  state.datasetId = null;
  state.stores = null;
  state.opps = null;
  state.budget = budget;
  state.horizon = Number($("#horizon").value);
  const btn = $("#btn-extract");
  busy(btn, true);
  try {
    const r = await api("/profile/extract", { description });
    state.profile = r.profile;
    state.followUps = r.follow_up_questions;
    state.threshold = r.low_confidence_threshold;
    state.required = r.required_fields;
    renderConfirm();
    show("confirm");
  } catch (e) { showError(e); } finally { busy(btn, false); }
}

/* ---------- screen 2: confirm ---------- */
function fieldNeedsCheck(name, f) {
  return (f.value === null && state.required.includes(name)) || (f.value !== null && f.source !== "retailer" && f.confidence < state.threshold) ||
    state.followUps.some((q) => q.field === name);
}

function optionLabel(name, v) { return t(OPTION_PREFIX[name] + v); }

function ensureDatalists() {
  if (!$("#currency-list")) {
    document.body.append(el("datalist", { id: "currency-list" },
      POPULAR_CURRENCIES.map((c) => el("option", { value: c }))));
  }
  if (!$("#country-list")) {
    document.body.append(el("datalist", { id: "country-list" },
      POPULAR_COUNTRIES.map((c) => el("option", { value: c }))));
  }
}

function buildControl(name, f, draftVal) {
  const id = "f-" + name;
  const cur = draftVal !== undefined ? draftVal : f.value;
  if (name === "nearby_anchors") {
    const chosen = new Set(cur || []);
    return el("div", { class: "chips", role: "group", "aria-labelledby": id + "-l" },
      OPTIONS[name].map((v) => el("label", { class: "chk" },
        el("input", { type: "checkbox", value: v, checked: chosen.has(v) || null, "data-anchor": v }),
        optionLabel(name, v))));
  }
  if (OPTIONS[name]) {
    const sel = el("select", { id, "data-control": name },
      el("option", { value: "", text: t("blank") }),
      OPTIONS[name].map((v) => el("option", { value: v, text: optionLabel(name, v) })));
    sel.value = cur ?? "";
    return sel;
  }
  if (name === "payday_day") {
    return el("input", { id, type: "number", min: "1", max: "31", inputmode: "numeric",
      "data-control": name, value: cur ?? "" });
  }
  if (name === "currency" || name === "country") {
    ensureDatalists();
    return el("input", {
      id,
      type: "text",
      "data-control": name,
      value: cur ?? "",
      list: name === "currency" ? "currency-list" : "country-list",
      autocapitalize: "characters",
      placeholder: name === "currency" ? "e.g. USD, EUR, GBP" : "e.g. US, GB, FR",
    });
  }
  return el("input", { id, type: "text", "data-control": name, value: cur ?? "" });
}

function readControl(name) {
  if (name === "nearby_anchors") {
    return $$("input[data-anchor]").filter((c) => c.checked).map((c) => c.value);
  }
  const c = $('[data-control="' + name + '"]');
  if (!c) return undefined;
  const raw = c.value.trim();
  if (raw === "") return null;
  if (name === "payday_day") return Number(raw);
  if (name === "currency") {
    const upper = raw.toUpperCase();
    return CURRENCY_MAP[raw] || CURRENCY_MAP[upper] || upper;
  }
  if (name === "country") {
    const upper = raw.toUpperCase();
    return COUNTRY_MAP[raw] || COUNTRY_MAP[upper] || upper;
  }
  return raw;
}

function collectDraft() {
  const d = {};
  for (const n of FIELD_ORDER) { const v = readControl(n); if (v !== undefined) d[n] = v; }
  return d;
}

function renderConfirm(draft = {}) {
  const box = $("#confirm-fields");
  box.replaceChildren();
  let firstCheck = null;
  for (const name of FIELD_ORDER) {
    const f = state.profile.fields[name];
    const needs = fieldNeedsCheck(name, f);
    const q = state.followUps.find((x) => x.field === name);
    const row = el("div", { class: "cf" + (needs ? " check" : ""), "data-field": name },
      el(name === "nearby_anchors" ? "div" : "label",
        { id: "f-" + name + "-l", for: name === "nearby_anchors" ? null : "f-" + name,
          text: t("f_" + name) }),
      buildControl(name, f, draft[name]),
      q ? el("p", { class: "q", text: q.question }) : null,
      el("div", { class: "meta" },
        needs ? el("span", { class: "badge warn", text: "! " + t("needs_check") }) : null,
        f.value === null ? el("span", { text: t("not_found") + (state.required.includes(name) ? "" : " (" + t("optional") + ")") })
          : f.source === "retailer" ? null
          : el("span", { text: t("confidence") + " " + fmt.pct(f.confidence) })));
    if (needs && !firstCheck) firstCheck = row;
    box.append(row);
  }
  return firstCheck;
}

function sameValue(name, a, b) {
  if (name === "nearby_anchors") return JSON.stringify([...(a || [])].sort()) === JSON.stringify([...(b || [])].sort());
  return (a ?? null) === (b ?? null);
}

async function onConfirm(ev) {
  ev.preventDefault();
  clearAlerts();
  const edits = {};
  for (const name of FIELD_ORDER) {
    const now = readControl(name);
    if (now !== undefined && !sameValue(name, now, state.profile.fields[name].value)) edits[name] = now;
  }
  if (edits.currency || edits.country) {
    state.datasetId = null;
    state.stores = null;
    state.opps = null;
  }
  const btn = $("#btn-confirm");
  busy(btn, true);
  try {
    const r = await api("/profile/confirm", { profile_id: state.profile.profile_id, edits });
    state.profile = r.profile;
    state.followUps = r.follow_up_questions || [];
    if (r.status === "needs_input") {
      const first = renderConfirm();
      if (first) first.scrollIntoView({ block: "center" });
      return;
    }
    await runPlan({ first: true });
  } catch (e) { showError(e); } finally { busy(btn, false); }
}

/* ---------- screen 3: plan ---------- */
const isMultiStore = () => !!state.salesCsv &&
  state.salesCsv.trim().split("\n")[0].toLowerCase().split(",").map((c) => c.trim()).includes("store_id");

/** Multi-store CSVs: the server splits them into one dataset per store; the plan then uses one. */
async function registerStores() {
  const r = await api("/stores", { profile_id: state.profile.profile_id,
    products_csv: state.productsCsv, sales_csv: state.salesCsv });
  state.stores = r.stores;
  state.datasetId = r.stores[0].dataset_id;
  const sel = $("#store-select");
  sel.replaceChildren(...r.stores.map((s) => el("option", { value: s.dataset_id, text: s.store_id })));
  sel.value = state.datasetId;
}

async function runPlan({ first = false } = {}) {
  if (isMultiStore() && !state.stores) {
    try { await registerStores(); } catch (e) { showError(e); return; }
  }
  const seq = ++state.seq;
  const body = { profile_id: state.profile.profile_id, budget: state.budget,
    horizon_days: state.horizon, language: state.lang };
  if (state.datasetId) body.dataset_id = state.datasetId;
  else { body.products_csv = state.productsCsv; body.sales_csv = state.salesCsv; }
  if (!first) {
    $("#plan-status").textContent = t("updating");
    $$(".profit, #buy-list, #explanation").forEach((n) => n.classList.add("dim"));
  }
  try {
    const r = await api("/plan", body);
    if (seq !== state.seq) return; // a newer request superseded this one
    if (r.status === "needs_confirmation") {
      state.followUps = r.follow_up_questions || [];
      state.profile = r.profile;
      renderConfirm();
      show("confirm");
      return;
    }
    state.resp = r;
    state.datasetId = r.dataset_id;
    renderPlan(first);
    if (first) show("plan");
  } catch (e) {
    if (seq === state.seq) showError(e);
  } finally {
    if (seq === state.seq) {
      $("#plan-status").textContent = "";
      $$(".dim").forEach((n) => n.classList.remove("dim"));
    }
  }
}

function setNum(sel, value, kind, path) {
  const n = $(sel);
  n.textContent = fmt[kind](value);
  n.dataset.value = String(value);
  n.dataset.path = path;
}

function flag(text, bad = false) { return el("p", { class: "flag" + (bad ? " bad" : ""), text }); }

function chip(text, cls) { return el("span", { class: "badge " + cls, text }); }

function lineRow(line, i, forecasts, names, skipped) {
  const fc = forecasts[line.product_id];
  const base = "/lines/" + i;
  const chips = [];
  const unc = { low: "ok", medium: "warn", high: "bad" }[line.uncertainty];
  if (!skipped) chips.push(chip((line.uncertainty === "low" ? "" : "! ") + t("unc_" + line.uncertainty), unc));
  if (fc && fc.cold_start) chips.push(chip("! " + t("flag_cold_start"), "warn"));
  else if (fc && fc.low_data) chips.push(chip("! " + t("flag_low_data"), "warn"));
  for (const code of line.reason_codes) {
    chips.push(chip(hasKey("reason_" + code) ? t("reason_" + code) : code, "plain"));
  }
  const summary = el("summary", {},
    el("span", { class: "qty" }, num(line.order_qty, "qty", base + "/order_qty")),
    el("span", { class: "pname", text: names[line.product_id] || line.product_id }),
    skipped ? el("span") : el("span", { class: "pcost" }, num(line.line_cost, "money", base + "/line_cost")),
    el("span", { class: "psub" }, chips));
  const detail = el("div", { class: "detail" }, el("dl", {},
    el("dt", { text: t("unit_cost") }), el("dd", {}, num(line.unit_cost, "money", base + "/unit_cost")),
    skipped ? null : el("dt", { text: t("line_profit") }),
    skipped ? null : el("dd", {}, num(line.expected_profit, "money", base + "/expected_profit")),
    el("dt", { text: t("demand_label") + " (" + t("units") + ")" }),
    el("dd", {}, num(line.expected_demand, "dec", base + "/expected_demand")),
    el("dt", { text: t("stockout_label") }),
    el("dd", {}, num(line.stockout_probability, "pct", base + "/stockout_probability"))));
  return el("li", { "data-product": line.product_id }, el("details", {}, summary, detail));
}

function renderPlan(first = false) {
  const r = state.resp, p = r.plan;
  const names = r.product_names || {};
  const forecasts = Object.fromEntries(r.forecast.forecasts.map((f) => [f.product_id, f]));

  $("#store-box").hidden = !(state.stores && state.stores.length > 1);
  for (const id of ["#cur-a", "#cur-b", "#cur-c"]) $(id).textContent = p.currency;
  setNum("#spend-val", p.total_cost, "money", "/total_cost");
  setNum("#budget-val", p.budget, "money", "/budget");
  setNum("#profit-val", p.expected_total_profit, "money", "/expected_total_profit");
  // The bar width is the optimizer's own capital_utilization, not a ratio computed here.
  $("#tape-fill").style.width = Math.round(Math.min(1, p.capital_utilization) * 1000) / 10 + "%";
  $("#tape").setAttribute("aria-label", t("spend_label") + " " + fmt.money(p.total_cost) + " " +
    t("of_budget") + " " + fmt.money(p.budget));

  // budget controls
  const range = $("#budget-range"), numIn = $("#budget-num");
  if (first || !state.step) {
    state.step = Math.pow(10, Math.max(0, Math.floor(Math.log10(p.budget)) - 1));
    range.step = String(state.step);
    range.min = String(state.step);
    range.max = String(Math.max(p.budget * 2, state.step * 10));
  }
  if (p.budget > Number(range.max)) range.max = String(p.budget);
  if (document.activeElement !== range) range.value = String(p.budget);
  if (document.activeElement !== numIn) numIn.value = String(p.budget);
  $("#budget").value = String(p.budget);

  // flags: API warnings, then low-confidence items
  const flags = $("#plan-flags");
  flags.replaceChildren();
  for (const w of r.warnings) flags.append(flag(hasKey("warn_" + w.code) ? t("warn_" + w.code) : w.message));
  const shaky = p.lines.some((l) => l.order_qty > 0 && (l.uncertainty === "high" ||
    (forecasts[l.product_id] && (forecasts[l.product_id].low_data || forecasts[l.product_id].cold_start))));
  if (shaky) flags.append(flag(t("low_conf_banner")));

  const ex = $("#explanation");
  if (r.explanation) { ex.textContent = r.explanation.text; ex.classList.remove("missing"); ex.lang = r.explanation.language; }
  else { ex.textContent = t("explanation_missing"); ex.classList.add("missing"); ex.removeAttribute("lang"); }

  // lines
  const idx = p.lines.map((l, i) => [l, i]);
  const buy = idx.filter(([l]) => l.order_qty > 0).sort((a, b) => b[0].line_cost - a[0].line_cost);
  const skip = idx.filter(([l]) => l.order_qty === 0);
  const buyList = $("#buy-list");
  buyList.replaceChildren(...(buy.length
    ? buy.map(([l, i]) => lineRow(l, i, forecasts, names, false))
    : [el("li", { class: "muted", text: t("buy_empty"), style: "padding:14px 0" })]));
  $("#skip-list").replaceChildren(...skip.map(([l, i]) => lineRow(l, i, forecasts, names, true)));
  $("#skip-list").hidden = $("#skip-title").hidden = skip.length === 0;

  // risks
  const rl = $("#risk-list");
  rl.replaceChildren(...(p.risks.length ? p.risks.map((k) => el("li", {},
    chip(k.severity === "high" ? "! " + t("unc_high") : k.severity, k.severity === "high" ? "bad" : "warn"), " ",
    el("span", { text: (k.product_id ? (names[k.product_id] || k.product_id) + ": " : "") +
      (hasKey("risk_" + k.code) ? t("risk_" + k.code) : k.code) })))
    : [el("li", { class: "muted", text: t("no_risks") })]));

  // sensitivity
  const tb = $("#sens-table tbody");
  tb.replaceChildren(...p.budget_sensitivity.map((b, j) => el("tr", {},
    el("td", {}, num(b.budget, "money", "/budget_sensitivity/" + j + "/budget")),
    el("td", {}, num(b.total_cost, "money", "/budget_sensitivity/" + j + "/total_cost")),
    el("td", {}, num(b.expected_total_profit, "money", "/budget_sensitivity/" + j + "/expected_total_profit")))));

  $("#timing").textContent = t("ready_in") + " " + Math.round(r.timings_ms.total) + " " + t("ms") +
    (r.cache && r.cache.forecast_hit ? " (" + t("cached") + ")" : "");
  document.body.dataset.planRequest = r.request_id;
}


/* ---------- screen 4: explore new products (Component D) ----------
 * Same rule as the plan: every number is copied from the API response with data-path/data-value.
 * The range bar is a drawing of low/mid/high as fractions of high; it adds no figure of its own.
 */
const LEVELS = [[0.34, "lvl_low"], [0.67, "lvl_medium"], [Infinity, "lvl_high"]];
const SCORE_KEYS = ["demand_potential", "competition", "profitability", "capital_requirement", "uncertainty"];
const levelOf = (v) => t(LEVELS.find(([max]) => v < max)[1]);

function rangeBar(d, hyp) {
  const pos = (v) => (d.high > 0 ? Math.round(v / d.high * 1000) / 10 : 0) + "%";
  const bar = el("div", { class: "rbar " + (hyp ? "hyp" : "obs"), role: "img",
    "aria-label": t("est_range") + " " + fmt.qty(d.low) + " – " + fmt.qty(d.high) },
    el("div", { class: "rfill", style: "left:" + pos(d.low) + ";right:0" }),
    el("div", { class: "rmid", style: "left:" + pos(d.mid) }));
  return bar;
}

function oppCard(o, i, cur, trialAvail) {
  const hyp = o.demand_basis === "hypothesized";
  const base = "/opportunities/" + i;
  const d = o.demand;
  const scores = el("ul", { class: "scores" }, SCORE_KEYS.map((k) => el("li", {},
    el("span", { text: t("sc_" + k) }), " ",
    el("strong", { text: levelOf(o.scores[k]) }), " ",
    el("span", { class: "muted small" }, "(", num(o.scores[k], "dec", base + "/scores/" + k), ")"))));
  const kids = [
    el("summary", {},
      el("span", { class: "pname", text: o.name }),
      el("span", { class: "psub" },
        chip(hyp ? t("basis_hyp") : t("basis_observed"), hyp ? "warn" : "plain"),
        chip(t("not_forecast"), "plain")),
      rangeBar(d, hyp),
      el("span", { class: "rnums" },
        el("span", {}, t("range_low") + " ", num(d.low, "qty", base + "/demand/low")),
        el("span", {}, t("range_mid") + " ", num(d.mid, "qty", base + "/demand/mid")),
        el("span", {}, t("range_high") + " ", num(d.high, "qty", base + "/demand/high"))),
      el("span", { class: "muted small" }, d.unit + " · ", num(d.horizon_days, "qty", base + "/demand/horizon_days"),
        " " + t("days")))
  ];
  const body = el("div", { class: "detail wide" });
  if (hyp) {
    body.append(el("p", { class: "muted", text: t("based_on_similar") }),
      el("ul", { class: "scores" }, o.comparables.map((c, j) => el("li", {},
        c.name + " ", el("span", { class: "muted small" }, "(", num(c.similarity, "dec",
          base + "/comparables/" + j + "/similarity"), ")")))));
  } else if (o.observed_requests) {
    body.append(el("p", {}, num(o.observed_requests.count, "qty", base + "/observed_requests/count"),
      " " + t("requests_in") + " ", num(o.observed_requests.window_days, "qty",
        base + "/observed_requests/window_days"), " " + t("days")));
  }
  body.append(el("p", { class: "muted small", text: t("scores_exact") }), scores);
  for (const n of o.notes) body.append(flag(hasKey("note_" + n) ? t("note_" + n) : n));
  kids.push(body);

  const trial = el("div", { class: "trial" }, el("strong", { text: t("trial_title") }));
  if (o.trial_order_qty != null) {
    trial.append(el("p", { class: "muted small", text: t("trial_hint") }),
      el("p", {}, t("trial_qty_label") + ": ", num(o.trial_order_qty, "qty", base + "/trial_order_qty"), " · " +
        t("trial_cost_label") + ": ", num(o.trial_cost, "money", base + "/trial_cost"), " " + cur));
    if (o.trial_order_qty === 0) trial.append(el("p", { class: "muted", text: t("trial_zero") }));
  } else if (!trialAvail) trial.append(el("p", { class: "muted", text: t("trial_unavailable") }));
  else trial.append(el("p", { class: "muted", text: t("trial_zero") }));
  return el("li", { class: "opp", "data-basis": o.demand_basis }, el("details", {}, kids), trial);
}

function renderExplore() {
  const r = state.opps, out = r.opportunities;
  $("#explore-sample").hidden = r.catalogue_source !== "sample_synthetic";
  const fl = $("#explore-flags");
  fl.replaceChildren(...r.warnings.map((w) => flag(hasKey("warn_" + w.code) ? t("warn_" + w.code) : w.message)));
  const body = $("#explore-body");
  body.replaceChildren();
  const groups = [["observed", "grp_observed"], ["hypothesized", "grp_hyp"]];
  for (const [basis, key] of groups) {
    const items = out.opportunities.map((o, i) => [o, i]).filter(([o]) => o.demand_basis === basis);
    if (!items.length) continue;
    body.append(el("h3", { text: t(key) }), el("p", { class: "muted small", text: t(key + "_hint") }),
      el("ul", { class: "lines opps" }, items.map(([o, i]) =>
        oppCard(o, i, out.currency, out.trial_orders_available))));
  }
  if (!out.opportunities.length) body.append(el("p", { class: "muted", text: t("no_opps") }));
  if (out.excluded.length) {
    body.append(el("h3", { text: t("excluded_title") }), el("ul", { class: "risks" }, out.excluded.map((x) =>
      el("li", {}, el("strong", { text: x.name }), " – ",
        hasKey("excl_" + x.reason) ? t("excl_" + x.reason) : x.reason))));
  }
}

async function onExplore() {
  clearAlerts();
  const seq = ++state.seq;
  const body = { profile_id: state.profile.profile_id, budget: state.budget, horizon_days: state.horizon };
  if (state.datasetId) body.dataset_id = state.datasetId;
  else { body.products_csv = state.productsCsv; body.sales_csv = state.salesCsv; }
  const btn = $("#btn-explore");
  busy(btn, true);
  try {
    const r = await api("/opportunities", body);
    if (seq !== state.seq) return;
    state.opps = r;
    show("explore");
    renderExplore();
  } catch (e) {
    showError(e);
  } finally {
    busy(btn, false);
  }
}

function scheduleBudgetRun(value) {
  const v = Number(value);
  if (!(v > 0)) return;
  state.budget = v;
  setNum("#budget-val", v, "money", "/budget"); // shows the typed value until the plan answers
  clearTimeout(state.timer);
  state.timer = setTimeout(() => runPlan(), 250);
}

/* ---------- chat ---------- */
function addMsg(kind, text, who) {
  const li = el("li", { class: "msg " + kind },
    el("span", { class: "who", text: who }), el("span", { class: "body", text }));
  $("#chat-log").append(li);
  li.scrollIntoView({ block: "nearest" });
  return li;
}

async function ask(question) {
  question = question.trim();
  if (!question || !state.resp) return;
  addMsg("user", question, t("you"));
  const pending = addMsg("bot", "…", t("assistant"));
  const btn = $("#btn-ask");
  busy(btn, true);
  try {
    const r = await api("/ask", { request_id: state.resp.request_id, question, language: state.lang });
    pending.querySelector(".body").textContent = r.explanation.text;
    pending.lang = r.explanation.language;
  } catch (e) {
    pending.classList.add("err");
    pending.querySelector(".body").textContent = errMsg(e);
  } finally { busy(btn, false); }
}

function renderSuggestions() {
  const box = $("#suggest");
  box.replaceChildren(...["chat_s1", "chat_s2"].map((k) => el("button", {
    type: "button", text: t(k), onclick: () => ask(t(k)) })));
}

/* ---------- wiring ---------- */
function onLang(ev) {
  const draft = state.screen === "confirm" ? collectDraft() : null;
  state.lang = ev.target.value;
  storeLang();
  applyStatic();
  if (state.screen === "confirm" && state.profile) renderConfirm(draft);
  if (state.screen === "explore" && state.opps) renderExplore();
  if (state.screen === "plan" && state.resp) { renderPlan(); runPlan(); } // re-explain in new language
}

function init() {
  state.lang = loadLang();
  const sel = $("#lang");
  sel.replaceChildren(...LANGS.map((l) => el("option", { value: l, text: window.I18N[l].lang_name })));
  sel.value = state.lang;
  sel.addEventListener("change", onLang);
  applyStatic();

  $("#form-describe").addEventListener("submit", onExtract);
  $("#form-confirm").addEventListener("submit", onConfirm);
  $("#btn-back").addEventListener("click", () => show("describe"));
  $("#btn-edit").addEventListener("click", () => show("describe"));
  $("#btn-explore").addEventListener("click", onExplore);
  $("#btn-explore-back").addEventListener("click", () => show("plan"));
  $("#btn-example").addEventListener("click", () => {
    $("#description").value = t("example_desc");
    $("#description").focus();
  });
  $("#btn-demo").addEventListener("click", async () => {
    clearAlerts();
    try {
      const d = await api("/demo/files", null, "GET");
      state.productsCsv = d.products_csv; state.salesCsv = d.sales_csv; state.datasetId = null;
      state.stores = null; state.opps = null;
      setDataStatus(t("demo_loaded"));
    } catch (e) { showError(e); }
  });
  $("#btn-demo-chain").addEventListener("click", async () => {
    clearAlerts();
    try {
      const d = await api("/demo/chain", null, "GET");
      state.productsCsv = d.products_csv; state.salesCsv = d.sales_csv; state.datasetId = null;
      state.stores = null; state.opps = null;
      setDataStatus(t("chain_loaded"));
    } catch (e) { showError(e); }
  });
  $("#store-select").addEventListener("change", (ev) => {
    state.datasetId = ev.target.value;
    state.opps = null;
    runPlan();
  });
  for (const [id, key] of [["#file-products", "productsCsv"], ["#file-sales", "salesCsv"]]) {
    $(id).addEventListener("change", async (ev) => {
      state[key] = await readFile(ev.target);
      state.datasetId = null; // new files => new dataset
      state.stores = null; state.opps = null;
      setDataStatus(state.productsCsv && state.salesCsv ? t("files_loaded") : "");
    });
  }
  $("#budget-range").addEventListener("input", (ev) => {
    $("#budget-num").value = ev.target.value;
    scheduleBudgetRun(ev.target.value);
  });
  $("#budget-num").addEventListener("input", (ev) => {
    const v = Number(ev.target.value);
    if (v > Number($("#budget-range").max)) $("#budget-range").max = String(v);
    if (v > 0) $("#budget-range").value = String(v);
    scheduleBudgetRun(ev.target.value);
  });
  $("#form-chat").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const q = $("#chat-input").value;
    $("#chat-input").value = "";
    ask(q);
  });
  show("describe", false);
}

document.addEventListener("DOMContentLoaded", init);
