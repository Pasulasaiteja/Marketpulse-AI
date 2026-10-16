"""Deterministic synthetic shop used by mocks, tests and the fallback demo.

SYNTHETIC DATA: invented for development; not real retailer data.
"""

from __future__ import annotations

import datetime as dt
import random

from marketpulse.contracts.models import CanonicalData, Product, SalesRecord

FIXTURE_AS_OF = dt.date(2026, 10, 12)
SEED = 42  # fixed for reproducibility
PRICE_SCALE = 10  # ASSUMPTION: scales invented prices so a 5,000 budget is binding
CURRENCY = "INR"

# (id, name, category, cost, price, base daily demand, stock, moq)
_PRODUCTS = [
    ("P001", "Rice 5kg", "grocery", 6.0, 8.0, 6.0, 40, 10),
    ("P002", "Cooking oil 1L", "grocery", 2.5, 3.5, 9.0, 30, 12),
    ("P003", "Notebook A5", "stationery", 0.6, 1.2, 12.0, 80, 50),
    ("P004", "Phone airtime card", "services", 0.9, 1.0, 20.0, 0, 20),
    ("P005", "Laundry soap", "household", 0.8, 1.4, 7.0, 25, 24),
    ("P006", "Bottled water 1.5L", "grocery", 0.5, 0.9, 25.0, 60, 24),
]


def make_canonical_data(days: int = 120, as_of: dt.date = FIXTURE_AS_OF, *, seed: int = SEED,
                        demand_scale: float = 1.0, shop_id: str = "demo-shop") -> CanonicalData:
    rng = random.Random(seed)
    products = [
        Product(
            product_id=pid,
            name=name,
            category=cat,
            unit_cost=round(cost * PRICE_SCALE, 2),
            unit_price=round(price * PRICE_SCALE, 2),
            current_stock=stock,
            on_order=0,
            lead_time_days=3,
            min_order_qty=moq,
        )
        for pid, name, cat, cost, price, _d, stock, moq in _PRODUCTS
    ]
    sales: list[SalesRecord] = []
    for i in range(days):
        day = as_of - dt.timedelta(days=days - 1 - i)
        weekend = 1.25 if day.weekday() >= 5 else 1.0
        for pid, _n, _c, _co, price, base, _s, _m in _PRODUCTS:
            units = max(0, round(rng.gauss(base * demand_scale * weekend, base * demand_scale * 0.3)))
            sales.append(SalesRecord(date=day, product_id=pid, units_sold=units,
                                     revenue=round(units * price * PRICE_SCALE, 2)))
    return CanonicalData(
        shop_id=shop_id,
        currency=CURRENCY,
        as_of=as_of,
        storage_capacity_units=None,
        products=products,
        sales=sales,
    )


# ASSUMPTION: three invented stores with different demand levels, to demo and test multi-store use.
DEMO_STORES = (("store-a", 1.0, 42), ("store-b", 0.5, 7), ("store-c", 1.8, 99))


def make_demo_chain(days: int = 120) -> dict[str, CanonicalData]:
    return {sid: make_canonical_data(days, seed=seed, demand_scale=scale, shop_id=sid)
            for sid, scale, seed in DEMO_STORES}
