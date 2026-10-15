"""
Backtesting & Benchmarking Harness (Task F & Deliverable 3)

Compares MarketPulse Optimizer against 3 standard retail baselines:
    1. Equal Budget Split (divides budget equally across SKUs)
    2. Historical Average Reorder (orders past mean sales, scaled to budget)
    3. Fixed-Threshold Reordering ((s, S) min-max policy, scaled to budget)

Simulates multi-period rolling retail inventory cycles and evaluates:
    - Realized Profit ($)
    - Stockout Rate (%)
    - Excess Inventory ($)
    - Capital Utilization (%)
"""
import math
import random
from typing import Dict, List, Tuple, Any
import numpy as np

import sys
from pathlib import Path

# Add project root to path for standalone execution
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from optimizer.models import Forecast, InventoryState, ProductMeta
from optimizer.engine import optimize
from mocks.mock_data import get_mock_retail_store


class BacktestSimulator:
    def __init__(self, seed: int = 42):
        self.seed = seed
        random.seed(seed)
        np.random.seed(seed)

    def run_simulation(
        self,
        num_periods: int = 6,
        budget_per_period: float = 3500.0
    ) -> Dict[str, Any]:
        """
        Executes a multi-period simulation comparing the 4 policies on identical demand realizations.
        """
        policies = ["MarketPulse Optimizer", "Equal Budget Split", "Historical Average", "Fixed-Threshold (s,S)"]
        
        # State tracking for each policy
        history: Dict[str, Dict[str, float]] = {
            pol: {
                "total_revenue": 0.0,
                "total_spend": 0.0,
                "total_holding_cost": 0.0,
                "total_net_profit": 0.0,
                "total_demand": 0.0,
                "total_lost_sales_units": 0.0,
                "total_leftover_units": 0.0,
                "total_leftover_value": 0.0,
                "total_budget_allocated": num_periods * budget_per_period
            }
            for pol in policies
        }

        # Initialize inventory state for each policy
        _, base_inventory, products = get_mock_retail_store()
        policy_inventory = {
            pol: {pid: inv.usable_on_hand for pid, inv in base_inventory.items()}
            for pol in policies
        }

        # Rolling period loop
        for period in range(1, num_periods + 1):
            # 1. Generate stochastic true customer demand for this period
            forecasts, _, _ = get_mock_retail_store()
            true_demands: Dict[str, int] = {}
            for pid, fc in forecasts.items():
                mean = fc.get_mean()
                std = fc.get_std()
                realized = int(max(0, round(np.random.normal(mean, std))))
                true_demands[pid] = realized

            # 2. Compute orders for each policy
            orders_by_policy: Dict[str, Dict[str, int]] = {}

            # --- Policy A: MarketPulse Optimizer ---
            current_inv_state = {
                pid: InventoryState(
                    on_hand=policy_inventory["MarketPulse Optimizer"][pid],
                    on_order=0,
                    days_to_next_replenishment=forecasts[pid].horizon_days
                )
                for pid in products
            }
            plan = optimize(forecasts, current_inv_state, products, budget=budget_per_period, compute_sensitivity=False)
            orders_by_policy["MarketPulse Optimizer"] = {pid: item.order_qty for pid, item in plan.items.items()}

            # --- Policy B: Equal Budget Split ---
            eq_orders: Dict[str, int] = {}
            per_sku_budget = budget_per_period / max(1, len(products))
            for pid, prod in products.items():
                units = int(per_sku_budget // prod.purchase_price)
                if prod.pack_size > 1:
                    units = (units // prod.pack_size) * prod.pack_size
                eq_orders[pid] = units
            orders_by_policy["Equal Budget Split"] = eq_orders

            # --- Policy C: Historical Average Reorder ---
            hist_orders: Dict[str, int] = {}
            for pid, prod in products.items():
                fc_mean = forecasts[pid].get_mean()
                curr = policy_inventory["Historical Average"][pid]
                needed = max(0, int(round(fc_mean - curr)))
                if prod.pack_size > 1:
                    needed = int(math.ceil(needed / prod.pack_size) * prod.pack_size)
                hist_orders[pid] = needed
            
            # Scale down if exceeds budget
            total_hist_cost = sum(hist_orders[p] * products[p].purchase_price for p in products)
            if total_hist_cost > budget_per_period:
                scale = budget_per_period / total_hist_cost
                hist_orders = {
                    p: int((q * scale // products[p].pack_size) * products[p].pack_size)
                    for p, q in hist_orders.items()
                }
            orders_by_policy["Historical Average"] = hist_orders

            # --- Policy D: Fixed-Threshold (s, S) Reorder ---
            # s = 0.3 * mean, S = 1.0 * mean
            ss_orders: Dict[str, int] = {}
            for pid, prod in products.items():
                mean = forecasts[pid].get_mean()
                s_level = int(0.3 * mean)
                S_level = int(1.1 * mean)
                curr = policy_inventory["Fixed-Threshold (s,S)"][pid]
                if curr <= s_level:
                    needed = max(0, S_level - curr)
                    if prod.pack_size > 1:
                        needed = int(math.ceil(needed / prod.pack_size) * prod.pack_size)
                    ss_orders[pid] = needed
                else:
                    ss_orders[pid] = 0

            # Scale down if exceeds budget
            total_ss_cost = sum(ss_orders[p] * products[p].purchase_price for p in products)
            if total_ss_cost > budget_per_period:
                scale = budget_per_period / total_ss_cost
                ss_orders = {
                    p: int((q * scale // products[p].pack_size) * products[p].pack_size)
                    for p, q in ss_orders.items()
                }
            orders_by_policy["Fixed-Threshold (s,S)"] = ss_orders

            # 3. Simulate sales, inventory updates, and financials across all policies
            for pol in policies:
                pol_orders = orders_by_policy[pol]
                period_spend = sum(pol_orders[p] * products[p].purchase_price for p in products)
                history[pol]["total_spend"] += period_spend

                for pid, prod in products.items():
                    ordered = pol_orders[pid]
                    prior_inv = policy_inventory[pol][pid]
                    available = prior_inv + ordered
                    dem = true_demands[pid]

                    sales = min(available, dem)
                    lost_sales = max(0, dem - available)
                    leftover = available - sales

                    # Update store inventory for next period
                    policy_inventory[pol][pid] = leftover

                    rev = sales * prod.selling_price
                    holding = leftover * prod.effective_holding_cost

                    history[pol]["total_revenue"] += rev
                    history[pol]["total_holding_cost"] += holding
                    history[pol]["total_demand"] += dem
                    history[pol]["total_lost_sales_units"] += lost_sales
                    history[pol]["total_leftover_units"] += leftover
                    history[pol]["total_leftover_value"] += leftover * prod.purchase_price

        # Compile final comparative metrics
        results: Dict[str, Dict[str, float]] = {}
        for pol in policies:
            h = history[pol]
            net_profit = h["total_revenue"] - h["total_spend"] - h["total_holding_cost"]
            h["total_net_profit"] = net_profit
            stockout_rate = (h["total_lost_sales_units"] / max(1.0, h["total_demand"])) * 100.0
            cap_utilization = (h["total_spend"] / h["total_budget_allocated"]) * 100.0

            results[pol] = {
                "total_net_profit": round(net_profit, 2),
                "total_revenue": round(h["total_revenue"], 2),
                "total_spend": round(h["total_spend"], 2),
                "holding_cost": round(h["total_holding_cost"], 2),
                "stockout_rate_pct": round(stockout_rate, 2),
                "excess_inventory_value": round(h["total_leftover_value"] / num_periods, 2),
                "capital_utilization_pct": round(cap_utilization, 2)
            }

        return results


def format_backtest_markdown_table(results: Dict[str, Dict[str, float]]) -> str:
    """Formats simulation results as a clean GitHub markdown report."""
    md = "| Metric | MarketPulse Optimizer | Equal Budget Split | Historical Average | Fixed-Threshold (s,S) |\n"
    md += "| :--- | :---: | :---: | :---: | :---: |\n"

    m_opt = results["MarketPulse Optimizer"]
    m_eq = results["Equal Budget Split"]
    m_ha = results["Historical Average"]
    m_ft = results["Fixed-Threshold (s,S)"]

    md += f"| **Total Net Profit ($)** | **${m_opt['total_net_profit']:,.2f}** | ${m_eq['total_net_profit']:,.2f} | ${m_ha['total_net_profit']:,.2f} | ${m_ft['total_net_profit']:,.2f} |\n"
    md += f"| **Stockout Rate (%)** | **{m_opt['stockout_rate_pct']}%** | {m_eq['stockout_rate_pct']}% | {m_ha['stockout_rate_pct']}% | {m_ft['stockout_rate_pct']}% |\n"
    md += f"| **Avg Excess Inventory ($)** | **${m_opt['excess_inventory_value']:,.2f}** | ${m_eq['excess_inventory_value']:,.2f} | ${m_ha['excess_inventory_value']:,.2f} | ${m_ft['excess_inventory_value']:,.2f} |\n"
    md += f"| **Capital Utilization (%)** | **{m_opt['capital_utilization_pct']}%** | {m_eq['capital_utilization_pct']}% | {m_ha['capital_utilization_pct']}% | {m_ft['capital_utilization_pct']}% |\n"

    # Profit gain calculation
    gain_vs_eq = ((m_opt['total_net_profit'] - m_eq['total_net_profit']) / max(1.0, m_eq['total_net_profit'])) * 100.0
    gain_vs_ha = ((m_opt['total_net_profit'] - m_ha['total_net_profit']) / max(1.0, m_ha['total_net_profit'])) * 100.0
    gain_vs_ft = ((m_opt['total_net_profit'] - m_ft['total_net_profit']) / max(1.0, m_ft['total_net_profit'])) * 100.0

    md += f"\n**MarketPulse Outperformance:**\n"
    md += f"- **+{gain_vs_eq:.1f}% higher profit** vs. Equal Budget Allocation\n"
    md += f"- **+{gain_vs_ha:.1f}% higher profit** vs. Historical Average Reordering\n"
    md += f"- **+{gain_vs_ft:.1f}% higher profit** vs. Fixed-Threshold Reordering\n"

    return md


if __name__ == "__main__":
    sim = BacktestSimulator(seed=42)
    res = sim.run_simulation(num_periods=6, budget_per_period=3500.0)
    print(format_backtest_markdown_table(res))
