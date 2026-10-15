# Shared Contract: Component C (Inventory Optimization Engine)

This document formalizes the exact input/output data contracts, function signatures, and JSON schemas for **Component C (Inventory Optimization Engine)** in MarketPulse AI.

- **Author / Owner:** Member 3 (Inventory Optimization Engine)
- **Consumers:** Member 4 (AI Grounded Explainer), Member 5 (API / Frontend)
- **Providers:** Member 1 (Product / Cost Catalog), Member 2 (Demand Forecasting Engine)

---

## 1. Primary Entry-Point Signatures

```python
def optimize(
    forecasts: dict[str, Forecast],
    inventory: dict[str, InventoryState],
    products: dict[str, ProductMeta],
    budget: float,
    max_storage_volume: Optional[float] = None
) -> Plan:
    """
    Computes a budget-constrained purchasing plan using Newsvendor marginal economics.
    """
    ...

def explain_inputs(plan: Plan) -> dict:
    """
    Extracts structured, deterministic facts and reasoning codes from the Plan
    that Member 4's LLM will narrate to the retailer without doing math.
    """
    ...
```

---

## 2. Input Contracts (Consumed from Members 1 & 2)

### A. `Forecast` (from Member 2)
```json
{
  "p10": 12.0,
  "p50": 30.0,
  "p90": 58.0,
  "mean": 32.5,
  "std": 14.2,
  "horizon_days": 14
}
```
*Fields:*
* `p10` (*float, required*): 10th percentile of cumulative demand over horizon.
* `p50` (*float, required*): Median forecast demand.
* `p90` (*float, required*): 90th percentile of cumulative demand.
* `mean` (*float, optional*): Expected value (if omitted, estimated from quantiles).
* `std` (*float, optional*): Standard deviation (if omitted, estimated via $(p90 - p10) / 2.56$).
* `horizon_days` (*int, default: 14*): Forecast planning horizon in days.

### B. `InventoryState` (from Retailer / Member 1)
```json
{
  "on_hand": 15,
  "on_order": 5,
  "expired_stock": 2,
  "days_to_next_replenishment": 7
}
```
*Fields:*
* `on_hand` (*int, required*): Physical units currently in shop.
* `on_order` (*int, default: 0*): Units already placed with supplier, in transit.
* `expired_stock` (*int, default: 0*): Damaged or expired units (excluded from usable stock).
* `days_to_next_replenishment` (*int, default: 7*): Time until the subsequent ordering cycle.

### C. `ProductMeta` (from Member 1 Catalog)
```json
{
  "product_id": "SKU_MILK_1L",
  "name": "Fresh Whole Milk 1L",
  "category": "Dairy",
  "purchase_price": 1.20,
  "selling_price": 1.80,
  "holding_cost": 0.05,
  "salvage_value": 0.20,
  "lead_time_days": 2,
  "min_order_qty": 6,
  "pack_size": 6,
  "unit_volume": 1.0,
  "shelf_life_days": 10
}
```
*Fields:*
* `product_id` (*str, required*): Unique product identifier.
* `name` (*str, required*): Human-readable name.
* `category` (*str, optional*): Product category.
* `purchase_price` (*float, required*): Supplier unit wholesale cost ($c_i$).
* `selling_price` (*float, required*): Retail sale price ($p_i$).
* `holding_cost` (*float, optional*): Cost of carrying unsold stock per cycle (default: $0.05 \times c_i$).
* `salvage_value` (*float, optional*): Residual recovery per unsold unit (default: $0.0$).
* `lead_time_days` (*int, default: 0*): Supplier transit days.
* `min_order_qty` (*int, default: 1*): Supplier minimum order quantity (MOQ).
* `pack_size` (*int, default: 1*): Ordering multiple (e.g. 6-pack, box of 12).
* `unit_volume` (*float, default: 1.0*): Relative shelf space footprint per unit.
* `shelf_life_days` (*int, optional*): Maximum days before expiry (None if non-perishable).

---

## 3. Output Contract: `Plan` (Delivered to Members 4 & 5)

```json
{
  "total_cost": 2980.50,
  "budget": 3000.00,
  "budget_used": 2980.50,
  "budget_remaining": 19.50,
  "total_expected_profit": 842.20,
  "total_items_ordered": 482,
  "binding_constraints": ["BUDGET"],
  "items": {
    "SKU_MILK_1L": {
      "product_id": "SKU_MILK_1L",
      "name": "Fresh Whole Milk 1L",
      "order_qty": 48,
      "cost": 57.60,
      "unit_cost": 1.20,
      "unit_price": 1.80,
      "expected_profit": 26.40,
      "expected_stockout_prob": 0.12,
      "expected_leftover": 3.4,
      "critical_ratio": 0.86,
      "binding_constraints": ["PACK_SIZE"],
      "reason_codes": ["ALLOCATED_HIGH_MARGIN", "PACK_SIZE_ROUNDED"],
      "uncertainty_flag": false,
      "relative_uncertainty": 0.65
    },
    "SKU_EXOTIC_SPICE": {
      "product_id": "SKU_EXOTIC_SPICE",
      "name": "Saffron Spice 5g",
      "order_qty": 0,
      "cost": 0.00,
      "unit_cost": 18.00,
      "unit_price": 24.00,
      "expected_profit": 0.00,
      "expected_stockout_prob": 0.85,
      "expected_leftover": 0.0,
      "critical_ratio": 0.45,
      "binding_constraints": ["BUDGET"],
      "reason_codes": ["DROPPED_HIGH_UNCERTAINTY", "LOW_CAPITAL_EFFICIENCY"],
      "uncertainty_flag": true,
      "relative_uncertainty": 2.10
    }
  },
  "sensitivity": {
    "100_percent": {
      "budget_level": "100%",
      "budget_amount": 3000.00,
      "total_cost": 2980.50,
      "total_expected_profit": 842.20,
      "items_ordered_count": 14
    },
    "80_percent": {
      "budget_level": "80%",
      "budget_amount": 2400.00,
      "total_cost": 2390.00,
      "total_expected_profit": 718.50,
      "items_ordered_count": 11
    },
    "60_percent": {
      "budget_level": "60%",
      "budget_amount": 1800.00,
      "total_cost": 1785.00,
      "total_expected_profit": 572.10,
      "items_ordered_count": 8
    }
  }
}
```

---

## 4. `explain_inputs(plan)` Output (For Member 4 Grounded Explainer)

```json
{
  "summary": {
    "budget": 3000.00,
    "total_spend": 2980.50,
    "expected_profit": 842.20,
    "budget_utilization_pct": 99.35,
    "num_products_funded": 12,
    "num_products_dropped": 4
  },
  "top_allocations": [
    {
      "name": "Fresh Whole Milk 1L",
      "qty": 48,
      "spend": 57.60,
      "profit": 26.40,
      "reason": "High margin and reliable local demand; rounded up to pack size of 6."
    }
  ],
  "dropped_items": [
    {
      "name": "Saffron Spice 5g",
      "cost_to_order": 18.00,
      "reason_code": "DROPPED_HIGH_UNCERTAINTY",
      "explanation": "Demand uncertainty is 210% of median with high unit cost; omitted to protect cash flow."
    }
  ],
  "uncertainty_alerts": [
    {
      "name": "Saffron Spice 5g",
      "relative_uncertainty": 2.10,
      "note": "Forecast interval ranges from 2 to 25 units; requires external market validation before capital commitment."
    }
  ],
  "budget_bottleneck": "At $3,000 budget, 4 products could not be funded. Increasing budget by $600 captures an additional $123.70 in expected profit."
}
```

---

## 5. Standard Reason Codes

* `ALLOCATED_OPTIMAL`: Funded to unconstrained Newsvendor optimal quantity.
* `ALLOCATED_TRIMMED_BUDGET`: Quantity reduced below unconstrained optimum due to budget cap.
* `PACK_SIZE_ROUNDED`: Quantity adjusted to supplier pack size multiple.
* `MOQ_PROMOTED`: Quantity rounded up to supplier minimum order quantity.
* `DROPPED_BUDGET_EXHAUSTED`: Viable product omitted because available budget ran out.
* `DROPPED_HIGH_UNCERTAINTY`: Product dropped because uncertainty ratio exceeded conservative threshold.
* `DROPPED_LOW_CAPITAL_EFFICIENCY`: Expected profit per dollar lower than competing catalog items.
* `CAPPED_SHELF_LIFE`: Order quantity capped to prevent spoilage before expiry.
