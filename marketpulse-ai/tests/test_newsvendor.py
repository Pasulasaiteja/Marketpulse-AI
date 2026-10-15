"""
Tests for Newsvendor Formulation (Task B)
"""
import pytest
from scipy.stats import norm
from optimizer.models import Forecast, InventoryState, ProductMeta
from optimizer.newsvendor import (
    compute_critical_ratio,
    compute_target_stock_quantile,
    compute_unconstrained_newsvendor_order,
    evaluate_newsvendor_metrics
)


def test_newsvendor_symmetric_closed_form():
    """
    When Cu == Co, Critical Ratio is exactly 0.50.
    Optimal stock level y* must equal mean demand mu.
    """
    forecast = Forecast(p10=74.37, p50=100.0, p90=125.63, mean=100.0, std=20.0, horizon_days=14)
    inventory = InventoryState(on_hand=0, on_order=0, days_to_next_replenishment=14)
    # p=20, c=10, holding=0, salvage=0 -> Cu = 10, Co = 10 -> CR = 0.5
    product = ProductMeta(
        product_id="SYM_ITEM",
        name="Symmetric Product",
        purchase_price=10.0,
        selling_price=20.0,
        holding_cost=0.0,
        salvage_value=0.0,
        lead_time_days=0
    )

    cr = compute_critical_ratio(product)
    assert abs(cr - 0.50) < 1e-4

    y_star = compute_target_stock_quantile(forecast, cr, time_scale=1.0)
    assert abs(y_star - 100.0) < 1e-3

    order_qty, details = compute_unconstrained_newsvendor_order(
        forecast, inventory, product, scale_to_protection_interval=False
    )
    assert order_qty == 100
    assert abs(details["expected_stockout_prob"] - 0.50) < 0.01


def test_newsvendor_high_margin_orders_above_mean():
    """
    When Cu >> Co (high margin), CR > 0.5, so y* > mean.
    """
    forecast = Forecast(p10=74.37, p50=100.0, p90=125.63, mean=100.0, std=20.0, horizon_days=14)
    inventory = InventoryState(on_hand=0, on_order=0, days_to_next_replenishment=14)
    # p=50, c=10, holding=0, salvage=0 -> Cu = 40, Co = 10 -> CR = 0.80
    product = ProductMeta(
        product_id="HIGH_MARGIN",
        name="High Margin Item",
        purchase_price=10.0,
        selling_price=50.0,
        holding_cost=0.0,
        salvage_value=0.0,
        lead_time_days=0
    )

    cr = compute_critical_ratio(product)
    assert abs(cr - 0.80) < 1e-4

    z_80 = norm.ppf(0.80)  # ~0.8416
    expected_y = 100.0 + z_80 * 20.0  # ~116.83
    
    order_qty, details = compute_unconstrained_newsvendor_order(
        forecast, inventory, product, scale_to_protection_interval=False
    )
    assert order_qty == 117
    assert order_qty > 100


def test_newsvendor_low_margin_orders_below_mean():
    """
    When Cu < Co (low margin / high overage risk), CR < 0.5, so y* < mean.
    """
    forecast = Forecast(p10=74.37, p50=100.0, p90=125.63, mean=100.0, std=20.0, horizon_days=14)
    inventory = InventoryState(on_hand=0, on_order=0, days_to_next_replenishment=14)
    # p=12, c=10, holding=0, salvage=0 -> Cu = 2, Co = 10 -> CR = 2/12 = 0.1667
    product = ProductMeta(
        product_id="LOW_MARGIN",
        name="Low Margin Item",
        purchase_price=10.0,
        selling_price=12.0,
        holding_cost=0.0,
        salvage_value=0.0,
        lead_time_days=0
    )

    cr = compute_critical_ratio(product)
    assert cr < 0.50

    order_qty, details = compute_unconstrained_newsvendor_order(
        forecast, inventory, product, scale_to_protection_interval=False
    )
    # y* = 100 + norm.ppf(0.1667) * 20 ≈ 100 - 0.9674 * 20 ≈ 80.65 -> 81
    assert order_qty == 81
    assert order_qty < 100


def test_uncertainty_response_theory():
    """
    Theory test: For a low-margin product (CR < 0.5), wider uncertainty
    MUST lower the order quantity, because the penalty of over-ordering
    exceeds the profit from an extra sale.
    """
    # Product with low margin: c=10, p=12 -> CR ≈ 0.1667
    product = ProductMeta(
        product_id="RISK_ITEM",
        name="Risky Perishable",
        purchase_price=10.0,
        selling_price=12.0,
        holding_cost=0.0,
        salvage_value=0.0,
        lead_time_days=0
    )
    inventory = InventoryState(on_hand=0, on_order=0, days_to_next_replenishment=14)

    # Tight uncertainty: std = 5
    forecast_tight = Forecast(p10=93.6, p50=100.0, p90=106.4, mean=100.0, std=5.0, horizon_days=14)
    # Wide uncertainty: std = 30
    forecast_wide = Forecast(p10=61.6, p50=100.0, p90=138.4, mean=100.0, std=30.0, horizon_days=14)

    qty_tight, details_tight = compute_unconstrained_newsvendor_order(
        forecast_tight, inventory, product, scale_to_protection_interval=False
    )
    qty_wide, details_wide = compute_unconstrained_newsvendor_order(
        forecast_wide, inventory, product, scale_to_protection_interval=False
    )

    # Tight: 100 - 0.9674 * 5 ≈ 95.16 -> 96
    # Wide: 100 - 0.9674 * 30 ≈ 70.98 -> 71
    assert qty_wide < qty_tight
    assert qty_tight - qty_wide > 20
