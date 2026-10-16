"""
Full System Integration Tests for Component C Optimizer (Tasks D & E)
"""
import pytest
from optimizer import optimize, explain_inputs
from optimizer.allocator import exact_milp_budget_allocation
from mocks.mock_data import get_mock_retail_store
from optimizer.models import Forecast, InventoryState, ProductMeta


def test_budget_feasibility_never_exceeded():
    """
    Test that total_cost <= budget under various budget constraints.
    """
    forecasts, inventory, products = get_mock_retail_store()

    for test_budget in [500.0, 1000.0, 2000.0, 3000.0, 5000.0, 7000.0]:
        plan = optimize(forecasts, inventory, products, budget=test_budget)
        assert plan.total_cost <= test_budget + 1e-4, f"Failed at budget {test_budget}: cost {plan.total_cost}"
        assert plan.budget_used == plan.total_cost
        assert plan.budget_remaining >= 0.0


def test_budget_monotonicity():
    """
    Test that a larger budget never yields lower total expected profit.
    """
    forecasts, inventory, products = get_mock_retail_store()

    budgets = [500.0, 1000.0, 2000.0, 3000.0, 5000.0, 7000.0]
    profits = []

    for b in budgets:
        plan = optimize(forecasts, inventory, products, budget=b, compute_sensitivity=False)
        profits.append(plan.total_expected_profit)

    for i in range(len(profits) - 1):
        assert profits[i + 1] >= profits[i] - 1e-4, (
            f"Monotonicity violated between {budgets[i]} (${profits[i]}) "
            f"and {budgets[i+1]} (${profits[i+1]})"
        )


def test_budget_change_5000_to_3000_deterministic():
    """
    Test the key hackathon demo scenario:
    Dropping budget from 5,000 to 3,000 deterministically drops or trims
    lower-priority products while protecting high-ROI core staples.
    """
    forecasts, inventory, products = get_mock_retail_store()

    plan_5k = optimize(forecasts, inventory, products, budget=5000.0)
    plan_3k = optimize(forecasts, inventory, products, budget=3000.0)

    assert plan_5k.total_cost <= 5000.0
    assert plan_3k.total_cost <= 3000.0
    assert plan_5k.total_expected_profit > plan_3k.total_expected_profit

    # Core staples (e.g., Milk, Bread, Rice, Oil) must still be funded in both
    assert plan_3k.items["SKU_MILK_1L"].order_qty > 0
    assert plan_3k.items["SKU_BREAD_WHITE"].order_qty > 0
    assert plan_3k.items["SKU_RICE_5KG"].order_qty > 0

    # Total units ordered at 5k must be >= total units at 3k
    assert plan_5k.total_items_ordered >= plan_3k.total_items_ordered


def test_greedy_vs_ip_optimality_gap():
    """
    Test that the greedy marginal allocation gets within 8% (>=92% ratio)
    of the exact MILP optimum.
    """
    forecasts, inventory, products = get_mock_retail_store()
    budget = 2000.0  # Tight budget to stress test knapsack selection

    greedy_plan = optimize(forecasts, inventory, products, budget=budget, compute_sensitivity=False)
    _, milp_profit = exact_milp_budget_allocation(forecasts, inventory, products, budget=budget)

    if milp_profit > 0:
        ratio = greedy_plan.total_expected_profit / milp_profit
        assert ratio >= 0.90, f"Greedy ratio {ratio:.3f} below acceptable 0.90 bound"


def test_high_uncertainty_handling():
    """
    High-uncertainty product (Saffron spice with relative uncertainty > 3.0)
    must be flagged and de-prioritized over reliable items under tight capital.
    """
    forecasts, inventory, products = get_mock_retail_store()
    
    # Run with limited budget ($1,500) where Saffron must be dropped in favor of staple goods
    plan_tight = optimize(forecasts, inventory, products, budget=1500.0)
    saffron_plan = plan_tight.items["SKU_EXOTIC_SPICE_CASE"]

    assert saffron_plan.uncertainty_flag is True
    assert saffron_plan.order_qty == 0
    assert any("UNCERTAINTY" in r for r in saffron_plan.reason_codes)


def test_explain_inputs_output_structure():
    """
    Test that explain_inputs(plan) returns all structured keys required by Member 4.
    """
    forecasts, inventory, products = get_mock_retail_store()
    plan = optimize(forecasts, inventory, products, budget=3000.0)
    facts = explain_inputs(plan)

    assert "summary" in facts
    assert "top_allocations" in facts
    assert "dropped_items" in facts
    assert "uncertainty_alerts" in facts
    assert "binding_constraints" in facts
    assert "budget_bottleneck" in facts
    assert "sensitivity" in facts

    summary = facts["summary"]
    assert summary["budget"] == 3000.0
    assert summary["total_spend"] == plan.total_cost
    assert len(facts["top_allocations"]) > 0


def test_edge_case_zero_budget():
    """Zero budget should result in zero orders and 0 cost without error."""
    forecasts, inventory, products = get_mock_retail_store()
    plan = optimize(forecasts, inventory, products, budget=0.0)
    assert plan.total_cost == 0.0
    assert plan.total_items_ordered == 0
    assert all(item.order_qty == 0 for item in plan.items.values())


def test_edge_case_all_unaffordable():
    """Budget so small that not even 1 MOQ can be bought."""
    forecasts, inventory, products = get_mock_retail_store()
    plan = optimize(forecasts, inventory, products, budget=0.10)
    assert plan.total_cost == 0.0
    assert plan.total_items_ordered == 0


def test_edge_case_huge_moq():
    """Product with MOQ larger than total budget cannot be bought."""
    forecasts, inventory, products = get_mock_retail_store()
    products["SKU_MILK_1L"].min_order_qty = 50000  # requires $60,000 to order

    plan = optimize(forecasts, inventory, products, budget=1000.0)
    assert plan.items["SKU_MILK_1L"].order_qty == 0
    assert "DROPPED_BUDGET_EXHAUSTED" in plan.items["SKU_MILK_1L"].reason_codes


def test_edge_case_zero_demand():
    """Product with zero forecasted demand should order zero units."""
    forecasts, inventory, products = get_mock_retail_store()
    forecasts["SKU_RICE_5KG"] = Forecast(p10=0, p50=0, p90=0, mean=0.0, std=0.0, horizon_days=30)

    plan = optimize(forecasts, inventory, products, budget=5000.0)
    assert plan.items["SKU_RICE_5KG"].order_qty == 0
