"""
Example: End-to-End Integration Demo for Member 3 (Inventory Optimizer).
Shows how Member 3 imports and calls forecast(), extracts demand quantiles,
computes optimal newsvendor order quantities, and adjusts for active shocks.
"""

import sys
from pathlib import Path

# Add project root to path if running directly from script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forecasting.api import forecast


def run_optimizer_handoff_demo():
    print("================================================================")
    print("  MarketPulse AI: Member 2 -> Member 3 (Optimizer) Integration  ")
    print("================================================================\n")

    store_id = "STORE_001"
    target_products = ["PROD_MILK_1L", "PROD_BREAD", "PROD_COOKING_OIL_1L"]
    horizon_days = 14

    print(f"1. Calling forecast() for Store: {store_id}, Horizon: {horizon_days} days...")
    # Primary API contract call
    df_forecast = forecast(
        store_id=store_id,
        product_ids=target_products,
        horizon_days=horizon_days,
        grid_step=0.05
    )

    print("\n2. Forecast DataFrame Schema received by Optimizer:")
    print(df_forecast[["store_id", "product_id", "p10", "p50", "p90", "shock_active", "widening_factor"]])

    print("\n3. Calculating Inventory Optimizer Quantities (Newsvendor Example):")
    # Simulate current stock and cost parameters for each product
    inventory_state = {
        "PROD_MILK_1L": {"on_hand": 15, "cost": 1.20, "price": 2.00},
        "PROD_BREAD": {"on_hand": 8, "cost": 0.80, "price": 1.50},
        "PROD_COOKING_OIL_1L": {"on_hand": 5, "cost": 3.00, "price": 4.50},
    }

    for _, row in df_forecast.iterrows():
        pid = row["product_id"]
        inv = inventory_state.get(pid, {"on_hand": 0, "cost": 1.0, "price": 2.0})

        # Newsvendor critical fractile: cu / (cu + co)
        # cu: underage cost (lost profit = price - cost)
        # co: overage cost (spoilage / holding = cost)
        cu = inv["price"] - inv["cost"]
        co = inv["cost"]
        critical_fractile = cu / (cu + co)

        # Select closest quantile from 5% grid dictionary
        grid_key = f"q{int(round(critical_fractile * 20) * 5):02d}"
        q_star_demand = row["quantiles"].get(grid_key, row["p50"])

        # Recommended order quantity: Q = max(0, Q* - OnHand)
        recommended_order = max(0, int(round(q_star_demand - inv["on_hand"])))

        print(f"\nProduct: {pid}")
        print(f"  - On Hand: {inv['on_hand']} units")
        print(f"  - Demand Quantiles: p10={row['p10']}, p50={row['p50']}, p90={row['p90']}")
        print(f"  - Critical Fractile (Service Level Target): {critical_fractile:.2f} (mapped to {grid_key})")
        print(f"  - Target Inventory at fractile: {q_star_demand:.1f} units")
        print(f"  - Recommended Order (Q_i): {recommended_order} units")
        if row["shock_active"]:
            print(f"  - WARNING: Shock active! Intervals widened by {row['widening_factor']}x")

    print("\nDONE: Forecast output seamlessly integrated with Optimizer logic!")


if __name__ == "__main__":
    run_optimizer_handoff_demo()
