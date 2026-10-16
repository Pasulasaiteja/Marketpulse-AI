"""
Tests for Baseline Replenishment Policy (Task A)
"""
import pytest
from optimizer.models import Forecast, InventoryState, ProductMeta
from optimizer.baseline import compute_baseline_quantity, compute_safety_stock


def test_baseline_known_values_unscaled():
    """
    Test standard unscaled baseline formula:
    D = 100, SS = 20, I = 30, P = 10 -> Q = 100 + 20 - 30 - 10 = 80
    """
    forecast = Forecast(p10=80, p50=100, p90=120, mean=100.0, std=12.16, horizon_days=14)
    # std=12.16, with z=1.6447 -> SS ≈ 20.0
    inventory = InventoryState(on_hand=30, on_order=10, expired_stock=0, days_to_next_replenishment=14)
    product = ProductMeta(product_id="TEST_1", name="Test Item", purchase_price=10.0, selling_price=15.0, lead_time_days=0)

    # Force exact SS calculation by choosing z
    z = 20.0 / 12.16
    qty, details = compute_baseline_quantity(
        forecast=forecast,
        inventory=inventory,
        product=product,
        service_factor_z=z,
        scale_to_protection_interval=False
    )
    assert qty == 80
    assert details["final_baseline_quantity"] == 80
    assert details["forecast_demand_D"] == 100.0
    assert details["usable_inventory_I"] == 30
    assert details["on_order_inventory_P"] == 10


def test_baseline_never_negative_on_excess_inventory():
    """
    When existing inventory exceeds target, order quantity must be 0, never negative.
    """
    forecast = Forecast(p10=20, p50=30, p90=40, mean=30.0, std=7.8, horizon_days=14)
    inventory = InventoryState(on_hand=200, on_order=50, expired_stock=0)
    product = ProductMeta(product_id="TEST_2", name="Excess Item", purchase_price=5.0, selling_price=10.0)

    qty, details = compute_baseline_quantity(forecast, inventory, product)
    assert qty == 0
    assert details["raw_order_quantity"] < 0
    assert details["final_baseline_quantity"] == 0


def test_baseline_excludes_expired_inventory():
    """
    Damaged/expired stock must NOT count as usable inventory.
    If on_hand=50, expired=30, usable=20.
    """
    forecast = Forecast(p10=40, p50=50, p90=60, mean=50.0, std=5.0, horizon_days=14)
    inventory_with_expired = InventoryState(on_hand=50, on_order=0, expired_stock=30, days_to_next_replenishment=14)
    product = ProductMeta(product_id="TEST_3", name="Perishable Item", purchase_price=2.0, selling_price=4.0, lead_time_days=0)

    qty_expired, details_expired = compute_baseline_quantity(
        forecast, inventory_with_expired, product, service_factor_z=1.0, scale_to_protection_interval=False
    )
    # Target = D (50) + SS (5) = 55. Usable = 50 - 30 = 20. Order = 55 - 20 = 35.
    assert details_expired["usable_inventory_I"] == 20
    assert qty_expired == 35


def test_baseline_accounts_for_on_order():
    """
    Inventory already ordered must reduce new orders.
    """
    forecast = Forecast(p10=40, p50=50, p90=60, mean=50.0, std=5.0, horizon_days=14)
    inv_no_order = InventoryState(on_hand=20, on_order=0, expired_stock=0, days_to_next_replenishment=14)
    inv_with_order = InventoryState(on_hand=20, on_order=15, expired_stock=0, days_to_next_replenishment=14)
    product = ProductMeta(product_id="TEST_4", name="Standard Item", purchase_price=3.0, selling_price=5.0, lead_time_days=0)

    qty_1, _ = compute_baseline_quantity(forecast, inv_no_order, product, service_factor_z=1.0, scale_to_protection_interval=False)
    qty_2, _ = compute_baseline_quantity(forecast, inv_with_order, product, service_factor_z=1.0, scale_to_protection_interval=False)

    assert qty_1 - qty_2 == 15


def test_baseline_scales_with_lead_time():
    """
    Longer lead time increases protection interval and safety stock.
    """
    forecast = Forecast(p10=70, p50=100, p90=130, mean=100.0, std=23.4, horizon_days=14)
    inventory = InventoryState(on_hand=0, on_order=0, days_to_next_replenishment=7)
    
    prod_short_lt = ProductMeta(product_id="P_SHORT", name="Local Supplier", lead_time_days=1)
    prod_long_lt = ProductMeta(product_id="P_LONG", name="Overseas Supplier", lead_time_days=7)

    qty_short, details_short = compute_baseline_quantity(forecast, inventory, prod_short_lt)
    qty_long, details_long = compute_baseline_quantity(forecast, inventory, prod_long_lt)

    # Protection days: short = 1 + 7 = 8 days. long = 7 + 7 = 14 days.
    assert details_long["safety_stock_SS"] > details_short["safety_stock_SS"]
    assert qty_long > qty_short
