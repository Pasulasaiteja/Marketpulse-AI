"""MarketPulse AI shared contracts (schema_version 1.0).

Single source of truth for every module boundary. JSON Schemas in
``contracts/schemas/`` are generated from these models
(``python scripts/export_schemas.py``); a test fails if they drift.

Conventions
-----------
* ``extra="forbid"`` everywhere: unknown or misspelled fields fail validation.
* Money is in the shop's currency, 2 decimals. Quantities are non-negative.
* Dates are ISO 8601 (YYYY-MM-DD).
* The LLM never produces numbers in these contracts. Forecast numbers come
  from the forecaster, purchase numbers from the optimizer.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from marketpulse import config

SchemaVersion = Literal["1.0"]
Prob = Annotated[float, Field(ge=0.0, le=1.0)]
NonNeg = Annotated[float, Field(ge=0.0)]
LangCode = Annotated[str, Field(pattern=r"^[a-z]{2}$")]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ===========================================================================
# 1. EXTRACTION PROFILE  (producer: extraction module; consumers: API, context)
# ===========================================================================
LocationType = Literal["urban_dense", "urban", "peri_urban", "rural", "unknown"]
IncomeBand = Literal["low", "lower_middle", "middle", "upper", "unknown"]
AnchorType = Literal[
    "school",
    "market",
    "transport_hub",
    "place_of_worship",
    "hospital",
    "university",
    "office_district",
    "factory",
    "other",
]
ShopCategory = Literal[
    "grocery", "pharmacy", "general_store", "clothing", "electronics", "hardware", "other"
]

T = TypeVar("T")


class ProfileField(_Base, Generic[T]):
    """One extracted field. ``value`` is None when it could not be determined."""

    value: T | None = None
    confidence: Prob = 0.0
    source: Literal["llm", "retailer", "default"] = "llm"
    evidence: str | None = Field(
        default=None, description="Span of the original description supporting the value."
    )


class ProfileFields(_Base):
    location_type: ProfileField[LocationType]
    income_band: ProfileField[IncomeBand]
    payday_day: ProfileField[Annotated[int, Field(ge=1, le=31)]] = Field(
        description="Day of month wages are typically paid. 'End of the month' normalizes to 28."
    )
    nearby_anchors: ProfileField[list[AnchorType]]
    shop_category: ProfileField[ShopCategory]
    place_name: ProfileField[str]
    country: ProfileField[Annotated[str, Field(pattern=r"^[A-Z]{2}$")]] = Field(
        description="ISO 3166-1 alpha-2"
    )
    currency: ProfileField[Annotated[str, Field(pattern=r"^[A-Z]{3}$")]] = Field(
        description="ISO 4217"
    )


class FollowUpQuestion(_Base):
    field: str
    question: str = Field(description="Short question written in the retailer's language.")
    reason: Literal["missing", "low_confidence", "conflict"]


class FieldEdit(_Base):
    field: str
    old_value: Any = None
    new_value: Any = None


class ExtractionProfile(_Base):
    schema_version: SchemaVersion = "1.0"
    profile_id: str
    language: LangCode = Field(description="Detected language of the description.")
    raw_description: str
    status: Literal["extracted", "confirmed"] = "extracted"
    fields: ProfileFields
    follow_up_questions: list[FollowUpQuestion] = Field(default_factory=list)
    edits: list[FieldEdit] = Field(default_factory=list)


# ===========================================================================
# 2. CANONICAL DATA  (producer: API CSV loader; consumers: forecaster, optimizer)
# ===========================================================================
class Product(_Base):
    product_id: str
    name: str
    category: str | None = None
    unit_cost: NonNeg = Field(description="Purchase price per unit.")
    unit_price: NonNeg = Field(description="Selling price per unit.")
    current_stock: NonNeg = 0
    on_order: NonNeg = 0
    lead_time_days: int = Field(default=0, ge=0)
    min_order_qty: int = Field(default=1, ge=1)
    shelf_life_days: int | None = Field(default=None, ge=1)
    storage_units: NonNeg = Field(default=1.0, description="Storage space per unit.")


class SalesRecord(_Base):
    date: dt.date
    product_id: str
    units_sold: NonNeg
    revenue: NonNeg | None = None
    stockout: bool = Field(
        default=False, description="True if the product ran out that day (demand is censored)."
    )


class CanonicalData(_Base):
    schema_version: SchemaVersion = "1.0"
    shop_id: str
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    as_of: dt.date = Field(description="Last day of data. No record may be later.")
    storage_capacity_units: NonNeg | None = None
    products: list[Product]
    sales: list[SalesRecord]

    @model_validator(mode="after")
    def _check(self) -> CanonicalData:
        ids = [p.product_id for p in self.products]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate product_id in products")
        known = set(ids)
        for s in self.sales:
            if s.product_id not in known:
                raise ValueError(f"sales row references unknown product_id {s.product_id!r}")
            if s.date > self.as_of:
                raise ValueError(f"sales row dated {s.date} is after as_of {self.as_of} (leakage)")
        return self


# ===========================================================================
# 3. SIGNAL OUTPUT  (producer: Component A / Member 1; consumers: context, D)
# ===========================================================================
class Evidence(_Base):
    source: str
    ref: str | None = None
    date: dt.date | None = None
    summary: str | None = None


class Signal(_Base):
    signal_id: str
    type: Literal[
        "demand_shift",
        "unmet_demand",
        "category_growth",
        "price_change",
        "review_theme",
        "seasonality",
    ]
    product_id: str | None = None
    category: str | None = None
    direction: Literal["up", "down", "flat"]
    magnitude: float | None = Field(default=None, description="Relative change, e.g. 0.2 = +20%.")
    confidence: Prob
    predictive_value_established: bool = Field(
        default=False,
        description="True only if an ablation showed this signal lowers forecast error. "
        "Unvalidated signals must not move forecasts.",
    )
    observed: bool = Field(
        default=True, description="True if measured in data; False if inferred."
    )
    evidence: list[Evidence] = Field(default_factory=list)


class SignalOutput(_Base):
    schema_version: SchemaVersion = "1.0"
    generated_at: dt.date
    signals: list[Signal] = Field(default_factory=list)


# ===========================================================================
# 4. CONTEXT FEATURES  (producer: context step; consumer: forecaster)
# ===========================================================================
class ContextFeature(_Base):
    name: str
    value: float
    tier: Literal["calendar", "economic", "shock", "profile"]
    is_assumption: bool = Field(
        description="True if the value/effect is hand-set rather than learned or sourced."
    )
    source_available: bool = True
    fallback_used: bool = False


class ShockAlert(_Base):
    code: str
    description: str
    widen_interval_factor: float = Field(default=1.0, ge=1.0)


class ContextFeatures(_Base):
    schema_version: SchemaVersion = "1.0"
    as_of: dt.date
    horizon_days: int
    features: list[ContextFeature]
    alerts: list[ShockAlert] = Field(default_factory=list)

    @field_validator("horizon_days")
    @classmethod
    def _horizon(cls, v: int) -> int:
        if v not in config.HORIZONS_DAYS:
            raise ValueError(f"horizon_days must be one of {config.HORIZONS_DAYS}")
        return v


# ===========================================================================
# 5. FORECAST OUTPUT  (producer: forecaster; consumers: optimizer, explainer)
# ===========================================================================
class QuantilePoint(_Base):
    p: Prob
    value: NonNeg


class ProductForecast(_Base):
    product_id: str
    mean: NonNeg = Field(description="Expected units demanded over the horizon.")
    quantiles: list[QuantilePoint] = Field(
        description="Exactly the grid in config.QUANTILE_GRID, ascending, non-decreasing values."
    )
    history_days: int = Field(ge=0)
    low_data: bool = False
    cold_start: bool = False

    @model_validator(mode="after")
    def _check(self) -> ProductForecast:
        ps = tuple(round(q.p, 6) for q in self.quantiles)
        if ps != tuple(config.QUANTILE_GRID):
            raise ValueError(f"quantiles must be exactly {config.QUANTILE_GRID}, got {ps}")
        vals = [q.value for q in self.quantiles]
        if any(b < a for a, b in zip(vals, vals[1:], strict=False)):
            raise ValueError("quantile values must be non-decreasing")
        return self

    def quantile(self, p: float) -> float:
        """Linear interpolation on the grid (clamped at the ends)."""
        pts = self.quantiles
        if p <= pts[0].p:
            return pts[0].value
        if p >= pts[-1].p:
            return pts[-1].value
        for a, b in zip(pts, pts[1:], strict=False):
            if a.p <= p <= b.p:
                w = (p - a.p) / (b.p - a.p)
                return a.value + w * (b.value - a.value)
        raise AssertionError("unreachable")


class ForecastOutput(_Base):
    schema_version: SchemaVersion = "1.0"
    as_of: dt.date
    horizon_days: int
    model_name: str
    context_features_used: list[str] = Field(default_factory=list)
    signals_used: list[str] = Field(default_factory=list, description="signal_ids")
    forecasts: list[ProductForecast]

    @field_validator("horizon_days")
    @classmethod
    def _horizon(cls, v: int) -> int:
        if v not in config.HORIZONS_DAYS:
            raise ValueError(f"horizon_days must be one of {config.HORIZONS_DAYS}")
        return v

    @model_validator(mode="after")
    def _unique(self) -> ForecastOutput:
        ids = [f.product_id for f in self.forecasts]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate product_id in forecasts")
        return self


# ===========================================================================
# 6. OPTIMIZER PLAN  (producer: optimizer; consumers: API, explainer, UI)
# ===========================================================================
ReasonCode = Literal[
    "HIGH_PROFIT_PER_CURRENCY",
    "BUDGET_BINDING",
    "HIGH_UNCERTAINTY_REDUCED_QTY",
    "MIN_ORDER_QTY_APPLIED",
    "STORAGE_LIMIT",
    "ALREADY_STOCKED",
    "LOW_MARGIN",
    "EXPIRY_LIMIT",
    "LOW_DATA_CAUTION",
    "NOT_AFFORDABLE",
]


class OptimizerConstraints(_Base):
    storage_capacity_units: NonNeg | None = None
    max_products: int | None = Field(default=None, ge=1)


class PlanLine(_Base):
    product_id: str
    order_qty: int = Field(ge=0)
    unit_cost: NonNeg
    line_cost: NonNeg
    expected_demand: NonNeg
    target_quantile: Prob = Field(description="Service level used for this product.")
    expected_sales_units: NonNeg
    expected_profit: float
    stockout_probability: Prob
    uncertainty: Literal["low", "medium", "high"]
    reason_codes: list[ReasonCode] = Field(default_factory=list)


class Risk(_Base):
    code: str
    product_id: str | None = None
    severity: Literal["low", "medium", "high"]
    description: str = Field(description="English text; numbers inside must come from the plan.")


class BudgetPoint(_Base):
    budget: NonNeg
    total_cost: NonNeg
    expected_total_profit: float


class Interval(_Base):
    low: float
    high: float

    @model_validator(mode="after")
    def _order(self) -> Interval:
        if self.high < self.low:
            raise ValueError("interval high < low")
        return self


class OptimizerPlan(_Base):
    schema_version: SchemaVersion = "1.0"
    as_of: dt.date
    horizon_days: int
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    budget: NonNeg
    total_cost: NonNeg
    capital_utilization: Prob
    expected_total_profit: float
    expected_profit_interval: Interval | None = None
    lines: list[PlanLine]
    binding_constraints: list[str] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)
    budget_sensitivity: list[BudgetPoint] = Field(
        default_factory=list, description="What happens under different budgets (optional)."
    )

    @model_validator(mode="after")
    def _check(self) -> OptimizerPlan:
        tol = config.MONEY_TOLERANCE
        for ln in self.lines:
            if abs(ln.line_cost - ln.order_qty * ln.unit_cost) > tol:
                raise ValueError(f"line_cost mismatch for {ln.product_id}")
        s = sum(ln.line_cost for ln in self.lines)
        if abs(s - self.total_cost) > tol:
            raise ValueError(f"total_cost {self.total_cost} != sum of lines {s:.2f}")
        if self.total_cost > self.budget + 1e-9:
            raise ValueError(f"total_cost {self.total_cost} exceeds budget {self.budget}")
        if self.budget > 0 and abs(self.total_cost / self.budget - self.capital_utilization) > 1e-3:
            raise ValueError("capital_utilization != total_cost / budget")
        ids = [ln.product_id for ln in self.lines]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate product_id in plan lines")
        return self


# ===========================================================================
# 7. EXPLANATION  (producer: explainer; consumer: API, UI)
# ===========================================================================
class CitedFigure(_Base):
    path: str = Field(description="JSON Pointer into the OptimizerPlan, e.g. /lines/0/order_qty")
    value: float | int | str


class Explanation(_Base):
    schema_version: SchemaVersion = "1.0"
    language: LangCode
    text: str
    cited_figures: list[CitedFigure] = Field(
        default_factory=list,
        description="Every number appearing in text must be listed here and match the plan.",
    )


# ===========================================================================
# 8. OPPORTUNITIES  (Component D, owned by Member 5)
#    Input: CatalogueItem list (+ CanonicalData + optional SignalOutput)
#    Output: OpportunityOutput. Nothing here is ever a forecast.
# ===========================================================================
class RequestStats(_Base):
    """Customer requests for an item the retailer does not stock (reviews, messages, notes)."""

    count: int = Field(ge=0)
    window_days: int = Field(ge=1, description="Period the count was collected over.")
    source: str


class CatalogueItem(_Base):
    """One candidate product from a supplier catalogue / public price data (INPUT to Component D)."""

    item_id: str
    name: str
    category: str | None = None
    unit_cost: NonNeg = Field(description="Supplier price per unit.")
    unit_price: NonNeg = Field(description="Typical public selling price per unit.")
    supplier_min_order_qty: int = Field(default=1, ge=1)
    supplier_available: bool = True
    sellers_count: int | None = Field(
        default=None, ge=0, description="Sellers of this item in public price data; null = unknown."
    )
    requests: RequestStats | None = None
    source: str = Field(description="Where this row came from (supplier list, public prices, ...).")


class DemandRange(_Base):
    low: NonNeg
    mid: NonNeg
    high: NonNeg
    unit: Literal["units_per_horizon"] = "units_per_horizon"
    horizon_days: int

    @model_validator(mode="after")
    def _order(self) -> DemandRange:
        if not (self.low <= self.mid <= self.high):
            raise ValueError("require low <= mid <= high")
        return self


class OpportunityScores(_Base):
    demand_potential: Prob = Field(
        description="Item's mid demand relative to the median current product, capped at 1."
    )
    competition: Prob = Field(description="Higher = more competition.")
    profitability: Prob
    capital_requirement: Prob = Field(description="Higher = more capital needed.")
    uncertainty: Prob = Field(description="Relative width of the demand range.")


class Comparable(_Base):
    product_id: str
    name: str
    similarity: Prob
    observed_units_per_horizon: NonNeg


OpportunitySource = Literal[
    "catalogue_gap", "unmet_demand", "category_growth", "comparable", "customer_requests"
]
OpportunityNote = Literal[
    "COMPETITION_UNKNOWN",
    "FEW_COMPARABLES",
    "SIGNALS_NOT_VALIDATED",
    "LOW_REQUEST_COUNT",
    "DEMAND_POTENTIAL_UNKNOWN",
    "MIN_ORDER_EXCEEDS_TRIAL_BUDGET",
    "MIN_ORDER_ABOVE_DEMAND_RANGE",
]
ExclusionReason = Literal[
    "ALREADY_STOCKED", "SUPPLIER_UNAVAILABLE", "NO_COMPARABLES", "COMPARABLES_NO_SALES"
]


class Opportunity(_Base):
    opportunity_id: str
    name: str
    category: str | None = None
    demand_basis: Literal["observed", "hypothesized"]
    is_forecast: Literal[False] = Field(
        default=False, description="Always false: opportunities are never forecasts."
    )
    demand: DemandRange
    basis_description: str = Field(description="English summary of how the range was obtained.")
    sources: list[OpportunitySource] = Field(default_factory=list)
    comparables: list[Comparable] = Field(default_factory=list)
    signal_ids: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    observed_requests: RequestStats | None = None
    scores: OpportunityScores
    unit_cost: NonNeg
    unit_price: NonNeg
    supplier_min_order_qty: int = Field(ge=1)
    trial_order_qty: int | None = Field(
        default=None, ge=0, description="From the optimizer under the trial budget; null = unavailable."
    )
    trial_cost: NonNeg | None = Field(default=None, description="The optimizer's line_cost.")
    notes: list[OpportunityNote] = Field(default_factory=list)

    @model_validator(mode="after")
    def _label_rules(self) -> Opportunity:
        if self.demand_basis == "hypothesized":
            lo, hi = self.demand.low, self.demand.high
            ratio = float("inf") if lo == 0 and hi > 0 else (hi / lo if lo > 0 else 1.0)
            if ratio < config.HYPOTHESIZED_MIN_INTERVAL_RATIO:
                raise ValueError(
                    "hypothesized demand interval too narrow "
                    f"(high/low < {config.HYPOTHESIZED_MIN_INTERVAL_RATIO})"
                )
            if not self.comparables:
                raise ValueError("hypothesized demand must be estimated from comparables")
            if self.observed_requests is not None:
                raise ValueError("an item with observed requests is 'observed', not 'hypothesized'")
        else:
            if self.observed_requests is None and not self.evidence:
                raise ValueError("observed demand needs observed_requests or evidence")
        if (self.trial_order_qty is None) != (self.trial_cost is None):
            raise ValueError("trial_order_qty and trial_cost must be given together")
        return self


class ExcludedCandidate(_Base):
    item_id: str
    name: str
    reason: ExclusionReason


class OpportunityOutput(_Base):
    schema_version: SchemaVersion = "1.0"
    as_of: dt.date
    horizon_days: int
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    budget: NonNeg
    trial_budget: NonNeg = Field(description="Budget given to the optimizer for trial orders.")
    trial_orders_available: bool = Field(
        description="False if the optimizer was unavailable or skipped; trial fields are then null."
    )
    opportunities: list[Opportunity]
    excluded: list[ExcludedCandidate] = Field(default_factory=list)


# ===========================================================================
# 9. MODULE ERROR (any module may raise ModuleFailure; API turns it into this)
# ===========================================================================
class ModuleError(_Base):
    module: Literal[
        "extractor", "context", "forecaster", "optimizer", "explainer", "signals", "opportunities"
    ]
    code: str
    message: str
    retryable: bool = False
    fallback_used: bool = False


# Registry used by the schema exporter and the boundary validator.
CONTRACT_MODELS: dict[str, type[BaseModel]] = {
    "ExtractionProfile": ExtractionProfile,
    "CanonicalData": CanonicalData,
    "SignalOutput": SignalOutput,
    "ContextFeatures": ContextFeatures,
    "ForecastOutput": ForecastOutput,
    "OptimizerPlan": OptimizerPlan,
    "Explanation": Explanation,
    "CatalogueItem": CatalogueItem,
    "OpportunityOutput": OpportunityOutput,
    "ModuleError": ModuleError,
}
