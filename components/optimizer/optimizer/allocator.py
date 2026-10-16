"""
Budget Allocation & Knapsack Optimization (Task D)

Allocates limited working capital across candidate products to maximize
total expected store profit while respecting budget, storage, MOQ, and pack size.

Provides:
1. Greedy Marginal ROI Allocation (fast, interpretable marginal analysis)
2. Exact Mixed-Integer Linear Program (MILP) using SciPy for benchmark comparison
"""
import math
from typing import Dict, List, Tuple, Optional, Any
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds

from .models import Forecast, InventoryState, ProductMeta, ProductPlan
from .newsvendor import (
    compute_critical_ratio,
    compute_target_stock_quantile,
    evaluate_newsvendor_metrics
)
from .constraints import enforce_pack_and_moq, compute_expiry_shelf_life_cap


def calculate_expected_profit_at_qty(
    qty: int,
    forecast: Forecast,
    inventory: InventoryState,
    product: ProductMeta,
    time_scale: float = 1.0
) -> float:
    """
    Computes expected net profit if order quantity is qty.
    Net profit = Revenue + Salvage - Purchase Cost - Holding Cost.
    """
    if qty <= 0:
        # Existing stock only
        curr_stock = inventory.usable_on_hand + inventory.on_order
        if curr_stock <= 0:
            return 0.0
        metrics = evaluate_newsvendor_metrics(curr_stock, forecast, product, time_scale=time_scale)
        rev = product.selling_price * metrics["expected_sales"]
        salvage = product.salvage_value * metrics["expected_leftover"]
        holding = product.effective_holding_cost * metrics["expected_leftover"]
        return rev + salvage - holding

    total_stock = inventory.usable_on_hand + inventory.on_order + qty
    metrics = evaluate_newsvendor_metrics(total_stock, forecast, product, time_scale=time_scale)
    
    revenue = product.selling_price * metrics["expected_sales"]
    order_cost = product.purchase_price * qty
    salvage = product.salvage_value * metrics["expected_leftover"]
    holding = product.effective_holding_cost * metrics["expected_leftover"]
    
    return revenue + salvage - order_cost - holding


def greedy_budget_allocation(
    forecasts: Dict[str, Forecast],
    inventory: Dict[str, InventoryState],
    products: Dict[str, ProductMeta],
    budget: float,
    max_storage_volume: Optional[float] = None,
    uncertainty_haircut_threshold: float = 1.25
) -> Tuple[Dict[str, int], Dict[str, List[str]], Dict[str, List[str]]]:
    """
    Greedy marginal ROI knapsack allocation.
    
    Step-by-step adds pack_size increments of products that offer the highest
    marginal expected profit per currency unit spent (dProfit / dCost > 0),
    subject to budget and volume limits.

    Returns:
        (quantities_dict, binding_constraints_dict, reason_codes_dict)
    """
    budget_remaining = float(budget)
    vol_remaining = float(max_storage_volume) if max_storage_volume is not None else float("inf")

    quantities: Dict[str, int] = {pid: 0 for pid in products}
    binding_constraints: Dict[str, List[str]] = {pid: [] for pid in products}
    reason_codes: Dict[str, List[str]] = {pid: [] for pid in products}

    # Pre-calculate upper bounds and uncertainty penalty per product
    upper_bounds: Dict[str, int] = {}
    uncertainty_penalties: Dict[str, float] = {}

    for pid, prod in products.items():
        fc = forecasts[pid]
        inv = inventory[pid]
        horizon = max(1, fc.horizon_days)
        protection_days = max(1, prod.lead_time_days + inv.days_to_next_replenishment)
        time_scale = protection_days / horizon

        # Newsvendor unconstrained target
        cr = prod.critical_ratio
        
        # Uncertainty check
        rel_unc = fc.relative_uncertainty()
        if rel_unc > uncertainty_haircut_threshold:
            # Haircut target service level for high-variance products to protect capital
            cr_effective = min(0.50, cr)  # Cap at median demand
            uncertainty_penalties[pid] = 0.85  # 15% marginal ROI discount
            reason_codes[pid].append("HIGH_UNCERTAINTY_HAIRCUT")
        else:
            cr_effective = cr
            uncertainty_penalties[pid] = 1.0

        y_target = compute_target_stock_quantile(fc, cr_effective, time_scale=time_scale)
        curr_stock = inv.usable_on_hand + inv.on_order
        max_desired = max(0, int(math.ceil(y_target - curr_stock)))

        # Expiry cap
        max_expiry, is_perishable = compute_expiry_shelf_life_cap(fc, inv, prod)
        if is_perishable and max_expiry is not None:
            max_desired = min(max_desired, max_expiry)

        upper_bounds[pid] = max_desired

    # Iterative marginal knapsack selection
    while True:
        best_pid = None
        best_roi = 0.0
        best_step_qty = 0
        best_step_cost = 0.0
        best_step_vol = 0.0

        for pid, prod in products.items():
            curr_q = quantities[pid]
            max_q = upper_bounds[pid]

            if curr_q >= max_q:
                continue

            # Determine next step quantity
            if curr_q == 0:
                # First step must meet MOQ and pack size
                step_q, _ = enforce_pack_and_moq(prod.min_order_qty, prod.min_order_qty, prod.pack_size, round_mode="up")
            else:
                step_q = prod.pack_size

            # Don't exceed unconstrained target by more than 1 pack
            if curr_q + step_q > max_q + (prod.pack_size - 1):
                continue

            step_cost = step_q * prod.purchase_price
            step_vol = step_q * prod.unit_volume

            if step_cost > budget_remaining or step_vol > vol_remaining:
                continue

            # Calculate marginal profit of this increment
            fc = forecasts[pid]
            inv = inventory[pid]
            horizon = max(1, fc.horizon_days)
            time_scale = max(1, prod.lead_time_days + inv.days_to_next_replenishment) / horizon

            profit_before = calculate_expected_profit_at_qty(curr_q, fc, inv, prod, time_scale)
            profit_after = calculate_expected_profit_at_qty(curr_q + step_q, fc, inv, prod, time_scale)
            marginal_profit = (profit_after - profit_before) * uncertainty_penalties[pid]

            if marginal_profit <= 0:
                continue

            roi = marginal_profit / step_cost
            if roi > best_roi:
                best_roi = roi
                best_pid = pid
                best_step_qty = step_q
                best_step_cost = step_cost
                best_step_vol = step_vol

        # If no positive ROI product fits, stop
        if best_pid is None:
            break

        # Allocate step
        quantities[best_pid] += best_step_qty
        budget_remaining -= best_step_cost
        vol_remaining -= best_step_vol

    # Annotate constraints and reason codes
    for pid, prod in products.items():
        q = quantities[pid]
        max_q = upper_bounds[pid]

        if q == 0:
            if budget_remaining < prod.purchase_price * prod.min_order_qty:
                reason_codes[pid].append("DROPPED_BUDGET_EXHAUSTED")
                binding_constraints[pid].append("BUDGET")
            elif forecasts[pid].relative_uncertainty() > uncertainty_haircut_threshold:
                reason_codes[pid].append("DROPPED_HIGH_UNCERTAINTY")
            else:
                reason_codes[pid].append("DROPPED_LOW_CAPITAL_EFFICIENCY")
        else:
            if q < max_q:
                reason_codes[pid].append("ALLOCATED_TRIMMED_BUDGET")
                binding_constraints[pid].append("BUDGET")
            else:
                reason_codes[pid].append("ALLOCATED_OPTIMAL")

            if prod.pack_size > 1:
                reason_codes[pid].append("PACK_SIZE_ROUNDED")
            if q == prod.min_order_qty:
                reason_codes[pid].append("MOQ_PROMOTED")

    return quantities, binding_constraints, reason_codes


def exact_milp_budget_allocation(
    forecasts: Dict[str, Forecast],
    inventory: Dict[str, InventoryState],
    products: Dict[str, ProductMeta],
    budget: float,
    max_storage_volume: Optional[float] = None
) -> Tuple[Dict[str, int], float]:
    """
    Exact Mixed-Integer Linear Program (MILP) using SciPy.
    Used to benchmark and verify the greedy algorithm.
    
    Approximates expected profit with piecewise-linear concave segments
    over integer multiples of pack sizes.
    """
    # For small-to-medium retail baskets (10-30 items), generate discrete candidates
    candidate_steps: List[Dict[str, Any]] = []

    for pid, prod in products.items():
        fc = forecasts[pid]
        inv = inventory[pid]
        horizon = max(1, fc.horizon_days)
        time_scale = max(1, prod.lead_time_days + inv.days_to_next_replenishment) / horizon

        # Candidate order quantities: 0, MOQ, MOQ + pack, ... up to target
        y_target = compute_target_stock_quantile(fc, prod.critical_ratio, time_scale=time_scale)
        curr_stock = inv.usable_on_hand + inv.on_order
        max_desired = max(0, int(math.ceil(y_target - curr_stock)))

        step_vals = [0]
        curr = max(prod.min_order_qty, prod.pack_size)
        while curr <= max_desired + prod.pack_size:
            step_vals.append(curr)
            curr += prod.pack_size

        for i in range(len(step_vals) - 1):
            q_from = step_vals[i]
            q_to = step_vals[i + 1]
            p_from = calculate_expected_profit_at_qty(q_from, fc, inv, prod, time_scale)
            p_to = calculate_expected_profit_at_qty(q_to, fc, inv, prod, time_scale)
            delta_profit = p_to - p_from
            delta_cost = (q_to - q_from) * prod.purchase_price
            delta_vol = (q_to - q_from) * prod.unit_volume

            if delta_profit > 0 and delta_cost <= budget:
                candidate_steps.append({
                    "pid": pid,
                    "delta_qty": q_to - q_from,
                    "delta_profit": delta_profit,
                    "delta_cost": delta_cost,
                    "delta_vol": delta_vol
                })

    if not candidate_steps:
        return {pid: 0 for pid in products}, 0.0

    num_vars = len(candidate_steps)
    # Objective: Maximize delta_profit -> minimize -delta_profit
    c = np.array([-step["delta_profit"] for step in candidate_steps])

    # Constraints:
    # 1. Budget constraint: sum(delta_cost * x) <= budget
    costs = [step["delta_cost"] for step in candidate_steps]
    vols = [step["delta_vol"] for step in candidate_steps]

    if max_storage_volume is not None and max_storage_volume > 0:
        A = np.array([costs, vols])
        b_u = np.array([budget, max_storage_volume])
    else:
        A = np.array([costs])
        b_u = np.array([budget])

    b_l = np.zeros(len(b_u))
    constraints = LinearConstraint(A, b_l, b_u)

    # Variable bounds: binary 0 <= x_j <= 1, integer
    integrality = np.ones(num_vars)  # all integer
    bounds = Bounds(0, 1)

    res = milp(c=c, constraints=constraints, integrality=integrality, bounds=bounds)

    chosen_quantities: Dict[str, int] = {pid: 0 for pid in products}
    total_opt_profit = 0.0

    if res.success:
        x_sol = np.round(res.x)
        for j, step in enumerate(candidate_steps):
            if x_sol[j] > 0.5:
                chosen_quantities[step["pid"]] += step["delta_qty"]
                total_opt_profit += step["delta_profit"]

    return chosen_quantities, total_opt_profit
