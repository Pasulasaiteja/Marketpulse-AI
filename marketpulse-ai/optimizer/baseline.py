"""
Baseline Replenishment Policy (Task A)

Implements the standard inventory control reorder formula:
    Q_i = max(0, D_i + SS_i - I_i - P_i)

Where:
    - D_i: forecast demand over the replenishment and lead time period
    - SS_i: safety stock calculated from forecast uncertainty
    - I_i: usable inventory on hand (excluding expired / damaged items)
    - P_i: inventory already on order with suppliers
"""
import math
from typing import Tuple
from .models import Forecast, InventoryState, ProductMeta


def compute_safety_stock(
    forecast: Forecast,
    lead_time_days: int = 0,
    replenishment_days: int = 7,
    service_factor_z: float = 1.645
) -> float:
    """
    Computes safety stock: SS = z * sigma_L.
    If lead time and replenishment days are provided relative to forecast horizon,
    scales variance by sqrt((L + R) / H).
    """
    base_std = forecast.get_std()
    horizon = max(1, forecast.horizon_days)
    protection_days = max(1, lead_time_days + replenishment_days)
    
    # Scale factor based on protection interval
    scale = math.sqrt(protection_days / horizon)
    ss = service_factor_z * base_std * scale
    return max(0.0, ss)


def compute_baseline_quantity(
    forecast: Forecast,
    inventory: InventoryState,
    product: ProductMeta,
    service_factor_z: float = 1.645,
    scale_to_protection_interval: bool = True
) -> Tuple[int, dict]:
    """
    Computes the baseline order quantity:
        Q_i = max(0, round(D_i + SS_i - I_usable - P_on_order))

    Returns:
        (order_qty, calculation_details)
    """
    horizon = max(1, forecast.horizon_days)
    protection_days = max(1, product.lead_time_days + inventory.days_to_next_replenishment)

    if scale_to_protection_interval and protection_days != horizon:
        time_ratio = protection_days / horizon
        d_mean = forecast.get_mean() * time_ratio
        ss = compute_safety_stock(
            forecast=forecast,
            lead_time_days=product.lead_time_days,
            replenishment_days=inventory.days_to_next_replenishment,
            service_factor_z=service_factor_z
        )
    else:
        d_mean = forecast.get_mean()
        ss = service_factor_z * forecast.get_std()

    i_usable = inventory.usable_on_hand
    p_on_order = max(0, inventory.on_order)
    current_stock_position = i_usable + p_on_order

    target_stock_position = d_mean + ss
    raw_qty = target_stock_position - current_stock_position
    
    # Baseline quantity is strictly non-negative integer
    order_qty = max(0, int(math.ceil(raw_qty)))

    details = {
        "forecast_demand_D": round(d_mean, 2),
        "safety_stock_SS": round(ss, 2),
        "usable_inventory_I": i_usable,
        "on_order_inventory_P": p_on_order,
        "net_stock_position": current_stock_position,
        "target_stock_position": round(target_stock_position, 2),
        "raw_order_quantity": round(raw_qty, 2),
        "final_baseline_quantity": order_qty
    }

    return order_qty, details
