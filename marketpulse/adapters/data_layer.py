"""Member 1 data layer (Akhtarali446/MarketPulse-AI) -> CanonicalData for ONE store.

Their tables: items(item_id, category_id, cost_price, selling_price[, supplier_id, lead_time_days]),
sales(date, store_id, item_id, sales_quantity, price, on_promotion[, is_stockout, ...]) and
stores(store_id, ..., region_id). Ours is a single shop, so the caller picks a store.

Mapping (every choice that is not a rename is listed here and in CONTRACT.md):
  item_id -> product_id; name = item_id (they have no names); category_id -> category
  cost_price/selling_price -> unit_cost/unit_price; lead_time_days copied (default 0)
  sales_quantity -> units_sold; revenue = sales_quantity * price
  stockout = their is_stockout column if present, else (units_sold == 0) when zero_is_stockout.
    CAVEAT: "zero sales == stockout" is THEIR rule; it cannot tell "out of stock" from "nobody
    wanted it". We pass it on so the forecaster can treat those days as censored rather than as
    zero demand. Whether the rule is right is their decision, not ours.
  currency = REGION_CURRENCY[region_id] (ASSUMPTION, overridable); min_order_qty = 1 and
  current_stock = 0 (ASSUMPTIONS: their data has neither).
"""

from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

from marketpulse.contracts.models import CanonicalData, Product, SalesRecord

# ASSUMPTION (hand-set): region -> currency. Ecuador uses the US dollar; "south_asia" spans several
# currencies (their fixture mentions Lahore), so INR is a placeholder the caller should override.
REGION_CURRENCY = {"south_asia": "INR", "ecuador": "USD"}
DEFAULT_CURRENCY = "USD"
DEFAULT_MIN_ORDER_QTY = 1  # ASSUMPTION: their items table has no supplier minimum.


class DataLayerError(ValueError):
    pass


def _rows(path: str | Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _need(rows: list[dict], cols: list[str], what: str) -> None:
    if not rows:
        raise DataLayerError(f"{what} is empty")
    missing = [c for c in cols if c not in rows[0]]
    if missing:
        raise DataLayerError(f"{what} is missing columns {missing}")


def load_store(items_csv: str | Path, sales_csv: str | Path, stores_csv: str | Path | None = None, *,
               store_id: str | None = None, currency: str | None = None,
               zero_is_stockout: bool = True) -> CanonicalData:
    items = _rows(items_csv)
    _need(items, ["item_id", "category_id", "cost_price", "selling_price"], "items file")
    sales = _rows(sales_csv)
    _need(sales, ["date", "store_id", "item_id", "sales_quantity", "price"], "sales file")

    stores = sorted({r["store_id"] for r in sales})
    if store_id is None:
        if len(stores) != 1:
            raise DataLayerError(f"sales has {len(stores)} stores; pass store_id (one of {stores[:5]}...)")
        store_id = stores[0]
    if store_id not in stores:
        raise DataLayerError(f"store_id {store_id!r} not in sales")

    region = None
    if stores_csv is not None:
        meta = {r["store_id"]: r for r in _rows(stores_csv)}
        region = meta.get(store_id, {}).get("region_id")
    cur = currency or REGION_CURRENCY.get(region or "", DEFAULT_CURRENCY)

    known = {r["item_id"] for r in items}
    products = [Product(product_id=r["item_id"], name=r["item_id"], category=r["category_id"],
                        unit_cost=float(r["cost_price"]), unit_price=float(r["selling_price"]),
                        lead_time_days=int(float(r.get("lead_time_days") or 0)),
                        min_order_qty=DEFAULT_MIN_ORDER_QTY) for r in items]
    recs, last = [], None
    for r in sales:
        if r["store_id"] != store_id:
            continue
        if r["item_id"] not in known:
            raise DataLayerError(f"sales row references item {r['item_id']!r} missing from items file")
        day = dt.date.fromisoformat(r["date"][:10])
        qty = float(r["sales_quantity"])
        if r.get("is_stockout") not in (None, ""):
            so = r["is_stockout"].strip().lower() == "true"
        else:
            so = zero_is_stockout and qty == 0
        recs.append(SalesRecord(date=day, product_id=r["item_id"], units_sold=qty,
                                revenue=round(qty * float(r["price"]), 2), stockout=so))
        last = day if last is None or day > last else last
    recs.sort(key=lambda s: (s.date, s.product_id))
    return CanonicalData(shop_id=store_id, currency=cur, as_of=last, products=products, sales=recs)


def load_all_stores(items_csv: str | Path, sales_csv: str | Path, stores_csv: str | Path | None = None, *,
                    currency: str | None = None, zero_is_stockout: bool = True) -> dict[str, CanonicalData]:
    """Every store in Member 1's sales file, one CanonicalData each (stores never share rows)."""
    ids = sorted({r["store_id"] for r in _rows(sales_csv)})
    return {sid: load_store(items_csv, sales_csv, stores_csv, store_id=sid, currency=currency,
                            zero_is_stockout=zero_is_stockout) for sid in ids}
