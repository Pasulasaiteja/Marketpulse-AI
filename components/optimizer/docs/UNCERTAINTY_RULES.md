# Uncertainty-Flag Rules Documentation

**Component C: Inventory Optimization Engine**  
**MarketPulse AI**

---

## 1. Principle & Motivation

In low-margin small retail, **uncertainty is asymmetric**:
- If demand is higher than predicted, the retailer experiences a lost opportunity (missed sale).
- If demand is lower than predicted on an expensive, slow-moving item, the retailer suffers **trapped cash flow and dead inventory**, which frequently causes business failure.

MarketPulse AI enforces explicit mathematical criteria to flag high-uncertainty items and prevent reckless allocation of scarce working capital.

---

## 2. Mathematical Definition of Relative Uncertainty

Given Member 2's demand forecast quantiles:
- $p_{10}$: 10th percentile (low demand scenario)
- $p_{50}$: 50th percentile (median demand scenario)
- $p_{90}$: 90th percentile (high demand scenario)

The **Relative Uncertainty Ratio ($RU_i$)** is defined as the inter-decile spread normalized by median demand:

$$RU_i = \frac{p_{90, i} - p_{10, i}}{\max(1.0, p_{50, i})}$$

### Interpretation:
* $RU_i < 0.6$: **Low Uncertainty** (Predictable staple, e.g. milk, bread, rice).
* $0.6 \le RU_i \le 1.25$: **Moderate Uncertainty** (Standard retail items, weather/seasonality dependent).
* $RU_i > 1.25$: **High Uncertainty** (Specialty products, unproven new SKUs, speculative items).

---

## 3. Decision Rules Under High Uncertainty

When $RU_i > 1.25$:

### Rule 1: Flagging and Reason Code
* Set `uncertainty_flag = True`.
* Emit reason code `HIGH_DEMAND_VARIANCE`.
* Surface warning in `explain_inputs(plan)["uncertainty_alerts"]`.

### Rule 2: Target Service Level Haircut (De-risking)
* Instead of ordering up to the theoretical Newsvendor quantile $F^{-1}(CR_i)$ (which could reach $p_{85}$ or $p_{90}$ for high margin goods), the target service level is capped at the median ($p_{50}$):
  $$CR_{\text{effective}, i} = \min(0.50, CR_i)$$
* **Theoretical Rationale:** An unproven or volatile item should not be stocked for optimistic upside when capital is constrained.

### Rule 3: Capital Allocation Priority Discount
* In the greedy marginal ROI knapsack, the marginal profit of high-uncertainty increments is discounted by 15%:
  $$\Delta \Pi_{\text{effective}} = 0.85 \times \Delta \Pi$$
* **Impact:** High-confidence staple goods (bread, milk, eggs, rice) always receive capital first. High-uncertainty items are only funded if surplus budget remains after fully securing core inventory.

### Rule 4: Drop Threshold
* If remaining capital after funding staple goods is insufficient to order the minimum pack/MOQ of the volatile item, the item is dropped completely with reason code:
  `DROPPED_HIGH_UNCERTAINTY`
* Member 4's LLM translates this to the retailer as:  
  *"Demand uncertainty for [Product] is high ([X]% variance) with high unit cost; omitted to protect cash flow."*

---

## 4. Verification in Test Suite

This behavior is tested and guaranteed in `tests/test_optimizer.py`:
- `test_high_uncertainty_handling`: Verifies that a high-variance SKU ($RU = 4.64$) is flagged and dropped under tight capital constraints, while low-uncertainty staples are prioritized.
