"""Adapters from the team component repositories to the shared application contracts."""

from __future__ import annotations

import datetime as dt
import importlib
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any

import pandas as pd

from marketpulse import config
from marketpulse.contracts.errors import ModuleFailure
from marketpulse.contracts.models import (
    BudgetPoint,
    CanonicalData,
    CitedFigure,
    ContextFeature,
    ContextFeatures,
    Evidence,
    Explanation,
    ExtractionProfile,
    ForecastOutput,
    OptimizerConstraints,
    OptimizerPlan,
    PlanLine,
    ProductForecast,
    ProfileField,
    ProfileFields,
    QuantilePoint,
    Risk,
    Signal,
    SignalOutput,
)
from marketpulse.normalizers import (
    COUNTRY_TO_CURRENCY,
    CURRENCY_TO_COUNTRY,
    normalize_country,
    normalize_currency,
)

_ROOT = Path(__file__).resolve().parents[3]
_COMPONENT_DIRS = {
    "forecasting": "components/forecasting",
    "market_signals": "components/forecasting",
    "optimizer": "components/optimizer",
    "llm": "components/llm",
    "data": "components/data-layer",
    "src": "components/data-layer",
}


def _load_component(package: str) -> Any:
    folder = _COMPONENT_DIRS[package]
    component_root = (_ROOT / folder).resolve()
    if not component_root.is_dir():
        module = {
            "forecasting": "forecaster",
            "market_signals": "signals",
            "optimizer": "optimizer",
            "llm": "extractor",
            "data": "context",
            "src": "context",
        }[package]
        raise ModuleFailure(
            module, "COMPONENT_NOT_FOUND",
            f"Required component folder {folder!r} is missing under components/.",
        )
    component_path = str(component_root)
    if component_path not in sys.path:
        sys.path.insert(0, component_path)
    return importlib.import_module(package)


def _region_for_country(country: str | None) -> str:
    # These are the only country-to-region mappings supplied by the regional adapters.
    return {"IN": "south_asia", "PK": "south_asia", "EC": "ecuador"}.get(country or "", "")


def _regional_context(profile: ExtractionProfile, dates: pd.DatetimeIndex) -> pd.DataFrame:
    _load_component("src")
    context_layer = importlib.import_module("src.context_layer")
    engine = context_layer.ContextEngine()
    region = _region_for_country(profile.fields.country.value)
    return engine.fetch_context(region, dates, ["marketpulse-shop"])


class TeamExtractor:
    """Maps Member 4's extraction schema to the integration profile contract."""

    _COUNTRIES = (
        (re.compile(
            r"(?:\bindia\b|\bbharat\b|भारत|\bhindustan\b|ہندوستان|\bdelhi\b|\bmumbai\b)",
            re.IGNORECASE,
        ), "IN"),
        (re.compile(r"(?:\bpakistan\b|پاکستان|\bkarachi\b|\blahore\b)", re.IGNORECASE), "PK"),
        (re.compile(r"(?:\becuador\b|\bquito\b)", re.IGNORECASE), "EC"),
        (re.compile(
            r"(?:\bunited states\b|\busa\b|\bamerica\b|\bnew york\b|\blos angeles\b|\bchicago\b)",
            re.IGNORECASE,
        ), "US"),
        (re.compile(
            r"(?:\bunited kingdom\b|\buk\b|\bgreat britain\b|\bbritain\b|\bengland\b|"
            r"\blondon\b|\bmanchester\b)",
            re.IGNORECASE,
        ), "GB"),
        (re.compile(r"(?:\bfrance\b|\bparis\b|\blyon\b|\bmarseille\b)", re.IGNORECASE), "FR"),
        (re.compile(r"(?:\bspain\b|\bespaña\b|\bespana\b|\bmadrid\b|\bbarcelona\b)", re.IGNORECASE), "ES"),
        (re.compile(r"(?:\bgermany\b|\bdeutschland\b|\bberlin\b|\bmunich\b)", re.IGNORECASE), "DE"),
        (re.compile(r"(?:\bitaly\b|\bitalia\b|\brome\b|\bmilan\b)", re.IGNORECASE), "IT"),
        (re.compile(r"(?:\bcanada\b|\btoronto\b|\bvancouver\b|\bmontreal\b)", re.IGNORECASE), "CA"),
        (re.compile(r"(?:\baustralia\b|\bsydney\b|\bmelbourne\b)", re.IGNORECASE), "AU"),
        (re.compile(r"(?:\bkenya\b|\bnairobi\b|\bmombasa\b)", re.IGNORECASE), "KE"),
        (re.compile(r"(?:\bnigeria\b|\blagos\b|\babuja\b)", re.IGNORECASE), "NG"),
        (re.compile(r"(?:\bsouth africa\b|\bjohannesburg\b|\bcape town\b)", re.IGNORECASE), "ZA"),
        (re.compile(r"(?:\bjapan\b|\btokyo\b|\bosaka\b)", re.IGNORECASE), "JP"),
        (re.compile(r"(?:\bbrazil\b|\bbrasil\b|\bsao paulo\b|\brio\b)", re.IGNORECASE), "BR"),
        (re.compile(r"(?:\bmexico\b|\bméxico\b)", re.IGNORECASE), "MX"),
        (re.compile(r"(?:\buae\b|\bdubai\b|\babu dhabi\b|\bunited arab emirates\b)", re.IGNORECASE), "AE"),
        (re.compile(r"(?:\bsaudi arabia\b|\briyadh\b|\bjeddah\b)", re.IGNORECASE), "SA"),
        (re.compile(r"(?:\bsingapore\b)", re.IGNORECASE), "SG"),
        (re.compile(r"(?:\bswitzerland\b|\bzurich\b|\bgeneva\b)", re.IGNORECASE), "CH"),
        (re.compile(
            r"(?:\bcameroon\b|\bcameroun\b|\bdouala\b|\byaoundé\b|\byaounde\b)",
            re.IGNORECASE,
        ), "CM"),
    )
    _CURRENCIES = (
        (re.compile(r"(?:\bUSD\b|\$|\bdollar(?:s)?\b|\bus dollar(?:s)?\b)", re.IGNORECASE), "USD"),
        (re.compile(r"(?:\bEUR\b|€|\beuro(?:s)?\b)", re.IGNORECASE), "EUR"),
        (re.compile(r"(?:\bGBP\b|£|\bpound(?:s)?\b|\bquid\b)", re.IGNORECASE), "GBP"),
        (re.compile(r"(?:\bINR\b|₹|\brupee(?:s)?\b|\brs\.?\b|रुपये|रुपया)", re.IGNORECASE), "INR"),
        (re.compile(r"(?:\bPKR\b|₨|روپے)", re.IGNORECASE), "PKR"),
        (re.compile(r"(?:\bCAD\b|c\$|\bcanadian dollar(?:s)?\b)", re.IGNORECASE), "CAD"),
        (re.compile(r"(?:\bAUD\b|a\$|\baustralian dollar(?:s)?\b)", re.IGNORECASE), "AUD"),
        (re.compile(r"(?:\bJPY\b|¥|\byen\b)", re.IGNORECASE), "JPY"),
        (re.compile(r"(?:\bKES\b|\bshilling(?:s)?\b|\bksh\b)", re.IGNORECASE), "KES"),
        (re.compile(r"(?:\bSAR\b|\briyal(?:s)?\b|﷼)", re.IGNORECASE), "SAR"),
        (re.compile(r"(?:\bAED\b|\bdirham(?:s)?\b)", re.IGNORECASE), "AED"),
        (re.compile(r"(?:\bBRL\b|r\$|\brea(?:l|is)\b)", re.IGNORECASE), "BRL"),
        (re.compile(r"(?:\bMXN\b|\bpeso(?:s)?\b)", re.IGNORECASE), "MXN"),
        (re.compile(r"(?:\bCHF\b|\bfranc(?:s)?\b)", re.IGNORECASE), "CHF"),
        (re.compile(r"(?:\bXAF\b|\bcfa\b)", re.IGNORECASE), "XAF"),
    )
    _LOCATION = {
        "urban_flagship": "urban_dense",
        "suburban_medium": "peri_urban",
        "rural_kiosk": "rural",
    }
    _INCOME = {"low": "low", "medium": "middle", "high": "upper"}
    _CATEGORY = {
        "grocery": "grocery",
        "pharmacy": "pharmacy",
        "clothing": "clothing",
        "electronics": "electronics",
        "hardware": "hardware",
        "general_store": "general_store",
    }
    _ANCHOR = {
        "school": "school",
        "university": "university",
        "market": "market",
        "mosque": "place_of_worship",
        "church": "place_of_worship",
        "temple": "place_of_worship",
        "hospital": "hospital",
        "clinic": "hospital",
        "bus_station": "transport_hub",
        "railway_station": "transport_hub",
        "factory": "factory",
        "office": "office_district",
    }

    def extract_profile(self, description: str, language_hint: str | None = None) -> ExtractionProfile:
        llm = _load_component("llm")
        settings = llm.config.get_settings()
        if settings.backend not in {"mock", "amd"}:
            raise ModuleFailure("extractor", "INVALID_LLM_BACKEND", "MARKETPULSE_LLM_BACKEND must be 'mock' or 'amd'.")  # noqa: E501
        client = None
        if settings.backend == "amd":
            if not settings.has_live_credentials:
                raise ModuleFailure("extractor", "AMD_CREDENTIALS_MISSING",
                                    "AMD backend is selected but AMD_API_KEY is missing or still a placeholder.")  # noqa: E501
            client = llm.client.AMDClient(settings)
        try:
            result = llm.extraction.extract_profile(
                description,
                locale=language_hint,
                client=client,
                offline=settings.backend == "mock",
                settings=settings,
            )
        except Exception as exc:
            raise ModuleFailure("extractor", "EXTRACTION_FAILED",
                                f"Member 4 extraction failed ({type(exc).__name__}).", True) from exc
        if settings.backend == "amd" and result.model.endswith("(fallback)"):
            raise ModuleFailure("extractor", "AMD_REQUEST_FAILED",
                                "AMD extraction failed or returned unusable output; rule fallback was not accepted.",  # noqa: E501
                                True)

        fields = result.fields
        raw_location = fields.get("location_type")
        raw_income = fields.get("income_band")
        raw_category = fields.get("shop_category")
        raw_anchors = fields.get("nearby_anchors")
        raw_payday = fields.get("payday")
        location = self._LOCATION.get(raw_location.value) if raw_location else None
        loc_conf = None
        if location is None:
            low = description.lower()
            if any(w in low for w in ("rural", "village", "gaon", "campagne", "pueblo", "गाँव", "गांव")):
                location, loc_conf = "rural", 0.85
            elif any(w in low for w in ("suburb", "colony", "residential", "township")):
                location, loc_conf = "peri_urban", 0.85
            elif any(w in low for w in ("delhi", "dilli", "दिल्ली", "karachi", "lahore", "mumbai", "quito", "city", "urban", "downtown", "metro", "शहर", "new york", "london", "paris", "madrid", "barcelona", "berlin", "tokyo", "toronto", "sydney", "chicago", "nairobi", "lagos", "los angeles")):  # noqa: E501
                location, loc_conf = "urban", 0.85

        income = self._INCOME.get(raw_income.value) if raw_income else None
        category_value = raw_category.value if raw_category else None
        if category_value == "general_store" and (raw_category and raw_category.confidence < 0.7):
            category = None
            raw_category = None
        else:
            category = self._CATEGORY.get(category_value, "other" if category_value else None)
        anchors = sorted({
            self._ANCHOR[anchor]
            for anchor in (raw_anchors.value or [])
            if anchor in self._ANCHOR
        }) if raw_anchors else []
        payday_values = raw_payday.value if raw_payday else None
        payday = None
        if isinstance(payday_values, list) and len(payday_values) == 1:
            payday = 28 if payday_values[0] == "last" else int(payday_values[0])
        elif isinstance(payday_values, (int, float)):
            payday = int(payday_values)
        if payday is None:
            m = re.search(r"(?:paid|payday|salary|tankha|वेतन)\s*(?:on\s+)?(?:the\s+)?([12]?\d|3[01])(?:st|nd|rd|th)?\b", description, re.IGNORECASE)  # noqa: E501
            if m:
                payday = int(m.group(1))

        country = None
        for pattern, code in self._COUNTRIES:
            if pattern.search(description):
                country = code
                break
        # Check text first for explicit currency mentions
        text_currency = None
        for pattern, code in self._CURRENCIES:
            if pattern.search(description):
                text_currency = code
                break

        if text_currency:
            currency_val = text_currency
            curr_conf = 0.95
        elif country and country in COUNTRY_TO_CURRENCY:
            currency_val = COUNTRY_TO_CURRENCY[country]
            curr_conf = 0.9
        elif fields.get("currency") and fields.get("currency").value:
            currency_val = normalize_currency(fields.get("currency").value)
            curr_conf = fields.get("currency").confidence
        else:
            currency_val = None

        if country is None and currency_val:
            if currency_val in CURRENCY_TO_COUNTRY:
                country = CURRENCY_TO_COUNTRY[currency_val]

        if country:
            country = normalize_country(country)

        language = result.source_language or "en"
        if len(language) != 2 or not language.isalpha():
            language = "en"
        rule_based = result.model.startswith("RuleBasedExtractor")

        def field(value: Any, source_field: Any = None, confidence: float | None = None) -> ProfileField:
            return ProfileField(
                value=value,
                confidence=confidence if confidence is not None else (
                    source_field.confidence if source_field else 0.0
                ),
                source="default" if rule_based else "llm",
            )

        return ExtractionProfile(
            profile_id="pending-" + uuid.uuid4().hex[:8],
            language=language,
            raw_description=description,
            fields=ProfileFields(
                location_type=field(location, raw_location, confidence=loc_conf),
                income_band=field(income, raw_income),
                payday_day=field(payday, raw_payday, confidence=0.8 if payday else None),
                nearby_anchors=field(anchors or None, raw_anchors),
                shop_category=field(category, raw_category),
                place_name=ProfileField(value=None, confidence=0.0, source="default"),
                country=field(country, confidence=0.95 if country else 0.0),
                currency=field(currency_val, fields.get("currency"), confidence=curr_conf),
            ),
            follow_up_questions=[],
        )


class TeamContextBuilder:
    """Adapts Member 1's regional context engine to ContextFeatures."""

    def build_context(
        self,
        profile: ExtractionProfile,
        as_of: dt.date,
        horizon_days: int,
        signals: SignalOutput | None = None,
    ) -> ContextFeatures:
        dates = pd.date_range(as_of + dt.timedelta(days=1), periods=horizon_days, freq="D")
        try:
            frame = _regional_context(profile, dates)
        except Exception as exc:
            raise ModuleFailure("context", "REGIONAL_CONTEXT_FAILED",
                                f"Member 1 context generation failed ({type(exc).__name__}).", True) from exc

        features: list[ContextFeature] = []
        if not frame.empty:
            for name, group in frame.groupby("feature_name"):
                fallback = bool(group["is_fallback"].all())
                values = group["value"].astype(float)
                value = float(values.max()) if name.startswith("is_") else float(values.mean())
                tier = "economic" if name == "inflation_rate" else "calendar"
                features.append(ContextFeature(
                    name=name,
                    value=value,
                    tier=tier,
                    is_assumption=True,
                    source_available=not fallback,
                    fallback_used=fallback,
                ))
        anchors = profile.fields.nearby_anchors.value or []
        features.extend([
            ContextFeature(name="near_school", value=float("school" in anchors), tier="profile",
                           is_assumption=False),
            ContextFeature(name="near_market", value=float("market" in anchors), tier="profile",
                           is_assumption=False),
        ])
        payday = profile.fields.payday_day.value
        if payday is not None:
            features.append(ContextFeature(
                name="payday_in_horizon",
                value=float(any(day.day == payday for day in dates)),
                tier="calendar",
                is_assumption=False,
            ))
        return ContextFeatures(as_of=as_of, horizon_days=horizon_days, features=features)


class TeamSignalProvider:
    """Converts Member 2's statistical signal pipeline to the shared signal schema."""

    def get_signals(self, data: CanonicalData | None, as_of: dt.date) -> SignalOutput:
        if data is None or not data.sales:
            return SignalOutput(generated_at=as_of, signals=[])
        try:
            market_signals = _load_component("market_signals")
            rows = [{
                "date": row.date,
                "store_id": data.shop_id,
                "product_id": row.product_id,
                "units_sold": row.units_sold,
            } for row in data.sales if row.date <= as_of]
            sales = pd.DataFrame(rows)
            detected = market_signals.pipeline.MarketSignalPipeline().extract_signals(
                sales, store_id=data.shop_id
            )
        except Exception as exc:
            raise ModuleFailure("signals", "SIGNAL_PIPELINE_FAILED",
                                f"Member 2 signal generation failed ({type(exc).__name__}).", True) from exc

        product_ids = {product.product_id for product in data.products}
        out = []
        _SIGNAL_MAP = {
            "CHANGE_POINT_SPIKE": ("demand_shift", "up", "sales_history"),
            "CHANGE_POINT_DROP": ("demand_shift", "down", "sales_history"),
            "CUSTOMER_NEED": ("unmet_demand", "up", "customer_review"),
            "CUSTOMER_COMPLAINT": ("review_theme", "down", "customer_review"),
            "EMERGING_PREFERENCE": ("category_growth", "up", "customer_review"),
        }
        _CONTRACT_TYPES = {
            "demand_shift", "unmet_demand", "category_growth",
            "price_change", "review_theme", "seasonality",
        }
        for row in detected.to_dict(orient="records"):
            raw_type = str(row.get("type", ""))
            if raw_type in _SIGNAL_MAP:
                sig_type, direction, source = _SIGNAL_MAP[raw_type]
            elif raw_type in _CONTRACT_TYPES:
                sig_type = raw_type
                direction = str(row.get("direction", "up")).lower()
                if direction not in {"up", "down", "flat"}:
                    direction = "up"
                source = str(row.get("source", "market_signal"))
            else:
                continue

            evidence = str(row.get("evidence", ""))
            match = re.search(r"([+-]\d+(?:\.\d+)?)%", evidence)
            mag = (abs(float(match.group(1))) / 100 if match
                   else (float(row["magnitude"]) if row.get("magnitude") is not None else None))
            target = str(row.get("product_or_category", ""))
            date_val = str(row.get("date", as_of.isoformat()))[:10]
            try:
                sig_date = dt.date.fromisoformat(date_val)
            except ValueError:
                sig_date = as_of

            out.append(Signal(
                signal_id=str(row.get("signal_id", f"SIG_{uuid.uuid4().hex[:8]}")),
                type=sig_type,
                product_id=target if target in product_ids else None,
                category=None if target in product_ids else (target or None),
                direction=direction,
                magnitude=mag,
                confidence=max(0.0, min(1.0, float(row.get("confidence", 0.7)))),
                predictive_value_established=False,
                observed=True,
                evidence=[Evidence(source=source, date=sig_date, summary=evidence or None)],
            ))
        return SignalOutput(generated_at=as_of, signals=out)



class TeamForecaster:
    """Adapts Member 2's DataFrame API and Member 1's date reindexer to ForecastOutput."""

    def forecast(
        self,
        data: CanonicalData,
        profile: ExtractionProfile,
        context: ContextFeatures,
        horizon_days: int,
        signals: SignalOutput | None = None,
    ) -> ForecastOutput:
        if not data.products or not data.sales:
            raise ModuleFailure("forecaster", "INSUFFICIENT_DATA",
                                "Member 2 forecasting requires products and at least one sales record.")
        try:
            data_package = _load_component("src")
            forecasting = _load_component("forecasting")
            product_by_id = {product.product_id: product for product in data.products}
            raw_sales = pd.DataFrame([{
                "date": row.date,
                "store_id": data.shop_id,
                "item_id": row.product_id,
                "sales_quantity": row.units_sold,
                "price": product_by_id[row.product_id].unit_price,
                "on_promotion": False,
            } for row in data.sales])
            sales = data_package.pipeline.reindex_continuous_dates(raw_sales)
            sales = sales.rename(columns={"item_id": "product_id", "sales_quantity": "units_sold"})

            min_date = min(row.date for row in data.sales)
            dates = pd.date_range(min_date, data.as_of, freq="D")
            profile_payday = profile.fields.payday_day.value
            region_frame = _regional_context(profile, pd.DatetimeIndex(dates))
            payday_rows = region_frame[region_frame["feature_name"] == "is_payday"]
            regional_payday = payday_rows.set_index("date")["value"] if not payday_rows.empty else pd.Series(dtype=float)  # noqa: E501
            context_rows = []
            for day in dates:
                if profile_payday is not None:
                    payday_flag = int(day.day == profile_payday)
                else:
                    payday_flag = int(regional_payday.get(day, 0.0))
                context_rows.append({
                    "date": day,
                    "payday_flag": payday_flag,
                    "holiday_flag": 0,
                    "shock_flag": 0,
                })
            context_frame = pd.DataFrame(context_rows)
            products_frame = pd.DataFrame([{
                "product_id": p.product_id,
                "category": p.category or "GENERAL",
            } for p in data.products])
            forecast_rows = forecasting.api.forecast(
                store_id=data.shop_id,
                product_ids=[product.product_id for product in data.products],
                horizon_days=horizon_days,
                model_name=os.environ.get("MARKETPULSE_FORECAST_MODEL") or None,
                dataset={"sales": sales, "context": context_frame, "products": products_frame},
                use_live_data=False,
                as_dataframe=False,
            )
        except ModuleFailure:
            raise
        except Exception as exc:
            raise ModuleFailure("forecaster", "FORECAST_FAILED",
                                f"Member 2 forecasting failed ({type(exc).__name__}).", True) from exc

        forecasts = []
        model_names: set[str] = set()
        feat = {f.name: f.value for f in context.features}
        effects = config.CONTEXT_DEMAND_EFFECTS
        mult = 1.0 + sum(effects.get(k, 0.0) * feat.get(k, 0.0) for k in ("near_school", "near_market"))

        for row in forecast_rows:
            quantiles = [
                QuantilePoint(p=q, value=max(0.0, float(row["quantiles"][f"q{int(q * 100):02d}"]) * mult))
                for q in config.QUANTILE_GRID
            ]
            p10, p50, p90 = (float(row[key]) * mult for key in ("p10", "p50", "p90"))
            product_history = sales[sales["product_id"] == row["product_id"]]
            forecasts.append(ProductForecast(
                product_id=row["product_id"],
                mean=max(0.0, (p10 + 4 * p50 + p90) / 6),
                quantiles=quantiles,
                history_days=int(product_history["date"].nunique()),
                low_data=row["model_name"] == "hierarchical_sparse_pooling",
                cold_start=not bool((sales[
                    (sales["product_id"] == row["product_id"]) & (sales["units_sold"] > 0)
                ]).shape[0]),
            ))
            model_names.add(str(row["model_name"]))
        used_feats = sorted([f.name for f in context.features if f.value > 0])
        return ForecastOutput(
            as_of=data.as_of,
            horizon_days=horizon_days,
            model_name=", ".join(sorted(model_names)),
            forecasts=forecasts,
            context_features_used=used_feats,
        )


class TeamOptimizer:
    """Adapts Member 3's optimization engine to OptimizerPlan."""

    _REASON_MAP = {
        "ALLOCATED_OPTIMAL": "HIGH_PROFIT_PER_CURRENCY",
        "ALLOCATED_TRIMMED_BUDGET": "BUDGET_BINDING",
        "HIGH_UNCERTAINTY_HAIRCUT": "HIGH_UNCERTAINTY_REDUCED_QTY",
        "DROPPED_HIGH_UNCERTAINTY": "HIGH_UNCERTAINTY_REDUCED_QTY",
        "MOQ_PROMOTED": "MIN_ORDER_QTY_APPLIED",
        "DROPPED_BUDGET_EXHAUSTED": "NOT_AFFORDABLE",
        "DROPPED_LOW_CAPITAL_EFFICIENCY": "LOW_MARGIN",
        "CAPPED_SHELF_LIFE": "EXPIRY_LIMIT",
        "ALREADY_STOCKED": "ALREADY_STOCKED",
    }

    def optimize(
        self,
        forecast: ForecastOutput,
        data: CanonicalData,
        budget: float,
        constraints: OptimizerConstraints | None = None,
    ) -> OptimizerPlan:
        if constraints and constraints.max_products is not None:
            raise ModuleFailure("optimizer", "UNSUPPORTED_CONSTRAINT",
                                "Member 3's optimizer does not support max_products.")
        try:
            optimizer = _load_component("optimizer")
            forecasts = {
                fc.product_id: optimizer.models.Forecast(
                    p10=fc.quantile(0.1),
                    p50=fc.quantile(0.5),
                    p90=fc.quantile(0.9),
                    mean=fc.mean,
                    horizon_days=forecast.horizon_days,
                ) for fc in forecast.forecasts
            }
            inventory = {
                p.product_id: optimizer.models.InventoryState(
                    on_hand=float(p.current_stock),
                    on_order=float(p.on_order),
                    days_to_next_replenishment=config.DAYS_TO_NEXT_REPLENISHMENT,
                ) for p in data.products
            }
            products = {
                p.product_id: optimizer.models.ProductMeta(
                    product_id=p.product_id,
                    name=p.name,
                    category=p.category or "General",
                    purchase_price=p.unit_cost,
                    selling_price=p.unit_price,
                    lead_time_days=p.lead_time_days,
                    min_order_qty=p.min_order_qty,
                    pack_size=config.DEFAULT_PACK_SIZE,
                    unit_volume=p.storage_units,
                    shelf_life_days=p.shelf_life_days,
                ) for p in data.products
            }

            native = optimizer.engine.optimize(
                forecasts=forecasts,
                inventory=inventory,
                products=products,
                budget=budget,
                max_storage_volume=(
                    constraints.storage_capacity_units if constraints else data.storage_capacity_units
                ),
            )
        except ModuleFailure:
            raise
        except Exception as exc:
            raise ModuleFailure("optimizer", "OPTIMIZATION_FAILED",
                                f"Member 3 optimization failed ({type(exc).__name__}).", True) from exc

        lines = []
        risks = []
        binding = set(native.binding_constraints)
        for _index, item in enumerate(native.items.values()):
            fc = next(f for f in forecast.forecasts if f.product_id == item.product_id)
            reasons = sorted({
                self._REASON_MAP[reason]
                for reason in item.reason_codes
                if reason in self._REASON_MAP
            })
            if fc.low_data and "LOW_DATA_CAUTION" not in reasons:
                reasons.append("LOW_DATA_CAUTION")
            for constraint in item.binding_constraints:
                binding.add(constraint)
            lines.append(PlanLine(
                product_id=item.product_id,
                order_qty=item.order_qty,
                unit_cost=item.unit_cost,
                line_cost=round(item.cost, 2),
                expected_demand=fc.mean,
                target_quantile=item.critical_ratio,
                expected_sales_units=max(0.0, fc.mean - item.expected_leftover),
                expected_profit=item.expected_profit,
                stockout_probability=item.expected_stockout_prob,
                uncertainty="high" if item.uncertainty_flag else (
                    "medium" if item.relative_uncertainty >= 0.5 else "low"
                ),
                reason_codes=reasons,
            ))
            if item.uncertainty_flag:
                risks.append(Risk(
                    code="HIGH_UNCERTAINTY",
                    product_id=item.product_id,
                    severity="high",
                    description=f"Demand for {item.name} has high relative uncertainty.",
                ))
        total_cost = round(sum(line.line_cost for line in lines), 2)
        sensitivity = [
            BudgetPoint(
                budget=point.budget_amount,
                total_cost=point.total_cost,
                expected_total_profit=point.total_expected_profit,
            )
            for point in native.sensitivity.values()
        ]
        return OptimizerPlan(
            as_of=forecast.as_of,
            horizon_days=forecast.horizon_days,
            currency=data.currency,
            budget=budget,
            total_cost=total_cost,
            capital_utilization=round(total_cost / budget, 4) if budget > 0 else 0.0,
            expected_total_profit=native.total_expected_profit,
            lines=lines,
            binding_constraints=sorted(binding),
            risks=risks,
            budget_sensitivity=sensitivity,
        )


class TeamExplainer:
    """Adapts Member 4's grounded AMD assistant to the shared Explanation contract."""

    def explain(
        self,
        plan: OptimizerPlan,
        forecast: ForecastOutput,
        question: str | None = None,
        language: str = "en",
    ) -> Explanation:
        llm = _load_component("llm")
        settings = llm.config.get_settings()
        if settings.backend not in {"mock", "amd"}:
            raise ModuleFailure("explainer", "INVALID_LLM_BACKEND", "MARKETPULSE_LLM_BACKEND must be 'mock' or 'amd'.")  # noqa: E501
        client = None
        if settings.backend == "amd":
            if not settings.has_live_credentials:
                raise ModuleFailure("explainer", "AMD_CREDENTIALS_MISSING",
                                    "AMD backend is selected but AMD_API_KEY is missing or still a placeholder.")  # noqa: E501
            client = llm.client.AMDClient(settings)

        lines = {line.product_id: line for line in plan.lines}
        items = {
            pid: {
                "product_id": pid,
                "name": pid,
                "order_qty": line.order_qty,
                "cost": line.line_cost,
                "unit_cost": line.unit_cost,
                "expected_profit": line.expected_profit,
                "expected_stockout_prob": line.stockout_probability,
                "reason_codes": self._legacy_reason_codes(line.reason_codes),
            }
            for pid, line in lines.items()
        }
        sensitivity = {
            f"{round(point.budget / plan.budget * 100) if plan.budget else 0}_percent": {
                "budget_amount": point.budget,
                "total_expected_profit": point.expected_total_profit,
            }
            for point in plan.budget_sensitivity
        }
        plan_payload = {
            "budget": plan.budget,
            "total_cost": plan.total_cost,
            "total_expected_profit": plan.expected_total_profit,
            "sensitivity": sensitivity,
            "items": items,
        }
        facts = {
            "summary": {
                "budget": plan.budget,
                "total_spend": plan.total_cost,
                "expected_profit": plan.expected_total_profit,
            },
            "top_allocations": [
                {"product_id": pid, "name": pid, "qty": line.order_qty,
                 "spend": line.line_cost, "expected_profit": line.expected_profit,
                 "reason": ", ".join(line.reason_codes)}
                for pid, line in lines.items() if line.order_qty > 0
            ],
            "dropped_items": [
                {"product_id": pid, "name": pid, "cost_to_order": line.unit_cost,
                 "reason_code": (line.reason_codes or ["LOW_MARGIN"])[0],
                 "explanation": "Not funded under the current constraints."}
                for pid, line in lines.items() if line.order_qty == 0
            ],
            "uncertainty_alerts": [],
        }
        try:
            answer = llm.explainer.explain(
                question or "Explain this purchasing plan.",
                plan_payload,
                {},
                language,
                explain_facts=facts,
                client=client,
                offline=settings.backend == "mock",
                settings=settings,
            )
        except Exception as exc:
            raise ModuleFailure("explainer", "EXPLANATION_FAILED",
                                f"Member 4 explanation failed ({type(exc).__name__}).", True) from exc
        if settings.backend == "amd" and not answer.guard_passed:
            raise ModuleFailure("explainer", "AMD_GUARD_FALLBACK",
                                "AMD output did not pass the number guard; no ungrounded explanation was returned.",  # noqa: E501
                                True)
        # Resolve cited figures as RFC 6901 pointers into the plan
        pool = self._plan_pointers(plan)
        cited: list[CitedFigure] = []
        tokens = re.findall(r"(?<![\w.])\d+(?:\.\d+)?(?![\w])", answer.text)
        all_grounded = True
        for tok in tokens:
            try:
                val = float(tok)
            except ValueError:
                continue
            matched = False
            for ptr, target_val in pool:
                if abs(val - target_val) < 0.005:
                    cited.append(CitedFigure(path=ptr, value=target_val))
                    matched = True
                    break
            if not matched:
                all_grounded = False
                break

        if all_grounded and cited:
            # Dedup cited figures by path
            seen_paths = set()
            dedup_cited = []
            for fig in cited:
                if fig.path not in seen_paths:
                    seen_paths.add(fig.path)
                    dedup_cited.append(fig)
            return Explanation(
                language=answer.language,
                text=answer.text,
                cited_figures=dedup_cited,
            )

        # Fallback to guaranteed-grounded localized explanation
        fallback_templates = {
            "en": ("Spend {cost} of {budget} {cur}. Expected profit: {profit} {cur}.",
                   "Order {qty} units of {pid} (cost {lc} {cur})."),
            "fr": ("Dépensez {cost} sur {budget} {cur}. Profit attendu : {profit} {cur}.",
                   "Commandez {qty} unités de {pid} (coût {lc} {cur})."),
            "es": ("Gaste {cost} de {budget} {cur}. Ganancia esperada: {profit} {cur}.",
                   "Pida {qty} unidades de {pid} (costo {lc} {cur})."),
            "hi": ("{budget} {cur} में से {cost} खर्च करें। अपेक्षित लाभ: {profit} {cur}।",
                   "{pid} की {qty} इकाइयाँ मँगाएँ (लागत {lc} {cur})।"),
            "ur": ("بجٹ {budget} {cur} میں سے {cost} خرچ کریں۔ متوقع منافع: {profit} {cur}۔",
                   "{pid} کی {qty} اکائیاں خریدیں (لاگت {lc} {cur})۔"),
        }
        lang = language if language in fallback_templates else "en"
        head, line_t = fallback_templates[lang]
        figs = [
            CitedFigure(path="/total_cost", value=plan.total_cost),
            CitedFigure(path="/budget", value=plan.budget),
            CitedFigure(path="/expected_total_profit", value=plan.expected_total_profit),
        ]
        parts = [head.format(cost=f"{plan.total_cost:.2f}", budget=f"{plan.budget:.2f}",
                             profit=f"{plan.expected_total_profit:.2f}", cur=plan.currency)]
        for i, ln in enumerate(plan.lines):
            if question and ln.product_id.lower() not in question.lower() and any(
                x.product_id.lower() in question.lower() for x in plan.lines
            ):
                continue
            if ln.order_qty == 0:
                continue
            parts.append(line_t.format(qty=ln.order_qty, pid=ln.product_id,
                                       lc=f"{ln.line_cost:.2f}", cur=plan.currency))
            figs += [CitedFigure(path=f"/lines/{i}/order_qty", value=ln.order_qty),
                     CitedFigure(path=f"/lines/{i}/line_cost", value=ln.line_cost)]
        return Explanation(language=lang, text=" ".join(parts), cited_figures=figs)

    @staticmethod
    def _plan_pointers(plan: OptimizerPlan) -> list[tuple[str, float]]:
        out = [
            ("/budget", float(plan.budget)),
            ("/total_cost", float(plan.total_cost)),
            ("/expected_total_profit", float(plan.expected_total_profit)),
            ("/capital_utilization", float(plan.capital_utilization)),
        ]
        for i, line in enumerate(plan.lines):
            out.extend([
                (f"/lines/{i}/order_qty", float(line.order_qty)),
                (f"/lines/{i}/unit_cost", float(line.unit_cost)),
                (f"/lines/{i}/line_cost", float(line.line_cost)),
                (f"/lines/{i}/expected_demand", float(line.expected_demand)),
                (f"/lines/{i}/target_quantile", float(line.target_quantile)),
                (f"/lines/{i}/expected_sales_units", float(line.expected_sales_units)),
                (f"/lines/{i}/expected_profit", float(line.expected_profit)),
                (f"/lines/{i}/stockout_probability", float(line.stockout_probability)),
            ])
        for j, pt in enumerate(plan.budget_sensitivity):
            out.extend([
                (f"/budget_sensitivity/{j}/budget", float(pt.budget)),
                (f"/budget_sensitivity/{j}/total_cost", float(pt.total_cost)),
                (f"/budget_sensitivity/{j}/expected_total_profit", float(pt.expected_total_profit)),
            ])
        return out

    @classmethod
    def _legacy_reason_codes(cls, reasons: list[str]) -> list[str]:
        reverse = {
            "HIGH_PROFIT_PER_CURRENCY": "ALLOCATED_OPTIMAL",
            "BUDGET_BINDING": "ALLOCATED_TRIMMED_BUDGET",
            "HIGH_UNCERTAINTY_REDUCED_QTY": "DROPPED_HIGH_UNCERTAINTY",
            "MIN_ORDER_QTY_APPLIED": "MOQ_PROMOTED",
            "NOT_AFFORDABLE": "DROPPED_BUDGET_EXHAUSTED",
            "LOW_MARGIN": "DROPPED_LOW_CAPITAL_EFFICIENCY",
            "EXPIRY_LIMIT": "CAPPED_SHELF_LIFE",
            "ALREADY_STOCKED": "ALLOCATED_OPTIMAL",
        }
        return [reverse[reason] for reason in reasons if reason in reverse]


def integrated_modules():
    """Return the real adapters for Member 1-4 components."""
    _load_component("forecasting")
    _load_component("optimizer")
    _load_component("llm")
    _load_component("src")
    return {
        "extractor": TeamExtractor(),
        "context": TeamContextBuilder(),
        "forecaster": TeamForecaster(),
        "optimizer": TeamOptimizer(),
        "explainer": TeamExplainer(),
        "signals": TeamSignalProvider(),
    }
