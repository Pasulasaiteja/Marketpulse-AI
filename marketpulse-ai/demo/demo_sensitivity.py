"""
Demo Script: Budget Sensitivity 5,000 vs 3,000 (Deliverable 4)

Runs MarketPulse Optimizer at $5,000 budget and $3,000 budget,
prints the exact comparative trade-offs, and exports output_5k_vs_3k.json
for Member 4 (Explainer) and Member 5 (Dashboard UI).
"""
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from optimizer import optimize, explain_inputs
from mocks.mock_data import get_mock_retail_store


def run_demo_comparison():
    forecasts, inventory, products = get_mock_retail_store()

    print("================================================================================")
    print("      MARKETPULSE AI: BUDGET SENSITIVITY DEMO ($5,000 vs. $3,000)")
    print("================================================================================")

    # 1. Optimize at $5,000
    plan_5k = optimize(forecasts, inventory, products, budget=5000.0)
    facts_5k = explain_inputs(plan_5k)

    # 2. Optimize at $3,000
    plan_3k = optimize(forecasts, inventory, products, budget=3000.0)
    facts_3k = explain_inputs(plan_3k)

    print(f"\n[SCENARIO 1: Full Budget $5,000]")
    print(f"Total Spend:            ${plan_5k.total_cost:,.2f} / $5,000.00")
    print(f"Expected Profit:        ${plan_5k.total_expected_profit:,.2f}")
    print(f"Total Units Ordered:    {plan_5k.total_items_ordered} units across {facts_5k['summary']['num_products_funded']} products")
    print(f"Products Dropped:       {facts_5k['summary']['num_products_dropped']}")

    print(f"\n[SCENARIO 2: Reduced Budget $3,000]")
    print(f"Total Spend:            ${plan_3k.total_cost:,.2f} / $3,000.00")
    print(f"Expected Profit:        ${plan_3k.total_expected_profit:,.2f}")
    print(f"Total Units Ordered:    {plan_3k.total_items_ordered} units across {facts_3k['summary']['num_products_funded']} products")
    print(f"Products Dropped:       {facts_3k['summary']['num_products_dropped']}")

    # 3. Item-by-item trade-off table
    print("\n--------------------------------------------------------------------------------")
    print(f"{'Product Name':<30} | {'Qty @ $5k':<10} | {'Qty @ $3k':<10} | {'Action Under $3k Budget'}")
    print("--------------------------------------------------------------------------------")

    trade_offs = []
    for pid, prod in products.items():
        q_5k = plan_5k.items[pid].order_qty
        q_3k = plan_3k.items[pid].order_qty

        if q_5k > 0 and q_3k == 0:
            action = "DROPPED (Capital preserved for staples)"
        elif q_5k > q_3k:
            action = f"TRIMMED by {q_5k - q_3k} units"
        elif q_5k == q_3k and q_5k > 0:
            action = "PROTECTED (Core bread-and-butter item)"
        else:
            action = "UNFUNDED"

        print(f"{prod.name:<30} | {q_5k:<10} | {q_3k:<10} | {action}")
        trade_offs.append({
            "product_id": pid,
            "name": prod.name,
            "qty_5k": q_5k,
            "cost_5k": plan_5k.items[pid].cost,
            "qty_3k": q_3k,
            "cost_3k": plan_3k.items[pid].cost,
            "status_change": action
        })

    print("--------------------------------------------------------------------------------")
    profit_diff = plan_5k.total_expected_profit - plan_3k.total_expected_profit
    print(f"\nFINANCIAL IMPACT: A $2,000 budget reduction lowers expected gross profit by ${profit_diff:,.2f}.")
    print("Notice how the optimizer automatically prioritizes fast-turning staples (Milk, Bread, Rice, Oil)")
    print("and sheds high-risk or lower-turnover inventory without human guesswork.")

    # 4. Save structured JSON for Members 4 & 5
    demo_output = {
        "scenario_5k": {
            "plan": plan_5k.to_dict(),
            "facts": facts_5k
        },
        "scenario_3k": {
            "plan": plan_3k.to_dict(),
            "facts": facts_3k
        },
        "trade_offs": trade_offs,
        "executive_summary": {
            "profit_difference": round(profit_diff, 2),
            "units_difference": plan_5k.total_items_ordered - plan_3k.total_items_ordered,
            "protected_staples": [t["name"] for t in trade_offs if "PROTECTED" in t["status_change"]],
            "dropped_items": [t["name"] for t in trade_offs if "DROPPED" in t["status_change"]]
        }
    }

    out_path = PROJECT_ROOT / "demo" / "output_5k_vs_3k.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(demo_output, f, indent=2)

    print(f"\n[Saved full comparison JSON to: {out_path}]")


if __name__ == "__main__":
    run_demo_comparison()
