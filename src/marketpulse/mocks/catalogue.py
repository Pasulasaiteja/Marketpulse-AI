"""SAMPLE supplier catalogue for Component D.

SYNTHETIC / INVENTED: not real products, prices or suppliers. Prices are on the same scale as the
synthetic demo shop in ``fixtures.py`` (INR). Each row exercises a different code path:

  C01 juice      hypothesized, one weak comparable, signals present but not validated
  C02 biscuits   observed (14 customer requests)
  C03 tea        hypothesized, two strong comparables (same category)
  C04 cable      hypothesized, one comparable, competition unknown
  C05 school bag excluded: no comparable at a similar price
  C06 sanitizer  observed, only 3 requests (wide interval), competition unknown
  C07 chocolate  hypothesized, thin margin
  C08 rice 5kg   excluded: already stocked
  C09 lamp       excluded: supplier cannot supply
"""

from __future__ import annotations

from marketpulse.contracts.models import CatalogueItem, RequestStats

SOURCE = "SYNTHETIC sample catalogue (invented)"


def sample_catalogue() -> list[CatalogueItem]:
    def item(item_id, name, category, cost, price, moq, sellers, requests=None, available=True):
        return CatalogueItem(
            item_id=item_id, name=name, category=category, unit_cost=cost, unit_price=price,
            supplier_min_order_qty=moq, sellers_count=sellers, requests=requests,
            supplier_available=available, source=SOURCE,
        )

    return [
        item("C01", "Fruit juice 1L", "beverages", 30, 45, 12, 6),
        item("C02", "Biscuits pack", "snacks", 10, 15, 48, 9,
             RequestStats(count=14, window_days=28, source="customer requests notebook (sample)")),
        item("C03", "Tea 250g", "grocery", 42, 60, 10, 4),
        item("C04", "Phone charging cable", "electronics", 70, 120, 6, None),
        item("C05", "School bag", "stationery", 160, 250, 5, 3),
        item("C06", "Hand sanitizer 100ml", "health", 25, 40, 12, None,
             RequestStats(count=3, window_days=28, source="customer requests notebook (sample)")),
        item("C07", "Premium chocolate bar", "snacks", 90, 100, 10, 5),
        item("C08", "Rice 5kg", "grocery", 60, 80, 10, 8),
        item("C09", "Desk lamp", "household", 120, 180, 4, 2, available=False),
    ]
