# Cost and Constraint Model Documentation

**Component C: Inventory Optimization Engine**  
**MarketPulse AI**

---

## 1. Executive Summary

This document formalizes the mathematical equations, economic parameters, and operational constraints implemented in the MarketPulse AI inventory optimization engine. 

In strict adherence to the project's core principle:
> **"Machine learning estimates demand. Optimization decides purchases. The language model translates and explains."**

The optimizer solves a multi-item, budget-constrained Newsvendor problem over discrete integer order batches, allocating working capital to maximize total store profit while mitigating stockout risk and dead inventory.

---

## 2. Core Economic Formulation

### 2.1 The Newsvendor Cost Model

For each product $i$, purchasing an extra unit creates asymmetric financial risks:

1. **Underage Cost ($C_u$):** The opportunity cost of having 1 unit too few when demand occurs (lost gross margin):
   $$C_{u, i} = p_i - c_i$$
   Where:
   - $p_i$ is the retail selling price.
   - $c_i$ is the wholesale purchase price.

2. **Overage Cost ($C_o$):** The cost of having 1 unit too many remaining unsold at the end of the planning cycle:
   $$C_{o, i} = c_i - s_i + h_i$$
   Where:
   - $s_i$ is the salvage or liquidation value per unsold unit (default: $0.0$).
   - $h_i$ is the per-cycle carrying/holding cost (cost of working capital, shelf occupancy, deterioration).

#### Explicit Assumption on Holding Cost
If holding cost is unstated in the catalog, it is assumed as:
$$h_i = 0.05 \times c_i$$
*(Assumption: 5% cost of capital and shrinkage per planning cycle).*

### 2.2 Optimal Unconstrained Service Level (Critical Ratio)

By marginal economic analysis, the optimal target inventory position $y_i^*$ satisfies:
$$P(D_i \le y_i^*) = CR_i = \frac{C_{u, i}}{C_{u, i} + C_{o, i}} = \frac{p_i - c_i}{(p_i - c_i) + (c_i - s_i + h_i)}$$

Given forecast cumulative distribution $F_i(x)$ over protection interval $(L_i + R_i)$:
$$y_i^* = F_i^{-1}(CR_i)$$

For normal demand $D_i \sim \mathcal{N}(\mu_i, \sigma_i^2)$:
$$y_i^* = \mu_i + z_{CR_i} \cdot \sigma_i, \quad z_{CR_i} = \Phi^{-1}(CR_i)$$

- When $CR_i > 0.5$ (high margin item), $z > 0 \implies y^* > \mu$.
- When $CR_i < 0.5$ (low margin item), $z < 0 \implies y^* < \mu$.

### 2.3 Expected Profit and Loss Functions

For target inventory level $y_i = I_{usable, i} + P_{on\_order, i} + Q_i$:
- Standardized score: $z_i = \frac{y_i - \mu_i}{\sigma_i}$
- Expected leftover units:
  $$\mathbb{E}[(y_i - D_i)^+] = (y_i - \mu_i)\Phi(z_i) + \sigma_i \phi(z_i)$$
- Expected units sold:
  $$\mathbb{E}[\min(y_i, D_i)] = y_i - \mathbb{E}[(y_i - D_i)^+]$$
- Expected stockout probability:
  $$P(\text{Stockout}) = 1 - \Phi(z_i)$$
- Expected cycle net profit:
  $$\Pi_i(Q_i) = p_i \cdot \mathbb{E}[\text{Sales}_i] + s_i \cdot \mathbb{E}[\text{Leftover}_i] - c_i \cdot Q_i - h_i \cdot \mathbb{E}[\text{Leftover}_i]$$

---

## 3. Operational Constraints

### 3.1 Hard Working Capital (Budget) Constraint
The total expenditure across all purchase orders cannot exceed the retailer's cash budget $B$:
$$\sum_{i=1}^N c_i \cdot Q_i \le B$$

### 3.2 Storage Volume Capacity
Total space occupied on shelves or in backroom cannot exceed maximum store capacity $V_{\max}$:
$$\sum_{i=1}^N v_i \cdot Q_i \le V_{\max}$$
Where $v_i$ is the unit volume or shelf footprint index.

### 3.3 Supplier MOQ & Pack Sizes
Suppliers do not deliver fractional or sub-pack quantities:
$$Q_i = 0 \quad \text{OR} \quad \left( Q_i \ge \text{MOQ}_i \quad \text{AND} \quad Q_i \equiv 0 \pmod{\text{pack\_size}_i} \right)$$

### 3.4 Expiry & Shelf-Life Cap
For perishable items with shelf-life $E_i$ days, the order is strictly bounded by maximum sellable demand before expiration:
$$Q_i + I_{usable, i} \le \text{MaxDemandUntilExpiry}(E_i) \approx \frac{\mu_i}{H} E_i + 1.282 \frac{\sigma_i}{\sqrt{H}}\sqrt{E_i}$$

---

## 4. Optimization Algorithms

1. **Greedy Marginal Knapsack (Primary Production Engine):**
   - At each iteration, evaluates all products for the next valid pack increment $\Delta Q_i$.
   - Selects the SKU with the highest positive marginal return on capital:
     $$\text{ROI} = \frac{\Delta \Pi_i}{\Delta C_i} = \frac{\Pi_i(Q_i + \Delta Q_i) - \Pi_i(Q_i)}{c_i \cdot \Delta Q_i}$$
   - Haircuts or penalizes high-uncertainty items when variance exceeds safety thresholds.
   - Halts when remaining budget cannot accommodate any valid pack size with $\text{ROI} > 0$.

2. **Mixed-Integer Linear Programming (MILP Benchmark):**
   - Solved using `scipy.optimize.milp` over discrete piecewise-linear candidate steps.
   - Used in the test harness to guarantee that the greedy solution achieves $\ge 90\%$ of the theoretical mathematical ceiling.
