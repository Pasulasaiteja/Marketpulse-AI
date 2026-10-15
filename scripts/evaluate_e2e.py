"""End-to-end evaluation (task E), metrics JSON.

Runs the whole pipeline (extract -> confirm -> plan -> explain) on Member 1's data layer files and
reports: contract validity, budget feasibility, cross-language consistency, latency vs targets, a
time-based rolling-origin backtest, and the size of the zero-sales/stockout bias in their data.

HONEST SCOPE: every module here is a MOCK unless swapped in registry.default_modules(). The backtest
therefore measures the mock forecaster and proves the harness works; it is NOT evidence about
Member 2's model. Re-run with real modules to get real numbers.

Usage: python scripts/evaluate_e2e.py DATA_LAYER_DIR [--out reports/e2e_metrics.json]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from marketpulse import config  # noqa: E402
from marketpulse.adapters.data_layer import load_store  # noqa: E402
from marketpulse.api.app import create_app  # noqa: E402
from marketpulse.registry import default_modules  # noqa: E402

DESCS = {
    "en": "Small shop near a school in Delhi, India.",
    "fr": "Petite boutique près d'une école à Delhi, India.",
    "es": "Pequeña tienda cerca de una escuela en Delhi, India.",
    "hi": "दिल्ली, भारत में स्कूल के पास छोटी दुकान।",
}
BUDGET = 5000.0
HORIZON = 14


def plan_checks(root: Path, stores: list[str]) -> dict:
    p = root / "data" / "processed"
    client = TestClient(create_app(default_modules(), audit_path=None))
    rows, cold, warm = [], [], []
    for sid in stores:
        data = load_store(p / "items_catalog.csv", p / "full_ml_feature_matrix.csv",
                          p / "stores_metadata.csv", store_id=sid, currency="INR")
        dj = data.model_dump(mode="json")
        lines = {}
        for lang, desc in DESCS.items():
            pid = client.post("/profile/extract", json={"description": desc}).json()["profile"]["profile_id"]
            client.post("/profile/confirm", json={"profile_id": pid, "edits": {}})
            t0 = time.perf_counter()
            r = client.post("/plan", json={"profile_id": pid, "budget": BUDGET, "horizon_days": HORIZON,
                                           "language": lang, "data": dj})
            cold.append(time.perf_counter() - t0)
            body = r.json()
            ok = r.status_code == 200 and body.get("status") == "ok"
            pl = body.get("plan") or {}
            lines[lang] = pl.get("lines")
            rows.append({"store": sid, "lang": lang, "ok": ok, "within_budget": ok and
                         pl["total_cost"] <= pl["budget"] + config.MONEY_TOLERANCE,
                         "explained": bool(body.get("explanation")),
                         "warnings": [w["code"] for w in body.get("warnings", [])]})
            t0 = time.perf_counter()  # same request again: forecast cache hit
            client.post("/plan", json={"profile_id": pid, "budget": BUDGET, "horizon_days": HORIZON,
                                       "language": lang, "data": dj})
            warm.append(time.perf_counter() - t0)
        rows[-1]["_lines_equal"] = all(v == lines["en"] for v in lines.values())
    n = len(rows)
    return {
        "plans_run": n,
        "plans_ok": sum(r["ok"] for r in rows),
        "within_budget": sum(r["within_budget"] for r in rows),
        "explanation_present": sum(r["explained"] for r in rows),
        "stores_with_identical_plan_across_languages": sum(1 for r in rows if r.get("_lines_equal")),
        "stores": len(stores),
        "cross_language_note": "mock extractor only; real extractor not tested",
        "warnings_seen": sorted({w for r in rows for w in r["warnings"]}),
        "latency_note": "mocks answer in milliseconds; these numbers say nothing about real modules",
        "latency_cold_s": {"median": round(statistics.median(cold), 3), "max": round(max(cold), 3),
                           "target": config.PLAN_LATENCY_COLD_SECONDS},
        "latency_warm_s": {"median": round(statistics.median(warm), 3), "max": round(max(warm), 3),
                           "target": config.PLAN_LATENCY_WARM_SECONDS},
    }


def backtest(root: Path, stores: list[str]) -> dict:
    """Rolling-origin, time-ordered: forecast at origin t from data <= t, score on days t+1..t+H."""
    m = default_modules()
    prof = m.extractor.extract_profile(DESCS["en"], "en")
    p = root / "data" / "processed"
    err, naive_err, hit, n, total_actual = 0.0, 0.0, 0, 0, 0.0
    for sid in stores:
        full = load_store(p / "items_catalog.csv", p / "full_ml_feature_matrix.csv",
                          p / "stores_metadata.csv", store_id=sid)
        last = full.as_of
        origin = last - dt.timedelta(days=HORIZON * 12)
        while origin + dt.timedelta(days=HORIZON) <= last:
            past = full.model_copy(update={"as_of": origin,
                                           "sales": [s for s in full.sales if s.date <= origin]})
            actual: dict[str, float] = {}
            for s in full.sales:
                if origin < s.date <= origin + dt.timedelta(days=HORIZON):
                    actual[s.product_id] = actual.get(s.product_id, 0.0) + s.units_sold
            ctx = m.context.build_context(prof, origin, HORIZON, None)
            fc = m.forecaster.forecast(past, prof, ctx, HORIZON, None)
            back = {s.product_id: 0.0 for s in past.sales}
            for s in past.sales:
                if s.date > origin - dt.timedelta(days=HORIZON):
                    back[s.product_id] += s.units_sold
            for f in fc.forecasts:
                a = actual.get(f.product_id, 0.0)
                err += abs(f.mean - a)
                naive_err += abs(back.get(f.product_id, 0.0) - a)
                hit += f.quantile(0.05) <= a <= f.quantile(0.95)
                total_actual += a
                n += 1
            origin += dt.timedelta(days=HORIZON)
    return {
        "forecasts_scored": n,
        "mae_units": round(err / n, 2),
        "naive_last_period_mae_units": round(naive_err / n, 2),
        "wape": round(err / total_actual, 4),
        "interval_90_coverage": round(hit / n, 4),
        "interval_90_target": 0.90,
        "scope": "MOCK forecaster: validates the harness, not Member 2's model",
    }


def stockout_bias(root: Path, stores: list[str]) -> dict:
    p = root / "data" / "processed"
    with_zero, without, flagged, rows = 0.0, 0.0, 0, 0
    for sid in stores:
        d = load_store(p / "items_catalog.csv", p / "full_ml_feature_matrix.csv",
                       p / "stores_metadata.csv", store_id=sid)
        q = [s.units_sold for s in d.sales]
        ok = [s.units_sold for s in d.sales if not s.stockout]
        with_zero += sum(q)
        without += sum(ok)
        flagged += sum(s.stockout for s in d.sales)
        rows += len(q)
    mean_all = with_zero / rows
    mean_ok = without / (rows - flagged)
    return {"share_of_days_flagged_stockout": round(flagged / rows, 4),
            "mean_daily_units_including_zero_days": round(mean_all, 3),
            "mean_daily_units_excluding_flagged_days": round(mean_ok, 3),
            "underestimate_if_zeros_treated_as_demand": round(1 - mean_all / mean_ok, 4),
            "note": "their rule flags every zero-sales day as a stockout, so this is an upper-bound check of "
                    "the bias they must censor, not a measured stockout rate"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("data_layer_dir")
    ap.add_argument("--out", default="reports/e2e_metrics.json")
    ap.add_argument("--stores", type=int, default=10)
    a = ap.parse_args()
    root = Path(a.data_layer_dir)
    import csv
    with open(root / "data/processed/stores_metadata.csv", newline="") as f:
        stores = [r["store_id"] for r in csv.DictReader(f)][: a.stores]
    report = {"generated": dt.date.today().isoformat(), "modules": "mocks (default_modules)",
              "horizon_days": HORIZON, "budget": BUDGET,
              "pipeline": plan_checks(root, stores),
              "backtest": backtest(root, stores[:3]),
              "stockout_bias": stockout_bias(root, stores)}
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
