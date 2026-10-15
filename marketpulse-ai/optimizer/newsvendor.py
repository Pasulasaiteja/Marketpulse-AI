"""
Newsvendor Formulation (Task B)

Implements the classical Newsvendor model under demand uncertainty:
    Critical Ratio CR = Cu / (Cu + Co)
    Target Stock Level y* = F^(-1)(CR)
    Order Quantity Q* = max(0, y* - I_usable - P_on_order)

Where:
    - Cu: Underage cost (lost profit margin = selling_price - purchase_price)
    - Co: Overage cost (purchase_price - salvage_value + holding_cost)
    - F: Cumulative distribution function of demand
"""
import math
from typing import Tuple, Dict, Any
from scipy.stats import norm
from .models import Forecast, InventoryState, ProductMeta


def compute_critical_ratio(product: ProductMeta) -> float:
    """
    Computes Newsvendor critical ratio:
        CR = Cu / (Cu + Co)
    """
    return product.critical_ratio


def compute_target_stock_quantile(
    forecast: Forecast,
    critical_ratio: float,
    time_scale: float = 1.0
) -> float:
    """
    Computes y* = F^(-1)(CR) for demand scaled by time_scale.
    Uses Normal distribution fitted to forecast mean and std.
    """
    mean = forecast.get_mean() * time_scale
    std = max(0.001, forecast.get_std() * math.sqrt(time_scale))
    
    # Bound CR safely away from 0 and 1
    cr_clamped = min(0.999, max(0.001, critical_ratio))
    z = norm.ppf(cr_clamped)
    y_star = mean + z * std
    return max(0.0, float(y_star))


def evaluate_newsvendor_metrics(
    target_inventory: float,
    forecast: Forecast,
    product: ProductMeta,
    time_scale: float = 1.0
) -> Dict[str, float]:
    """
    Calculates expected sales, expected leftover, stockout probability,
    and expected financial profit for a given target inventory position y.
    
    Using standard normal loss function:
        z = (y - mu) / sigma
        E[(y - D)^+] = (y - mu) * Phi(z) + sigma * phi(z)
        E[min(y, D)] = y - E[(y - D)^+]
        P(D > y) = 1 - Phi(z)
    """
    mean = forecast.get_mean() * time_scale
    std = max(0.001, forecast.get_std() * math.sqrt(time_scale))
    y = max(0.0, float(target_inventory))

    z = (y - mean) / std
    phi_z = norm.pdf(z)
    Phi_z = norm.cdf(z)

    # Expected leftover units
    expected_leftover = (y - mean) * Phi_z + std * phi_z
    expected_leftover = max(0.0, float(expected_leftover))

    # Expected units sold
    expected_sales = y - expected_leftover
    expected_sales = max(0.0, min(float(expected_sales), mean + 3.0 * std))

    # Stockout probability
    stockout_prob = 1.0 - Phi_z
    stockout_prob = max(0.0, min(1.0, float(stockout_prob)))

    return {
        "expected_sales": round(expected_sales, 4),
        "expected_leftover": round(expected_leftover, 4),
        "expected_stockout_prob": round(stockout_prob, 4),
        "z_score": round(float(z), 4)
    }


def compute_unconstrained_newsvendor_order(
    forecast: Forecast,
    inventory: InventoryState,
    product: ProductMeta,
    scale_to_protection_interval: bool = True
) -> Tuple[int, Dict[str, Any]]:
    """
    Determines the unconstrained optimal order quantity Q* based on Newsvendor quantile.
    """
    horizon = max(1, forecast.horizon_days)
    protection_days = max(1, product.lead_time_days + inventory.days_to_next_replenishment)
    time_scale = (protection_days / horizon) if scale_to_protection_interval else 1.0

    cr = compute_critical_ratio(product)
    y_star = compute_target_stock_quantile(forecast, cr, time_scale=time_scale)

    current_stock = inventory.usable_on_hand + inventory.on_order
    raw_q = max(0.0, y_star - current_stock)
    order_qty = int(math.ceil(raw_q))

    final_inventory = current_stock + order_qty
    metrics = evaluate_newsvendor_metrics(final_inventory, forecast, product, time_scale=time_scale)

    # Compute expected profit from the newly placed order Q
    # Profit = Revenue - Purchase Cost + Salvage - Holding Cost
    revenue = product.selling_price * metrics["expected_sales"]
    order_cost = product.purchase_price * order_qty
    salvage = product.salvage_value * metrics["expected_leftover"]
    holding = product.effective_holding_cost * metrics["expected_leftover"]
    expected_profit = revenue + salvage - order_cost - holding

    details = {
        "critical_ratio": round(cr, 4),
        "underage_cost_Cu": round(product.underage_cost, 2),
        "overage_cost_Co": round(product.overage_cost, 2),
        "target_stock_y_star": round(y_star, 2),
        "current_stock": current_stock,
        "raw_order_quantity": round(raw_q, 2),
        "order_qty": order_qty,
        "cost": round(order_cost, 2),
        "expected_profit": round(expected_profit, 2),
        "expected_stockout_prob": metrics["expected_stockout_prob"],
        "expected_leftover": metrics["expected_leftover"]
    }

    return order_qty, details
