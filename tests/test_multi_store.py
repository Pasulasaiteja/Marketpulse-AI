"""Multi-store support: one pair of CSVs, one dataset per store, stores never mix."""

import pytest
from fastapi.testclient import TestClient

from marketpulse.api.app import create_app
from marketpulse.csvloader import CsvError, dump_stores_csv, has_store_column, load_canonical_stores
from marketpulse.mocks.fixtures import make_demo_chain

DESC = "Small shop near a school in Delhi, India."


@pytest.fixture
def chain():
    return make_demo_chain()


@pytest.fixture
def client():
    return TestClient(create_app(audit_path=None))


def profile(c):
    pid = c.post("/profile/extract", json={"description": DESC}).json()["profile"]["profile_id"]
    assert c.post("/profile/confirm", json={"profile_id": pid, "edits": {}}).json()["status"] == "confirmed"
    return pid


def register(c, pid, chain):
    products, sales = dump_stores_csv(chain)
    return c.post("/stores", json={"profile_id": pid, "products_csv": products, "sales_csv": sales}).json()


def test_csv_roundtrip_gives_one_independent_dataset_per_store(chain):
    products, sales = dump_stores_csv(chain)
    assert has_store_column(sales)
    back = load_canonical_stores(products, sales, currency="INR")
    assert set(back) == set(chain)
    for sid, d in back.items():
        assert d.shop_id == sid
        assert len(d.sales) == len(chain[sid].sales)
        assert sum(s.units_sold for s in d.sales) == sum(s.units_sold for s in chain[sid].sales)


def test_store_specific_product_row_overrides_the_shared_row(chain):
    products, sales = dump_stores_csv(chain)
    lines = products.strip().splitlines()
    shared = [ln.split(",", 1)[1] for ln in lines[1:] if ln.startswith("store-a,")]
    # shared (blank store) rows for everyone, plus one store-b override with different stock
    head = lines[0]
    rows = [head] + [f",{r}" for r in shared]
    first = shared[0].split(",")
    first[4] = "999"  # current_stock column
    rows.append("store-b," + ",".join(first))
    out = load_canonical_stores("\n".join(rows) + "\n", sales, currency="INR")
    pid = first[0]
    stock = {sid: next(p for p in d.products if p.product_id == pid).current_stock for sid, d in out.items()}
    assert stock["store-b"] == 999 and stock["store-a"] != 999 and stock["store-c"] != 999


def test_missing_store_column_is_a_clear_error(chain):
    products, sales = dump_stores_csv(chain)
    no_store = "\n".join(",".join(ln.split(",")[1:]) for ln in sales.strip().splitlines())
    with pytest.raises(CsvError, match="store_id"):
        load_canonical_stores(products, no_store, currency="INR")


def test_stores_endpoint_registers_each_store(client, chain):
    pid = profile(client)
    products, sales = dump_stores_csv(chain)
    r = client.post("/stores", json={"profile_id": pid, "products_csv": products, "sales_csv": sales}).json()
    assert r["status"] == "ok" and r["currency"] == "INR"
    assert [s["store_id"] for s in r["stores"]] == ["store-a", "store-b", "store-c"]
    assert len({s["dataset_id"] for s in r["stores"]}) == 3
    assert all(s["history_days"] == 120 for s in r["stores"])


def test_each_stores_plan_uses_only_its_own_sales(client, chain):
    pid = profile(client)
    reg = register(client, pid, chain)
    mean_fc = {}
    for s in reg["stores"]:
        r = client.post("/plan", json={"profile_id": pid, "budget": 5000,
                                       "dataset_id": s["dataset_id"]}).json()
        assert r["status"] == "ok" and r["dataset_id"] == s["dataset_id"]
        mean_fc[s["store_id"]] = r["forecast"]["forecasts"][0]["mean"]
    # store-b sells about half, store-c about 1.8x, of store-a: forecasts follow each store's own data
    assert mean_fc["store-b"] < mean_fc["store-a"] < mean_fc["store-c"]
    # and the plan for a store equals the plan from that store's data posted on its own
    one = client.post("/plan", json={"profile_id": pid, "budget": 5000,
                                     "data": chain["store-c"].model_dump(mode="json")}).json()
    via = client.post("/plan", json={"profile_id": pid, "budget": 5000,
                                     "dataset_id": reg["stores"][2]["dataset_id"]}).json()
    assert one["plan"]["lines"] == via["plan"]["lines"]


def test_opportunities_work_per_store(client, chain):
    pid = profile(client)
    reg = register(client, pid, chain)
    r = client.post("/opportunities", json={"profile_id": pid, "budget": 5000,
                                            "dataset_id": reg["stores"][1]["dataset_id"]})
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_stores_endpoint_errors(client, chain):
    products, sales = dump_stores_csv(chain)
    r = client.post("/stores", json={"profile_id": "nope", "products_csv": products, "sales_csv": sales})
    assert r.status_code == 404
    pid = profile(client)
    r = client.post("/stores", json={"profile_id": pid, "products_csv": products,
                                     "sales_csv": "date,product_id,units_sold\n2026-01-01,P001,1\n"})
    assert r.status_code == 422 and "store_id" in r.text


def test_demo_chain_endpoint(client):
    r = client.get("/demo/chain").json()
    assert r["synthetic"] is True and has_store_column(r["sales_csv"])


# --------------------------------------------------------------- chain-wide view
def test_chain_plan_totals_each_store_independently(client, chain):
    pid = profile(client)
    reg = register(client, pid, chain)
    ids = [s["dataset_id"] for s in reg["stores"]]
    r = client.post("/chain/plan", json={"profile_id": pid, "budget": 5000, "dataset_ids": ids})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["allocation"] == "independent"
    assert body["currency"] == "INR"
    assert body["chain"]["stores_planned"] == 3 and body["chain"]["stores_failed"] == 0
    assert body["failures"] == [] and body["warnings"] == []
    # every store's share of the chain equals that store's own /plan
    per = {}
    for s in body["stores"]:
        one = client.post("/plan", json={"profile_id": pid, "budget": 5000,
                                         "dataset_id": s["dataset_id"]}).json()
        assert s["plan"] == one["plan"]
        per[s["dataset_id"]] = one["plan"]["total_cost"]
    assert body["chain"]["total_cost"] == round(sum(per.values()), 2)
    assert body["chain"]["total_budget"] == 15000.0
    assert body["chain"]["total_cost"] <= body["chain"]["total_budget"]
    assert body["chain"]["capital_utilization"] == round(
        body["chain"]["total_cost"] / body["chain"]["total_budget"], 4)


def test_chain_plan_honours_per_store_budgets(client, chain):
    pid = profile(client)
    reg = register(client, pid, chain)
    ids = [s["dataset_id"] for s in reg["stores"]]
    budgets = {ids[0]: 1000, ids[1]: 2000, ids[2]: 3000}
    body = client.post("/chain/plan", json={"profile_id": pid, "budget": 5000, "dataset_ids": ids,
                                            "store_budgets": budgets}).json()
    assert {s["dataset_id"]: s["budget"] for s in body["stores"]} == budgets
    assert body["chain"]["total_budget"] == 6000.0
    for s in body["stores"]:
        assert s["plan"]["total_cost"] <= budgets[s["dataset_id"]]


def test_chain_plan_reports_a_dead_store_and_still_plans_the_rest(client, chain):
    pid = profile(client)
    reg = register(client, pid, chain)
    ids = [s["dataset_id"] for s in reg["stores"]] + ["ds-nope"]
    body = client.post("/chain/plan", json={"profile_id": pid, "budget": 5000,
                                            "dataset_ids": ids}).json()
    assert body["status"] == "ok" and body["chain"]["stores_planned"] == 3
    assert body["chain"]["stores_failed"] == 1
    assert [f["code"] for f in body["failures"]] == ["DATASET_NOT_FOUND"]
    assert "STORE_FAILED" in {w["code"] for w in body["warnings"]}


def test_chain_plan_when_no_store_can_be_planned_is_an_honest_error(client, chain):
    pid = profile(client)
    r = client.post("/chain/plan", json={"profile_id": pid, "budget": 5000,
                                         "dataset_ids": ["nope"]})
    assert r.status_code == 502
    assert r.json()["error"]["code"] == "MODULE_FAILED"


def test_chain_plan_input_validation(client, chain):
    pid = profile(client)
    assert client.post("/chain/plan", json={"profile_id": pid, "budget": 5000,
                                            "dataset_ids": []}).status_code == 422
    reg = register(client, pid, chain)
    ids = [s["dataset_id"] for s in reg["stores"]]
    assert client.post("/chain/plan", json={"profile_id": pid, "budget": 0,
                                            "dataset_ids": ids}).status_code == 422
    assert client.post("/chain/plan", json={"profile_id": pid, "budget": 5000,
                                            "horizon_days": 5, "dataset_ids": ids}).status_code == 422
    assert client.post("/chain/plan", json={"profile_id": "nope", "budget": 5,
                                            "dataset_ids": ids}).status_code == 404


def test_chain_plan_rejects_mixed_currencies(chain):
    from marketpulse.audit import AuditLog
    from marketpulse.registry import mock_modules
    from marketpulse.service import ApiError, DecisionService

    svc = DecisionService(mock_modules(), AuditLog(None))
    pid = svc.extract_profile(DESC)["profile"]["profile_id"]
    svc.confirm_profile(pid, {})
    svc.datasets["ds-inr"] = chain["store-a"]
    svc.datasets["ds-usd"] = chain["store-b"].model_copy(update={"currency": "USD"})
    with pytest.raises(ApiError) as exc:
        svc.chain_plan({"profile_id": pid, "budget": 1000, "dataset_ids": ["ds-inr", "ds-usd"]})
    assert exc.value.code == "MIXED_CURRENCY"
