"""Shared configuration.

Every hand-set value lives here and is registered in ASSUMPTIONS so it is
visible, reviewable and never silently picked. Nothing in this file was
learned from data.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Assumption:
    name: str
    value: object
    rationale: str
    owner: str  # who may change it
    label: str = "ASSUMPTION (hand-set, not learned from data)"


ASSUMPTIONS: dict[str, Assumption] = {}


def _assume(name: str, value: object, rationale: str, owner: str = "Member 5") -> object:
    ASSUMPTIONS[name] = Assumption(name=name, value=value, rationale=rationale, owner=owner)
    return value


# --- Contract / pipeline ---------------------------------------------------
SCHEMA_VERSION = "1.0"

SUPPORTED_LANGUAGES = _assume(
    "SUPPORTED_LANGUAGES",
    ("en", "fr", "hi", "es"),
    "Chosen by the project owner on 2026-10-13: English, French, Hindi, Spanish.",
)

HORIZONS_DAYS = _assume(
    "HORIZONS_DAYS",
    (7, 14, 30),
    "README Component B: planning horizons of 7, 14 or 30 days.",
)

# Quantile grid every forecast must provide so the optimizer can solve the
# newsvendor problem at any service level by interpolation.
QUANTILE_GRID = _assume(
    "QUANTILE_GRID",
    (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95),
    "Needed so the optimizer can read arbitrary quantiles; grid chosen by Member 5 "
    "and must be agreed with the forecasting owner.",
)

# --- Extraction / confidence -----------------------------------------------
LOW_CONFIDENCE_THRESHOLD = _assume(
    "LOW_CONFIDENCE_THRESHOLD",
    0.7,
    "A field with a value but confidence below this triggers a follow-up question. "
    "Default chosen by the project owner; the extraction owner may override.",
)

REQUIRED_PROFILE_FIELDS = _assume(
    "REQUIRED_PROFILE_FIELDS",
    ("location_type", "country", "currency"),
    "Minimum fields needed to build context and format money. A missing or "
    "low-confidence required field blocks /plan until the retailer answers.",
)

# --- Latency (single-user local demo) ---------------------------------------
PLAN_LATENCY_WARM_SECONDS = _assume(
    "PLAN_LATENCY_WARM_SECONDS", 3.0, "/plan with cached forecasts. Chosen by project owner."
)
PLAN_LATENCY_COLD_SECONDS = _assume(
    "PLAN_LATENCY_COLD_SECONDS", 10.0, "/plan with no cache. Chosen by project owner."
)

# --- Opportunity Discovery (Component D) -----------------------------------
HYPOTHESIZED_MIN_INTERVAL_RATIO = _assume(
    "HYPOTHESIZED_MIN_INTERVAL_RATIO",
    2.0,
    "Hypothesized demand must have high/low >= 2.0 so it is visibly wide. "
    "Hand-set, not calibrated: no comparable-based estimator has been validated.",
)

# --- Numeric tolerance for money checks -------------------------------------
MONEY_TOLERANCE = _assume(
    "MONEY_TOLERANCE",
    0.01,
    "Money is expressed to 2 decimals; sums may differ from line items by rounding only.",
)


# --- Opportunity Discovery assumptions (all hand-set; none learned from data) -------------------
MIN_COMPARABLE_SIMILARITY = _assume(
    "MIN_COMPARABLE_SIMILARITY", 0.3,
    "A stocked product counts as a comparable only if similarity >= this. similarity = "
    "category_factor x price_ratio, where price_ratio = min/max of unit prices.")
DIFFERENT_CATEGORY_FACTOR = _assume(
    "DIFFERENT_CATEGORY_FACTOR", 0.5,
    "Similarity multiplier when categories differ (1.0 when they match).")
MAX_COMPARABLES = _assume("MAX_COMPARABLES", 5, "Use at most this many comparables, most similar first.")
NEW_PRODUCT_DISCOUNT = _assume(
    "NEW_PRODUCT_DISCOUNT", 0.5,
    "A product never sold here is assumed to sell this fraction of what its comparables sell.")
HYPOTHESIZED_LOW_FACTOR = _assume(
    "HYPOTHESIZED_LOW_FACTOR", 0.2, "low = mid x this, for hypothesized demand.")
HYPOTHESIZED_HIGH_FACTOR = _assume(
    "HYPOTHESIZED_HIGH_FACTOR", 2.0, "high = mid x this, for hypothesized demand.")
FEW_COMPARABLES_COUNT = _assume(
    "FEW_COMPARABLES_COUNT", 3, "With fewer comparables than this the interval is widened.")
FEW_COMPARABLES_LOW_MULT = _assume(
    "FEW_COMPARABLES_LOW_MULT", 0.5, "low factor multiplier when few comparables.")
FEW_COMPARABLES_HIGH_MULT = _assume(
    "FEW_COMPARABLES_HIGH_MULT", 1.5, "high factor multiplier when few comparables.")
SIGNAL_TILT_CAP = _assume(
    "SIGNAL_TILT_CAP", 0.5,
    "A signal with established predictive value may raise hypothesized mid by at most this fraction. "
    "Signals without established predictive value never change any number.")
UNITS_PER_REQUEST = _assume(
    "UNITS_PER_REQUEST", 1.0,
    "Each logged customer request is taken to mean 1 unit wanted. Requests are a LOWER BOUND on "
    "demand: most customers never ask.")
REQUEST_INTERVAL_Z = _assume(
    "REQUEST_INTERVAL_Z", 1.96,
    "Normal-approximation z for a Poisson interval on a request count (95%). Statistical, not tuned.")
LOW_REQUEST_COUNT = _assume("LOW_REQUEST_COUNT", 5, "Fewer requests than this get a LOW_REQUEST_COUNT note.")
SELLERS_SATURATION = _assume(
    "SELLERS_SATURATION", 10, "competition score = min(1, sellers_count / this).")
UNKNOWN_COMPETITION_SCORE = _assume(
    "UNKNOWN_COMPETITION_SCORE", 0.5, "Neutral competition score when sellers_count is unknown (flagged).")
TARGET_MARGIN = _assume("TARGET_MARGIN", 0.4, "profitability score = min(1, gross_margin / this).")
TRIAL_BUDGET_FRACTION = _assume(
    "TRIAL_BUDGET_FRACTION", 0.10,
    "A trial order is sized by the optimizer with this fraction of the retailer's budget. "
    "DECISION NEEDED: the project owner has not specified how to size trial orders.")

# --- Inventory & Optimizer Operational Assumptions -------------------------
DAYS_TO_NEXT_REPLENISHMENT = _assume(
    "DAYS_TO_NEXT_REPLENISHMENT", 7,
    "Default cadence in days between vendor replenishments for inventory optimization when unstated.",
)

DEFAULT_PACK_SIZE = _assume(
    "DEFAULT_PACK_SIZE", 1,
    "Default ordering pack size for products when not specified in catalog.",
)

# --- Forecasting Context Anchor Multipliers --------------------------------
CONTEXT_DEMAND_EFFECTS = _assume(
    "CONTEXT_DEMAND_EFFECTS",
    {"near_school": 0.05, "near_market": 0.08},
    "Hand-set demand multipliers for local context anchors (near_school: +5%, near_market: +8%).",
)

