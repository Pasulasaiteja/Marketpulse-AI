"""
Constraint Enforcement Module (Task C)

Handles practical retail constraints:
1. Minimum Order Quantity (MOQ) and Pack Sizes (multiples of carton/case)
2. Expiry & Shelf-Life Limits (capping order so stock is sellable before expiration)
3. Storage Capacity (global store or shelf volume limits)
4. Lead Time Protection Coverage
"""
import math
from typing import List, Tuple, Dict, Any, Optional
from .models import Forecast, InventoryState, ProductMeta


def enforce_pack_and_moq(
    qty: int,
    min_order_qty: int = 1,
    pack_size: int = 1,
    round_mode: str = "up"
) -> Tuple[int, List[str]]:
    """
    Enforces that order quantity Q:
    - is 0, OR >= min_order_qty
    - is a strict multiple of pack_size

    Returns:
        (adjusted_qty, list_of_reason_codes)
    """
    if qty <= 0:
        return 0, []

    moq = max(1, min_order_qty)
    pack = max(1, pack_size)
    reasons = []

    # Ensure MOQ is at least reached
    if qty < moq:
        if round_mode == "up":
            target = moq
            reasons.append("MOQ_PROMOTED")
        else:
            return 0, ["DROPPED_BELOW_MOQ"]
    else:
        target = qty

    # Ensure multiple of pack size
    remainder = target % pack
    if remainder != 0:
        if round_mode == "up":
            target = target + (pack - remainder)
            reasons.append("PACK_SIZE_ROUNDED")
        else:
            target = target - remainder
            if target < moq:
                return 0, ["DROPPED_BELOW_MOQ"]
            reasons.append("PACK_SIZE_ROUNDED_DOWN")

    return target, reasons


def compute_expiry_shelf_life_cap(
    forecast: Forecast,
    inventory: InventoryState,
    product: ProductMeta,
    safety_z: float = 1.282
) -> Tuple[Optional[int], bool]:
    """
    Computes maximum units of a product that can be sold before expiring.
    Orders above this cap will inevitably spoil.

    If product.shelf_life_days is None, product is non-perishable (no cap).
    
    Returns:
        (max_order_allowed, was_capped_bool)
    """
    if product.shelf_life_days is None:
        return None, False

    shelf_days = product.shelf_life_days
    horizon = max(1, forecast.horizon_days)

    # Daily rate of demand and std
    daily_mean = forecast.get_mean() / horizon
    daily_std = forecast.get_std() / math.sqrt(horizon)

    # Max expected demand over the product's remaining shelf life (mean + z * std)
    demand_until_expiry = daily_mean * shelf_days + safety_z * daily_std * math.sqrt(shelf_days)
    
    # Net headroom after existing usable inventory
    usable_inv = inventory.usable_on_hand + inventory.on_order
    max_order = max(0, int(math.floor(demand_until_expiry - usable_inv)))

    return max_order, True


def check_storage_capacity(
    order_quantities: Dict[str, int],
    products: Dict[str, ProductMeta],
    max_storage_volume: Optional[float]
) -> Tuple[bool, float, float]:
    """
    Calculates total volume footprint:
        Total Volume = sum(Q_i * unit_volume_i)
    
    Returns:
        (is_feasible, total_volume_used, max_volume)
    """
    if max_storage_volume is None or max_storage_volume <= 0:
        total_vol = sum(order_quantities.get(pid, 0) * prod.unit_volume for pid, prod in products.items())
        return True, round(total_vol, 2), float("inf")

    total_vol = sum(order_quantities.get(pid, 0) * prod.unit_volume for pid, prod in products.items())
    is_feasible = total_vol <= (max_storage_volume + 1e-6)
    return is_feasible, round(total_vol, 2), round(max_storage_volume, 2)


def apply_product_level_constraints(
    raw_qty: int,
    forecast: Forecast,
    inventory: InventoryState,
    product: ProductMeta
) -> Tuple[int, List[str], List[str]]:
    """
    Applies expiry limits, MOQ, and pack size to an unconstrained target order.

    Returns:
        (constrained_qty, binding_constraints, reason_codes)
    """
    binding_constraints = []
    reason_codes = []
    qty = raw_qty

    if qty <= 0:
        return 0, [], []

    # 1. Expiry / Shelf-Life Cap
    max_expiry, is_perishable = compute_expiry_shelf_life_cap(forecast, inventory, product)
    if is_perishable and max_expiry is not None:
        if qty > max_expiry:
            qty = max_expiry
            binding_constraints.append("EXPIRY_SHELF_LIFE")
            reason_codes.append("CAPPED_SHELF_LIFE")

    if qty <= 0:
        return 0, binding_constraints, reason_codes

    # 2. MOQ & Pack Size
    adjusted_qty, pack_reasons = enforce_pack_and_moq(
        qty=qty,
        min_order_qty=product.min_order_qty,
        pack_size=product.pack_size,
        round_mode="up"
    )

    if adjusted_qty != qty:
        if "MOQ_PROMOTED" in pack_reasons:
            binding_constraints.append("MOQ")
        if "PACK_SIZE_ROUNDED" in pack_reasons or "PACK_SIZE_ROUNDED_DOWN" in pack_reasons:
            binding_constraints.append("PACK_SIZE")
        reason_codes.extend(pack_reasons)

    # 3. Re-verify expiry cap after pack size rounding up
    if is_perishable and max_expiry is not None and adjusted_qty > max_expiry:
        # If rounding up exceeds expiry cap, step down by pack size
        step_down = (adjusted_qty - max_expiry + product.pack_size - 1) // product.pack_size
        adjusted_qty = max(0, adjusted_qty - step_down * product.pack_size)
        binding_constraints.append("EXPIRY_SHELF_LIFE")
        reason_codes.append("CAPPED_SHELF_LIFE")

    return adjusted_qty, binding_constraints, reason_codes
