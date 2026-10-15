"""Adapter for Member 1's data layer. Uses tiny fixtures; the real files are checked if present."""

import os
from pathlib import Path

import pytest

from marketpulse.adapters.data_layer import DataLayerError, load_all_stores, load_store

ITEMS = "item_id,category_id,cost_price,selling_price,supplier_id,lead_time_days\n" \
        "ITEM_001,CAT_1,10.0,25.0,S_A,3\nITEM_002,CAT_2,5.0,9.0,S_B,7\n"
SALES = ("date,store_id,item_id,sales_quantity,price,on_promotion\n"
         "2025-01-01,STORE_001,ITEM_001,4.0,25.0,False\n2025-01-01,STORE_001,ITEM_002,0.0,9.0,False\n"
         "2025-01-02,STORE_001,ITEM_001,6.0,25.0,True\n2025-01-02,STORE_002,ITEM_001,9.0,25.0,False\n")
STORES = ("store_id,store_name,location_type,population_class,region_id\n"
          "STORE_001,a,rural_kiosk,low_density,ecuador\nSTORE_002,b,urban_flagship,high_density,south_asia\n")


@pytest.fixture
def files(tmp_path):
    for n, c in (("items.csv", ITEMS), ("sales.csv", SALES), ("stores.csv", STORES)):
        (tmp_path / n).write_text(c)
    return tmp_path / "items.csv", tmp_path / "sales.csv", tmp_path / "stores.csv"


def test_maps_one_store_to_the_contract(files):
    i, s, st = files
    d = load_store(i, s, st, store_id="STORE_001")
    assert d.shop_id == "STORE_001" and d.currency == "USD" and str(d.as_of) == "2025-01-02"
    assert len(d.sales) == 3  # the other store's row is not mixed in
    p = {x.product_id: x for x in d.products}
    assert p["ITEM_001"].unit_cost == 10.0 and p["ITEM_001"].lead_time_days == 3
    assert p["ITEM_001"].category == "CAT_1"
    r = next(x for x in d.sales if x.product_id == "ITEM_001" and x.units_sold == 6)
    assert r.revenue == 150.0


def test_zero_sales_is_flagged_as_stockout_by_their_rule_and_can_be_turned_off(files):
    i, s, st = files
    z = next(x for x in load_store(i, s, st, store_id="STORE_001").sales if x.product_id == "ITEM_002")
    assert z.stockout is True
    z = next(x for x in load_store(i, s, st, store_id="STORE_001", zero_is_stockout=False).sales
             if x.product_id == "ITEM_002")
    assert z.stockout is False


def test_explicit_stockout_column_wins(files, tmp_path):
    i, _, st = files
    f = tmp_path / "m.csv"
    f.write_text("date,store_id,item_id,sales_quantity,price,is_stockout\n"
                 "2025-01-01,STORE_001,ITEM_001,0.0,25.0,False\n")
    assert load_store(i, f, st).sales[0].stockout is False


def test_region_sets_currency_and_override_works(files):
    i, s, st = files
    assert load_store(i, s, st, store_id="STORE_002").currency == "INR"
    assert load_store(i, s, st, store_id="STORE_002", currency="PKR").currency == "PKR"


def test_multi_store_needs_a_choice_and_bad_input_is_explained(files, tmp_path):
    i, s, st = files
    with pytest.raises(DataLayerError, match="pass store_id"):
        load_store(i, s, st)
    with pytest.raises(DataLayerError, match="not in sales"):
        load_store(i, s, st, store_id="NOPE")
    bad = tmp_path / "bad.csv"
    bad.write_text("date,store_id\n2025-01-01,STORE_001\n")
    with pytest.raises(DataLayerError, match="missing columns"):
        load_store(i, bad, st, store_id="STORE_001")
    unk = tmp_path / "unk.csv"
    unk.write_text("date,store_id,item_id,sales_quantity,price\n2025-01-01,STORE_001,ITEM_999,1,2\n")
    with pytest.raises(DataLayerError, match="missing from items"):
        load_store(i, unk, st, store_id="STORE_001")


def test_load_all_stores_keeps_stores_apart_and_uses_each_region(files):
    i, s, st = files
    out = load_all_stores(i, s, st)
    assert set(out) == {"STORE_001", "STORE_002"}
    assert len(out["STORE_001"].sales) == 3 and len(out["STORE_002"].sales) == 1
    assert out["STORE_001"].currency == "USD" and out["STORE_002"].currency == "INR"


REAL = os.environ.get("MP_DATA_LAYER_DIR")


@pytest.mark.skipif(not REAL, reason="set MP_DATA_LAYER_DIR to the data layer repo to run")
def test_real_data_layer_files_load_and_plan():
    root = Path(REAL) / "data" / "processed"
    d = load_store(root / "items_catalog.csv", root / "full_ml_feature_matrix.csv",
                   root / "stores_metadata.csv", store_id="STORE_001")
    assert len(d.products) == 20 and len(d.sales) == 7300 and d.currency == "INR"
