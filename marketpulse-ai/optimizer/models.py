from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import math


@dataclass
class Forecast:
    """
    Demand forecast distribution for a given planning horizon.
    Supplied by Member 2.
    """
    p10: float
    p50: float
    p90: float
    mean: Optional[float] = None
    std: Optional[float] = None
    horizon_days: int = 14

    def get_mean(self) -> float:
        """Estimate mean from quantiles using modified PERT if unprovided."""
        if self.mean is not None:
            return float(self.mean)
        return (self.p10 + 4.0 * self.p50 + self.p90) / 6.0

    def get_std(self) -> float:
        """
        Estimate std from 80% inter-decile range: z_0.90 ≈ 1.28155, range = 2.5631 * std.
        """
        if self.std is not None and self.std > 0:
            return float(self.std)
        spread = max(0.01, self.p90 - self.p10)
        return spread / 2.5631

    def relative_uncertainty(self) -> float:
        """
        Relative uncertainty ratio: (p90 - p10) / max(1.0, p50).
        High values (> 1.25) indicate wide variance and high risk.
        """
        denom = max(1.0, self.p50)
        return max(0.0, (self.p90 - self.p10) / denom)


@dataclass
class InventoryState:
    """
    Current stock status for a product.
    """
    on_hand: float = 0.0
    on_order: float = 0.0
    expired_stock: float = 0.0
    days_to_next_replenishment: int = 7

    @property
    def usable_on_hand(self) -> float:
        """Physical inventory minus damaged or expired items."""
        return max(0.0, float(self.on_hand) - float(self.expired_stock))

    @property
    def net_effective_inventory(self) -> float:
        """Total stock already available or committed in transit."""
        return self.usable_on_hand + float(self.on_order)



@dataclass
class ProductMeta:
    """
    Catalog, pricing, supply, and physical parameters for a product.
    Supplied by Member 1.
    """
    product_id: str
    name: str
    category: str = "General"
    purchase_price: float = 1.0
    selling_price: float = 1.5
    holding_cost: Optional[float] = None
    salvage_value: float = 0.0
    lead_time_days: int = 0
    min_order_qty: int = 1
    pack_size: int = 1
    unit_volume: float = 1.0
    shelf_life_days: Optional[int] = None

    @property
    def margin(self) -> float:
        """Gross margin per unit."""
        return self.selling_price - self.purchase_price

    @property
    def effective_holding_cost(self) -> float:
        """
        Cost of capital & storage for holding unsold unit over planning cycle.
        Assumption: 5% of wholesale cost if unstated.
        """
        if self.holding_cost is not None:
            return max(0.0, self.holding_cost)
        return max(0.01, 0.05 * self.purchase_price)

    @property
    def underage_cost(self) -> float:
        """Cost of stocking 1 unit too few: lost profit margin."""
        return max(0.01, self.margin)

    @property
    def overage_cost(self) -> float:
        """
        Cost of stocking 1 unit too many: wholesale cost - salvage + holding cost.
        """
        net_loss = self.purchase_price - self.salvage_value
        return max(0.01, net_loss + self.effective_holding_cost)

    @property
    def critical_ratio(self) -> float:
        """
        Newsvendor optimal service level fractile: Cu / (Cu + Co).
        Always in (0, 1).
        """
        cu = self.underage_cost
        co = self.overage_cost
        return cu / (cu + co)


@dataclass
class ProductPlan:
    """
    Optimization result and recommendation metrics for a single product.
    """
    product_id: str
    name: str
    order_qty: int
    cost: float
    unit_cost: float
    unit_price: float
    expected_profit: float
    expected_stockout_prob: float
    expected_leftover: float
    critical_ratio: float
    binding_constraints: List[str] = field(default_factory=list)
    reason_codes: List[str] = field(default_factory=list)
    uncertainty_flag: bool = False
    relative_uncertainty: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "product_id": self.product_id,
            "name": self.name,
            "order_qty": int(self.order_qty),
            "cost": round(self.cost, 2),
            "unit_cost": round(self.unit_cost, 2),
            "unit_price": round(self.unit_price, 2),
            "expected_profit": round(self.expected_profit, 2),
            "expected_stockout_prob": round(self.expected_stockout_prob, 4),
            "expected_leftover": round(self.expected_leftover, 2),
            "critical_ratio": round(self.critical_ratio, 4),
            "binding_constraints": self.binding_constraints,
            "reason_codes": self.reason_codes,
            "uncertainty_flag": self.uncertainty_flag,
            "relative_uncertainty": round(self.relative_uncertainty, 4),
        }


@dataclass
class SensitivityPoint:
    """
    Summary metrics at a specific budget scaling level.
    """
    budget_level: str
    budget_amount: float
    total_cost: float
    total_expected_profit: float
    items_ordered_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "budget_level": self.budget_level,
            "budget_amount": round(self.budget_amount, 2),
            "total_cost": round(self.total_cost, 2),
            "total_expected_profit": round(self.total_expected_profit, 2),
            "items_ordered_count": self.items_ordered_count,
        }


@dataclass
class Plan:
    """
    Complete store-level purchasing plan output.
    """
    total_cost: float
    budget: float
    budget_used: float
    budget_remaining: float
    total_expected_profit: float
    total_items_ordered: int
    items: Dict[str, ProductPlan] = field(default_factory=dict)
    binding_constraints: List[str] = field(default_factory=list)
    sensitivity: Dict[str, SensitivityPoint] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_cost": round(self.total_cost, 2),
            "budget": round(self.budget, 2),
            "budget_used": round(self.budget_used, 2),
            "budget_remaining": round(self.budget_remaining, 2),
            "total_expected_profit": round(self.total_expected_profit, 2),
            "total_items_ordered": int(self.total_items_ordered),
            "binding_constraints": self.binding_constraints,
            "items": {pid: item.to_dict() for pid, item in self.items.items()},
            "sensitivity": {k: v.to_dict() for k, v in self.sensitivity.items()},
        }
