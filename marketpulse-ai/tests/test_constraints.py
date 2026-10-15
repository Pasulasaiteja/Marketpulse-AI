"""
Tests for Constraint Enforcement (Task C)
"""
import pytest
from optimizer.models import Forecast, InventoryState, ProductMeta
from optimizer.constraints import (
    enforce_pack_and_moq,
    compute_expiry_shelf_life_cap,
    check_storage_capacity,
    apply_product_level_constraints
)


def test_moq_and_pack_size_rounding():
    """
    Test that quantities below MOQ are promoted or dropped,
    and rounded to integer multiples of pack_size.
    """
    # MOQ=10, pack=6. Raw qty = 4 -> MOQ promotes to 10 -> rounded up to multiple of 6 -> 12
    qty, reasons = enforce_pack_and_moq(4, min_order_qty=10, pack_size=6, round_mode="up")
    assert qty == 12
    assert "MOQ_PROMOTED" in reasons
    assert "PACK_SIZE_ROUNDED" in reasons

    # Exact multiple: 18 -> 18, no changes
    qty_exact, reasons_exact = enforce_pack_and_moq(18, min_order_qty=10, pack_size=6, round_mode="up")
    assert qty_exact == 18

    # Zero remains zero
    qty_zero, _ = enforce_pack_and_moq(0, min_order_qty=10, pack_size=6)
    assert qty_zero == 0


def test_expiry_cap_blocks_spoilage():
    """
    Test that perishable products are strictly capped by demand
    within their shelf life.
    """
    # Daily demand = 100 / 14 = 7.14 units/day.
    # Shelf life = 3 days. Demand over 3 days ≈ 21-25 units.
    forecast = Forecast(p10=80, p50=100, p90=120, mean=100.0, std=15.0, horizon_days=14)
    inv = InventoryState(on_hand=5, on_order=0, expired_stock=0)
    perishable_prod = ProductMeta(
        product_id="FRESH_BERRIES",
        name="Fresh Berries",
        purchase_price=2.0,
        selling_price=5.0,
        shelf_life_days=3,
        min_order_qty=1,
        pack_size=1
    )

    cap, is_capped = compute_expiry_shelf_life_cap(forecast, inv, perishable_prod)
    assert is_capped is True
    assert cap is not None
    # Cap should be around 25 - 5 = 20 units
    assert cap < 35

    # If unconstrained order wanted 80, it must be clamped down
    constrained_qty, constraints, reasons = apply_product_level_constraints(
        80, forecast, inv, perishable_prod
    )
    assert constrained_qty <= cap
    assert "EXPIRY_SHELF_LIFE" in constraints
    assert "CAPPED_SHELF_LIFE" in reasons


def test_storage_capacity_check():
    """
    Test global storage constraint validation.
    """
    prods = {
        "P1": ProductMeta(product_id="P1", name="Bulky Item", unit_volume=5.0),
        "P2": ProductMeta(product_id="P2", name="Compact Item", unit_volume=0.5)
    }
    # 10 units of P1 (50 vol) + 20 units of P2 (10 vol) = 60 vol
    orders = {"P1": 10, "P2": 20}
    
    is_feas_100, vol_100, _ = check_storage_capacity(orders, prods, max_storage_volume=100.0)
    assert is_feas_100 is True
    assert vol_100 == 60.0

    is_feas_50, vol_50, _ = check_storage_capacity(orders, prods, max_storage_volume=50.0)
    assert is_feas_50 is False
    assert vol_50 == 60.0
