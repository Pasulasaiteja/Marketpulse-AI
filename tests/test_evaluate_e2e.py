"""Smoke test for the end-to-end evaluation harness on a tiny synthetic data-layer folder."""

import datetime as dt
import random

from scripts import evaluate_e2e as ev


def make_root(tmp_path):
    d = tmp_path / "data" / "processed"
    d.mkdir(parents=True)
    (d / "items_catalog.csv").write_text(
        "item_id,category_id,cost_price,selling_price,supplier_id,lead_time_days\n"
        "ITEM_001,CAT_1,10.0,25.0,S,3\nITEM_002,CAT_2,5.0,9.0,S,7\n")
    (d / "stores_metadata.csv").write_text(
        "store_id,store_name,location_type,population_class,region_id\n"
        "STORE_001,a,rural_kiosk,low_density,ecuador\n")
    rng = random.Random(0)
    rows = ["date,store_id,item_id,sales_quantity,price,on_promotion,is_stockout"]
    for i in range(200):
        day = dt.date(2025, 1, 1) + dt.timedelta(days=i)
        for item, price in (("ITEM_001", 25.0), ("ITEM_002", 9.0)):
            q = 0.0 if rng.random() < 0.1 else float(rng.randint(5, 15))
            rows.append(f"{day},STORE_001,{item},{q},{price},False,{q == 0.0}")
    (d / "full_ml_feature_matrix.csv").write_text("\n".join(rows) + "\n")
    return tmp_path


def test_harness_reports_every_section(tmp_path):
    root = make_root(tmp_path)
    plans = ev.plan_checks(root, ["STORE_001"])
    assert plans["plans_run"] == plans["plans_ok"] == plans["within_budget"] == 4
    assert plans["stores_with_identical_plan_across_languages"] == 1
    bt = ev.backtest(root, ["STORE_001"])
    assert bt["forecasts_scored"] > 0 and 0 <= bt["interval_90_coverage"] <= 1
    assert "MOCK" in bt["scope"]
    so = ev.stockout_bias(root, ["STORE_001"])
    assert 0.05 < so["share_of_days_flagged_stockout"] < 0.2
    assert so["mean_daily_units_excluding_flagged_days"] > so["mean_daily_units_including_zero_days"]
