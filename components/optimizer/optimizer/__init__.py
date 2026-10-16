"""
MarketPulse AI - Inventory Optimization Engine (Component C)
"""
from .models import (
    Forecast,
    InventoryState,
    ProductMeta,
    ProductPlan,
    Plan,
    SensitivityPoint
)
from .engine import optimize, explain_inputs
from .baseline import compute_baseline_quantity, compute_safety_stock
from .newsvendor import compute_critical_ratio, compute_unconstrained_newsvendor_order

__all__ = [
    "Forecast",
    "InventoryState",
    "ProductMeta",
    "ProductPlan",
    "Plan",
    "SensitivityPoint",
    "optimize",
    "explain_inputs",
    "compute_baseline_quantity",
    "compute_safety_stock",
    "compute_critical_ratio",
    "compute_unconstrained_newsvendor_order"
]
