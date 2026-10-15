"""Retailer CSV -> CanonicalData.

Products CSV columns (required first four):
  product_id,name,unit_cost,unit_price[,current_stock,on_order,lead_time_days,
  min_order_qty,category,shelf_life_days,storage_units]
Sales CSV columns: date,product_id,units_sold[,revenue,stockout]
A day with no sales row is passed through as missing (the forecaster decides;
see CONTRACT.md Q-C).
"""

from __future__ import annotations

import csv
import datetime as dt
import io

from pydantic import ValidationError

from marketpulse.contracts.models import CanonicalData, Product, SalesRecord


class CsvError(ValueError):
    """Raised with a row-level message the retailer can act on."""


def dump_csv(data: CanonicalData) -> tuple[str, str]:
    """CanonicalData -> (products_csv, sales_csv) in the formats ``load_canonical_data`` reads."""
    p, q = io.StringIO(), io.StringIO()
    pw = csv.writer(p, lineterminator="\n")
    pw.writerow(["product_id", "name", "unit_cost", "unit_price", "current_stock", "on_order",
                 "lead_time_days", "min_order_qty", "category"])
    for x in data.products:
        pw.writerow([x.product_id, x.name, x.unit_cost, x.unit_price, x.current_stock, x.on_order,
                     x.lead_time_days, x.min_order_qty, x.category or ""])
    qw = csv.writer(q, lineterminator="\n")
    qw.writerow(["date", "product_id", "units_sold", "revenue", "stockout"])
    for r in data.sales:
        qw.writerow([r.date.isoformat(), r.product_id, r.units_sold,
                     "" if r.revenue is None else r.revenue, str(r.stockout).lower()])
    return p.getvalue(), q.getvalue()


def _rows(text: str, required: list[str], label: str) -> list[tuple[int, dict[str, str]]]:
    reader = csv.DictReader(io.StringIO(text.strip()))
    cols = [c.strip().lower() for c in (reader.fieldnames or [])]
    missing = [c for c in required if c not in cols]
    if missing:
        raise CsvError(f"{label} CSV is missing column(s): {', '.join(missing)}")
    out = []
    for n, raw in enumerate(reader, start=2):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        if any(row.values()):
            out.append((n, row))
    if not out:
        raise CsvError(f"{label} CSV has no data rows")
    return out


def _num(row: dict[str, str], key: str, n: int, label: str, default: float | None = None) -> float:
    raw = row.get(key, "")
    if raw == "":
        if default is None:
            raise CsvError(f"{label} CSV row {n}: '{key}' is required")
        return default
    try:
        return float(raw.replace(",", ""))
    except ValueError as exc:
        raise CsvError(f"{label} CSV row {n}: '{key}' is not a number ({raw!r})") from exc


def load_canonical_data(
    products_csv: str,
    sales_csv: str,
    *,
    shop_id: str,
    currency: str,
    as_of: dt.date | None = None,
    storage_capacity_units: float | None = None,
) -> CanonicalData:
    products = []
    for n, r in _rows(products_csv, ["product_id", "name", "unit_cost", "unit_price"], "products"):
        try:
            products.append(
                Product(
                    product_id=r["product_id"],
                    name=r["name"],
                    category=r.get("category") or None,
                    unit_cost=_num(r, "unit_cost", n, "products"),
                    unit_price=_num(r, "unit_price", n, "products"),
                    current_stock=_num(r, "current_stock", n, "products", 0.0),
                    on_order=_num(r, "on_order", n, "products", 0.0),
                    lead_time_days=int(_num(r, "lead_time_days", n, "products", 0)),
                    min_order_qty=int(_num(r, "min_order_qty", n, "products", 1)),
                    shelf_life_days=int(r["shelf_life_days"]) if r.get("shelf_life_days") else None,
                    storage_units=_num(r, "storage_units", n, "products", 1.0),
                )
            )
        except ValidationError as exc:
            raise CsvError(f"products CSV row {n}: {exc.errors()[0]['msg']}") from exc
    sales = []
    for n, r in _rows(sales_csv, ["date", "product_id", "units_sold"], "sales"):
        try:
            day = dt.date.fromisoformat(r["date"])
        except ValueError as exc:
            raise CsvError(f"sales CSV row {n}: date must be YYYY-MM-DD ({r['date']!r})") from exc
        try:
            sales.append(
                SalesRecord(
                    date=day,
                    product_id=r["product_id"],
                    units_sold=_num(r, "units_sold", n, "sales"),
                    revenue=_num(r, "revenue", n, "sales", -1) if r.get("revenue") else None,
                    stockout=r.get("stockout", "").lower() in {"1", "true", "yes"},
                )
            )
        except ValidationError as exc:
            raise CsvError(f"sales CSV row {n}: {exc.errors()[0]['msg']}") from exc
    last = max(s.date for s in sales)
    try:
        return CanonicalData(
            shop_id=shop_id,
            currency=currency,
            as_of=as_of or last,
            storage_capacity_units=storage_capacity_units,
            products=products,
            sales=sales,
        )
    except ValidationError as exc:
        raise CsvError(exc.errors()[0]["msg"].replace("Value error, ", "")) from exc


def dump_stores_csv(stores: dict[str, CanonicalData]) -> tuple[str, str]:
    """Several stores -> (products_csv, sales_csv) where both carry a ``store_id`` column."""
    p, q = io.StringIO(), io.StringIO()
    pw, qw = csv.writer(p, lineterminator="\n"), csv.writer(q, lineterminator="\n")
    pw.writerow(["store_id", "product_id", "name", "unit_cost", "unit_price", "current_stock", "on_order",
                 "lead_time_days", "min_order_qty", "category"])
    qw.writerow(["store_id", "date", "product_id", "units_sold", "revenue", "stockout"])
    for sid, data in stores.items():
        for x in data.products:
            pw.writerow([sid, x.product_id, x.name, x.unit_cost, x.unit_price, x.current_stock, x.on_order,
                         x.lead_time_days, x.min_order_qty, x.category or ""])
        for r in data.sales:
            qw.writerow([sid, r.date.isoformat(), r.product_id, r.units_sold,
                         "" if r.revenue is None else r.revenue, str(r.stockout).lower()])
    return p.getvalue(), q.getvalue()


def has_store_column(sales_csv: str) -> bool:
    head = sales_csv.strip().splitlines()[0] if sales_csv.strip() else ""
    return "store_id" in [c.strip().lower() for c in head.split(",")]


def _csv_text(header: list[str], rows: list[dict[str, str]]) -> str:
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(header)
    for r in rows:
        w.writerow([r.get(h, "") for h in header])
    return out.getvalue()


def load_canonical_stores(products_csv: str, sales_csv: str, *, currency: str,
                          as_of: dt.date | None = None) -> dict[str, CanonicalData]:
    """Multi-store CSVs -> one CanonicalData per store (``shop_id`` = ``store_id``).

    Sales CSV must have a ``store_id`` column. Products CSV may have one too: a row with a
    store_id applies to that store only (e.g. its own stock level); a row with it blank, or a
    products CSV without the column, is shared by every store. Stores never see each other's sales.
    """
    sales = _rows(sales_csv, ["store_id", "date", "product_id", "units_sold"], "sales")
    prods = _rows(products_csv, ["product_id", "name", "unit_cost", "unit_price"], "products")
    s_head = [c.strip().lower() for c in sales_csv.strip().splitlines()[0].split(",")]
    p_head = [c.strip().lower() for c in products_csv.strip().splitlines()[0].split(",")]
    by_store: dict[str, list[dict[str, str]]] = {}
    for n, r in sales:
        if not r["store_id"]:
            raise CsvError(f"sales CSV row {n}: 'store_id' is required")
        by_store.setdefault(r["store_id"], []).append(r)
    out = {}
    for sid, rows in by_store.items():
        mine = [r for _n, r in prods if r.get("store_id", "") in ("", sid)]
        seen: dict[str, dict[str, str]] = {}
        for r in mine:  # a store-specific row overrides a shared row for the same product
            if r["product_id"] not in seen or r.get("store_id"):
                seen[r["product_id"]] = r
        out[sid] = load_canonical_data(
            _csv_text([h for h in p_head if h != "store_id"], list(seen.values())),
            _csv_text([h for h in s_head if h != "store_id"], rows),
            shop_id=sid, currency=currency, as_of=as_of)
    return out
