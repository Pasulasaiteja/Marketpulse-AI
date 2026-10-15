"""
Main Optimization Engine & LLM Explanation Inputs (Deliverable 1 & Tasks D/E)

Primary functions:
    1. optimize(forecasts, inventory, products, budget, max_storage_volume=None) -> Plan
    2. explain_inputs(plan: Plan) -> dict
"""
import math
from typing import Dict, List, Optional, Any
from .models import (
    Forecast,
    InventoryState,
    ProductMeta,
    ProductPlan,
    Plan,
    SensitivityPoint
)
from .allocator import greedy_budget_allocation, calculate_expected_profit_at_qty
from .newsvendor import compute_critical_ratio, evaluate_newsvendor_metrics
from .constraints import check_storage_capacity


def optimize(
    forecasts: Dict[str, Forecast],
    inventory: Dict[str, InventoryState],
    products: Dict[str, ProductMeta],
    budget: float,
    max_storage_volume: Optional[float] = None,
    compute_sensitivity: bool = True
) -> Plan:
    """
    Computes a budget-constrained purchasing plan using Newsvendor marginal economics.

    Args:
        forecasts: Dict mapping product_id to Forecast distribution
        inventory: Dict mapping product_id to current InventoryState
        products: Dict mapping product_id to ProductMeta catalog specifications
        budget: Total working capital budget
        max_storage_volume: Optional total shelf/warehouse space constraint
        compute_sensitivity: Whether to generate 80% and 60% budget sensitivity points

    Returns:
        Plan object containing itemized purchase quantities, financials, and constraints.
    """
    if budget < 0:
        budget = 0.0

    # 1. Run greedy budget allocation
    quantities, binding_constraints_map, reason_codes_map = greedy_budget_allocation(
        forecasts=forecasts,
        inventory=inventory,
        products=products,
        budget=budget,
        max_storage_volume=max_storage_volume
    )

    total_cost = 0.0
    total_expected_profit = 0.0
    total_items_ordered = 0
    items_plan: Dict[str, ProductPlan] = {}

    for pid, prod in products.items():
        q = quantities.get(pid, 0)
        fc = forecasts[pid]
        inv = inventory[pid]

        horizon = max(1, fc.horizon_days)
        time_scale = max(1, prod.lead_time_days + inv.days_to_next_replenishment) / horizon

        cost = q * prod.purchase_price
        total_cost += cost
        total_items_ordered += q

        # Calculate metrics for final stock position (existing + newly ordered)
        final_stock = inv.usable_on_hand + inv.on_order + q
        metrics = evaluate_newsvendor_metrics(final_stock, fc, prod, time_scale=time_scale)

        # Expected profit attributed to this purchasing cycle
        item_profit = calculate_expected_profit_at_qty(q, fc, inv, prod, time_scale)
        total_expected_profit += max(0.0, item_profit)

        rel_unc = fc.relative_uncertainty()
        is_uncertain = rel_unc > 1.25

        p_plan = ProductPlan(
            product_id=pid,
            name=prod.name,
            order_qty=q,
            cost=round(cost, 2),
            unit_cost=round(prod.purchase_price, 2),
            unit_price=round(prod.selling_price, 2),
            expected_profit=round(item_profit, 2),
            expected_stockout_prob=metrics["expected_stockout_prob"],
            expected_leftover=metrics["expected_leftover"],
            critical_ratio=round(prod.critical_ratio, 4),
            binding_constraints=binding_constraints_map.get(pid, []),
            reason_codes=reason_codes_map.get(pid, []),
            uncertainty_flag=is_uncertain,
            relative_uncertainty=round(rel_unc, 4)
        )
        items_plan[pid] = p_plan

    # Check store-level binding constraints
    store_binding_constraints = []
    if total_cost >= budget * 0.98 and budget > 0:
        store_binding_constraints.append("BUDGET")
    
    is_vol_ok, total_vol, max_vol = check_storage_capacity(quantities, products, max_storage_volume)
    if max_storage_volume is not None and total_vol >= max_storage_volume * 0.98:
        store_binding_constraints.append("STORAGE_CAPACITY")

    budget_used = round(total_cost, 2)
    budget_rem = round(max(0.0, budget - total_cost), 2)

    # 2. Compute sensitivity points (100%, 80%, 60%)
    sensitivity_dict: Dict[str, SensitivityPoint] = {
        "100_percent": SensitivityPoint(
            budget_level="100%",
            budget_amount=round(budget, 2),
            total_cost=round(total_cost, 2),
            total_expected_profit=round(total_expected_profit, 2),
            items_ordered_count=sum(1 for q in quantities.values() if q > 0)
        )
    }

    if compute_sensitivity and budget > 0:
        for pct_label, mult in [("80_percent", 0.80), ("60_percent", 0.60)]:
            b_sub = budget * mult
            sub_plan = optimize(
                forecasts=forecasts,
                inventory=inventory,
                products=products,
                budget=b_sub,
                max_storage_volume=max_storage_volume,
                compute_sensitivity=False
            )
            sensitivity_dict[pct_label] = SensitivityPoint(
                budget_level=f"{int(mult * 100)}%",
                budget_amount=round(b_sub, 2),
                total_cost=round(sub_plan.total_cost, 2),
                total_expected_profit=round(sub_plan.total_expected_profit, 2),
                items_ordered_count=sum(1 for item in sub_plan.items.values() if item.order_qty > 0)
            )

    return Plan(
        total_cost=round(total_cost, 2),
        budget=round(budget, 2),
        budget_used=budget_used,
        budget_remaining=budget_rem,
        total_expected_profit=round(total_expected_profit, 2),
        total_items_ordered=total_items_ordered,
        items=items_plan,
        binding_constraints=store_binding_constraints,
        sensitivity=sensitivity_dict
    )


def explain_inputs(plan: Plan) -> Dict[str, Any]:
    """
    Extracts structured, deterministic facts and reasoning codes from the Plan
    that Member 4's LLM will narrate to the retailer without doing math.
    """
    funded_items = [item for item in plan.items.values() if item.order_qty > 0]
    dropped_items = [item for item in plan.items.values() if item.order_qty == 0]

    # Sort funded by expected profit descending
    funded_items.sort(key=lambda x: x.expected_profit, reverse=True)

    top_allocations = []
    for item in funded_items[:5]:
        reasons_desc = []
        if "ALLOCATED_OPTIMAL" in item.reason_codes:
            reasons_desc.append("High capital efficiency and verified local demand")
        if "ALLOCATED_TRIMMED_BUDGET" in item.reason_codes:
            reasons_desc.append("Funded partially to preserve cash under current budget")
        if "PACK_SIZE_ROUNDED" in item.reason_codes:
            reasons_desc.append("Rounded to supplier pack multiple")
        if "MOQ_PROMOTED" in item.reason_codes:
            reasons_desc.append("Met supplier minimum order quantity")
        if not reasons_desc:
            reasons_desc.append("Positive expected margin")

        top_allocations.append({
            "product_id": item.product_id,
            "name": item.name,
            "qty": item.order_qty,
            "spend": item.cost,
            "expected_profit": item.expected_profit,
            "reason": "; ".join(reasons_desc)
        })

    dropped_list = []
    for item in dropped_items:
        reasons = item.reason_codes
        if "DROPPED_BUDGET_EXHAUSTED" in reasons:
            desc = "Working capital exhausted before reaching this item's minimum order requirement."
        elif "DROPPED_HIGH_UNCERTAINTY" in reasons:
            desc = f"Demand uncertainty is high ({int(item.relative_uncertainty * 100)}% variance); omitted to protect cash flow."
        elif "DROPPED_LOW_CAPITAL_EFFICIENCY" in reasons:
            desc = "Expected profit per dollar lower than higher-priority catalog staples."
        else:
            desc = "Not prioritized under current constraints."

        dropped_list.append({
            "product_id": item.product_id,
            "name": item.name,
            "unit_cost": item.unit_cost,
            "reason_codes": item.reason_codes,
            "explanation": desc
        })

    uncertainty_alerts = []
    for item in plan.items.values():
        if item.uncertainty_flag:
            uncertainty_alerts.append({
                "product_id": item.product_id,
                "name": item.name,
                "relative_uncertainty": item.relative_uncertainty,
                "status": "Funded with conservative haircut" if item.order_qty > 0 else "Dropped due to risk",
                "note": f"Relative uncertainty ratio is {item.relative_uncertainty:.2f} (above 1.25 safety threshold)."
            })

    utilization = (plan.budget_used / plan.budget * 100.0) if plan.budget > 0 else 0.0

    # Bottleneck explanation
    if "BUDGET" in plan.binding_constraints:
        s_80 = plan.sensitivity.get("80_percent")
        gain_text = ""
        if s_80:
            diff_prof = plan.total_expected_profit - s_80.total_expected_profit
            gain_text = f" At 100% budget (${plan.budget:,.2f}), the plan captures ${diff_prof:,.2f} more profit than at 80%."
        bottleneck = f"Budget is fully binding ({utilization:.1f}% utilized).{gain_text}"
    else:
        bottleneck = f"Budget is non-binding (${plan.budget_remaining:,.2f} remaining); unconstrained optimal demand satisfied."

    return {
        "summary": {
            "budget": plan.budget,
            "total_spend": plan.total_cost,
            "expected_profit": plan.total_expected_profit,
            "budget_utilization_pct": round(utilization, 2),
            "num_products_funded": len(funded_items),
            "num_products_dropped": len(dropped_items)
        },
        "top_allocations": top_allocations,
        "dropped_items": dropped_list,
        "uncertainty_alerts": uncertainty_alerts,
        "binding_constraints": plan.binding_constraints,
        "budget_bottleneck": bottleneck,
        "sensitivity": {k: v.to_dict() for k, v in plan.sensitivity.items()}
    }
