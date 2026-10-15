"""Decision service: chains the modules in the agreed pipeline order.

profile extraction -> data/context -> forecast -> optimize -> explain

Rules enforced here (core principle): this layer never computes a forecast or a
money figure. It validates every module boundary, decides honestly what to do on
failure, and records everything in the audit log.
"""

from __future__ import annotations

import hashlib
import json
import math
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from marketpulse import config
from marketpulse.audit import AuditLog
from marketpulse.contracts.errors import ModuleFailure
from marketpulse.contracts.integrity import check_explanation_numbers
from marketpulse.contracts.models import (
    CanonicalData,
    ContextFeatures,
    Explanation,
    ExtractionProfile,
    FieldEdit,
    FollowUpQuestion,
    ForecastOutput,
    ModuleError,
    OpportunityOutput,
    OptimizerConstraints,
    OptimizerPlan,
    ProfileFields,
    SignalOutput,
)
from marketpulse.contracts.validate import ContractViolation, validate_payload
from marketpulse.csvloader import CsvError, load_canonical_data, load_canonical_stores
from marketpulse.mocks.catalogue import sample_catalogue
from marketpulse.normalizers import normalize_country, normalize_currency
from marketpulse.opportunities.discovery import DiscoveryEngine
from marketpulse.registry import Modules, default_modules


class ApiError(Exception):
    """Carries an HTTP status and an honest, structured body."""

    def __init__(self, status: int, code: str, message: str, module_error: ModuleError | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.module_error = module_error

    def body(self, request_id: str | None = None) -> dict[str, Any]:
        err: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.module_error:
            err["module_error"] = self.module_error.model_dump(mode="json")
        return {"status": "error", "request_id": request_id, "error": err}


class StepFailed(Exception):
    def __init__(self, error: ModuleError):
        super().__init__(error.message)
        self.error = error


# --- follow-up question text (used only when the extractor did not supply one) -----------------
_FIELD_NAMES = {
    "en": {"location_type": "location type", "country": "country", "currency": "currency"},
    "fr": {"location_type": "type d'emplacement", "country": "pays", "currency": "devise"},
    "es": {"location_type": "tipo de ubicación", "country": "país", "currency": "moneda"},
    "hi": {"location_type": "स्थान का प्रकार", "country": "देश", "currency": "मुद्रा"},
}
_Q = {
    "en": {"missing": "Please tell us your {f}.", "low_confidence": "Is your {f} correct?"},
    "fr": {"missing": "Merci d'indiquer votre {f}.", "low_confidence": "Votre {f} est-il correct ?"},
    "es": {"missing": "Indique su {f}.", "low_confidence": "¿Es correcto su {f}?"},
    "hi": {"missing": "कृपया अपना {f} बताएँ।", "low_confidence": "क्या आपका {f} सही है?"},
}


def compute_followups(profile: ExtractionProfile) -> list[FollowUpQuestion]:
    """Apply the low-confidence rule (CONTRACT.md section 5, rule 7)."""
    lang = profile.language if profile.language in _Q else "en"
    supplied = {q.field: q.question for q in profile.follow_up_questions}
    out: list[FollowUpQuestion] = []
    for name in ProfileFields.model_fields:
        f = getattr(profile.fields, name)
        required = name in config.REQUIRED_PROFILE_FIELDS
        reason = None
        if f.value is None and required:
            reason = "missing"
        elif f.value is not None and f.source != "retailer" and (
            f.confidence < config.LOW_CONFIDENCE_THRESHOLD
        ):
            reason = "low_confidence"
        if reason:
            label = _FIELD_NAMES.get(lang, _FIELD_NAMES["en"]).get(name, name.replace("_", " "))
            text = supplied.get(name) or _Q[lang][reason].format(f=label)
            out.append(FollowUpQuestion(field=name, question=text, reason=reason))
    return out


def _dump(model: BaseModel | None) -> Any:
    return model.model_dump(mode="json") if model is not None else None


def _hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


@dataclass
class Trace:
    """Per-request step record -> audit log and response timings."""

    request_id: str
    started: float = field(default_factory=time.perf_counter)
    steps: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)

    def warn(self, code: str, message: str) -> None:
        self.warnings.append({"code": code, "message": message})

    def timings(self) -> dict[str, float]:
        t = {s["module"]: s["ms"] for s in self.steps}
        t["total"] = round((time.perf_counter() - self.started) * 1000, 1)
        return t


@dataclass
class StoredResult:
    plan: OptimizerPlan
    forecast: ForecastOutput
    language: str


class BoundedDict(dict):
    """Dictionary with an upper size bound that evicts the oldest entries (LRU/FIFO)."""

    def __init__(self, maxsize: int = 500, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._maxsize = max(1, maxsize)
        self._order: OrderedDict[Any, None] = OrderedDict()
        for k in self:
            self._order[k] = None

    def __setitem__(self, key: Any, value: Any) -> None:
        super().__setitem__(key, value)
        self._order[key] = None
        self._order.move_to_end(key)
        while len(self._order) > self._maxsize:
            oldest, _ = self._order.popitem(last=False)
            super().pop(oldest, None)

    def __getitem__(self, key: Any) -> Any:
        val = super().__getitem__(key)
        if key in self._order:
            self._order.move_to_end(key)
        return val

    def get(self, key: Any, default: Any = None) -> Any:
        if key in self:
            return self[key]
        return default

    def pop(self, key: Any, *args: Any) -> Any:
        self._order.pop(key, None)
        return super().pop(key, *args)

    def clear(self) -> None:
        self._order.clear()
        super().clear()


def _parse_budget_and_horizon(req: dict[str, Any]) -> tuple[float, int]:
    """Defensively parses and validates budget and horizon_days from a request dictionary."""
    if "budget" not in req or req["budget"] is None:
        raise ApiError(422, "INVALID_BUDGET", "Budget is required.")
    try:
        budget = float(req["budget"])
    except (TypeError, ValueError) as exc:
        raise ApiError(422, "INVALID_BUDGET", "Budget must be a valid number.") from exc
    if not math.isfinite(budget) or budget <= 0:
        raise ApiError(422, "INVALID_BUDGET", "Budget must be greater than 0.")

    raw_horizon = req.get("horizon_days", 14)
    if raw_horizon is None:
        raw_horizon = 14
    try:
        horizon = int(raw_horizon)
    except (TypeError, ValueError) as exc:
        raise ApiError(422, "INVALID_HORIZON", f"horizon_days must be one of {config.HORIZONS_DAYS}") from exc
    if horizon not in config.HORIZONS_DAYS:
        raise ApiError(422, "INVALID_HORIZON", f"horizon_days must be one of {config.HORIZONS_DAYS}")

    return budget, horizon


class DecisionService:
    def __init__(self, modules: Modules | None = None, audit: AuditLog | None = None):
        self.m = modules or default_modules()
        self.audit = audit or AuditLog(None)
        self._lock = threading.Lock()
        self.profiles: dict[str, ExtractionProfile] = BoundedDict(maxsize=500)
        self.datasets: dict[str, CanonicalData] = BoundedDict(maxsize=500)
        self.results: dict[str, StoredResult] = BoundedDict(maxsize=500)
        self.forecast_cache: dict[str, ForecastOutput] = BoundedDict(maxsize=500)

    def clear_cache(self) -> None:
        """Explicitly clear ephemeral in-memory caches."""
        with self._lock:
            self.forecast_cache.clear()
            self.results.clear()


    # ------------------------------------------------------------------ helpers
    def _call(
        self,
        trace: Trace,
        module: str,
        contract: str,
        fn: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Run one module, validate its output at the boundary, never leak a traceback."""
        t0 = time.perf_counter()
        status, err = "ok", None
        try:
            out = fn(*args, **kwargs)
            validate_payload(contract, out)
            return out
        except ModuleFailure as exc:
            err = ModuleError(module=module, code=exc.code, message=exc.message,
                              retryable=exc.retryable)
        except ContractViolation as exc:
            err = ModuleError(module=module, code="CONTRACT_VIOLATION", message=str(exc)[:500])
        except Exception as exc:  # noqa: BLE001 - a module bug must not crash the API
            err = ModuleError(module=module, code="UNEXPECTED_ERROR",
                              message=f"{type(exc).__name__} in {module}")
        finally:
            ms = round((time.perf_counter() - t0) * 1000, 1)
            if err:
                status = "failed"
            trace.steps.append({"module": module, "status": status, "ms": ms,
                                "error": _dump(err)})
        raise StepFailed(err)

    def _fail(self, trace: Trace, endpoint: str, exc: StepFailed) -> ApiError:
        e = exc.error
        self.audit.write(trace.request_id, endpoint, outcome="error", steps=trace.steps,
                         error=_dump(e))
        return ApiError(502, "MODULE_FAILED",
                        f"The {e.module} step failed ({e.code}). No plan was produced.", e)

    # ----------------------------------------------------------- /profile/extract
    def extract_profile(self, description: str, language_hint: str | None = None) -> dict[str, Any]:
        trace = Trace(uuid.uuid4().hex[:12])
        if not description.strip():
            raise ApiError(422, "EMPTY_DESCRIPTION", "Please describe your shop.")
        if language_hint and language_hint not in config.SUPPORTED_LANGUAGES:
            raise ApiError(422, "UNSUPPORTED_LANGUAGE",
                           f"Supported languages: {', '.join(config.SUPPORTED_LANGUAGES)}")
        try:
            profile = self._call(trace, "extractor", "ExtractionProfile",
                                 self.m.extractor.extract_profile, description, language_hint)
        except StepFailed as exc:
            raise self._fail(trace, "/profile/extract", exc) from exc
        # The API owns profile ids: a module-supplied id could collide and overwrite a
        # profile the retailer already confirmed.
        profile = profile.model_copy(update={"profile_id": "prof-" + uuid.uuid4().hex[:10]})
        follow = compute_followups(profile)
        with self._lock:
            self.profiles[profile.profile_id] = profile
        self.audit.write(trace.request_id, "/profile/extract", outcome="ok",
                         said=description, extracted=_dump(profile.fields),
                         language=profile.language, follow_ups=[f.field for f in follow],
                         steps=trace.steps)
        return {
            "status": "needs_confirmation",
            "request_id": trace.request_id,
            "profile": _dump(profile),
            "follow_up_questions": [_dump(f) for f in follow],
            "low_confidence_threshold": config.LOW_CONFIDENCE_THRESHOLD,
            "required_fields": list(config.REQUIRED_PROFILE_FIELDS),
        }

    # ----------------------------------------------------------- /profile/confirm
    def confirm_profile(self, profile_id: str, edits: dict[str, Any]) -> dict[str, Any]:
        trace = Trace(uuid.uuid4().hex[:12])
        with self._lock:
            profile = self.profiles.get(profile_id)
        if profile is None:
            raise ApiError(404, "PROFILE_NOT_FOUND", f"No profile {profile_id!r}.")
        unknown = [k for k in edits if k not in ProfileFields.model_fields]
        if unknown:
            raise ApiError(422, "UNKNOWN_FIELD", f"Unknown profile field(s): {', '.join(unknown)}")
        edits = dict(edits)
        if "currency" in edits and edits["currency"] is not None:
            edits["currency"] = normalize_currency(edits["currency"])
        if "country" in edits and edits["country"] is not None:
            edits["country"] = normalize_country(edits["country"])
        fields = profile.fields.model_dump(mode="json")
        changes: list[FieldEdit] = []
        for name, new in edits.items():
            old = fields[name]["value"]
            if old != new:
                changes.append(FieldEdit(field=name, old_value=old, new_value=new))
            fields[name] = {"value": new, "confidence": 1.0, "source": "retailer",
                            "evidence": None}
        # Defensively ensure any existing values are also normalized
        if fields["currency"]["value"] is not None:
            fields["currency"]["value"] = normalize_currency(fields["currency"]["value"])
        if fields["country"]["value"] is not None:
            fields["country"]["value"] = normalize_country(fields["country"]["value"])
        # Confirming means the retailer has seen and accepted every value shown.
        for name, f in fields.items():
            if f["value"] is not None and f["source"] != "retailer":
                fields[name] = {**f, "confidence": 1.0, "source": "retailer"}
        try:
            new_fields = ProfileFields.model_validate(fields)
        except ValidationError as exc:
            e = exc.errors()[0]
            raise ApiError(422, "INVALID_FIELD_VALUE",
                           f"{'.'.join(str(p) for p in e['loc'][:1])}: {e['msg']}") from exc
        updated = profile.model_copy(update={
            "fields": new_fields, "edits": profile.edits + changes, "follow_up_questions": []})
        follow = compute_followups(updated)
        missing = [f for f in follow if f.reason == "missing"]
        updated = updated.model_copy(update={"status": "extracted" if missing else "confirmed"})
        with self._lock:
            self.profiles[profile_id] = updated
        self.audit.write(trace.request_id, "/profile/confirm", outcome="ok",
                         profile_id=profile_id, changed=[_dump(c) for c in changes],
                         status=updated.status, follow_ups=[f.field for f in follow])
        return {
            "status": "needs_input" if missing else "confirmed",
            "request_id": trace.request_id,
            "profile": _dump(updated),
            "follow_up_questions": [_dump(f) for f in missing],
        }

    # --------------------------------------------------------------------- /plan
    def _resolve_data(self, req: dict[str, Any], profile: ExtractionProfile) -> tuple[str, CanonicalData]:
        cur = profile.fields.currency.value
        if req.get("data") is not None:
            data = req["data"]
            if cur and data.currency != cur:
                data = data.model_copy(update={"currency": cur})
        elif req.get("dataset_id"):
            data = self.datasets.get(req["dataset_id"])
            if data is None:
                raise ApiError(404, "DATASET_NOT_FOUND", f"No dataset {req['dataset_id']!r}.")
            if cur and data.currency != cur:
                data = data.model_copy(update={"currency": cur})
                with self._lock:
                    self.datasets[req["dataset_id"]] = data
            return req["dataset_id"], data
        elif req.get("products_csv") and req.get("sales_csv"):
            if not cur:
                raise ApiError(422, "CURRENCY_REQUIRED",
                               "Currency is needed to read CSV data.")
            try:
                data = load_canonical_data(req["products_csv"], req["sales_csv"],
                                           shop_id=req.get("shop_id") or "shop", currency=cur,
                                           as_of=req.get("as_of"))
            except CsvError as exc:
                raise ApiError(422, "CSV_INVALID", str(exc)) from exc
        else:
            raise ApiError(422, "DATA_REQUIRED",
                           "Provide data, dataset_id, or both products_csv and sales_csv.")
        ds_id = "ds-" + _hash(data.model_dump(mode="json"))[:12]
        with self._lock:
            self.datasets[ds_id] = data
        return ds_id, data

    def register_stores(self, req: dict[str, Any]) -> dict[str, Any]:
        """Multi-store CSVs -> one dataset per store. The plan/opportunity calls then take that
        store's ``dataset_id`` exactly as for a single shop, so stores can never mix."""
        with self._lock:
            profile = self.profiles.get(req["profile_id"])
        if profile is None:
            raise ApiError(404, "PROFILE_NOT_FOUND", f"No profile {req['profile_id']!r}.")
        cur = profile.fields.currency.value
        if not cur:
            raise ApiError(422, "CURRENCY_REQUIRED", "Currency is needed to read CSV data.")
        try:
            stores = load_canonical_stores(req["products_csv"], req["sales_csv"], currency=cur,
                                           as_of=req.get("as_of"))
        except CsvError as exc:
            raise ApiError(422, "CSV_INVALID", str(exc)) from exc
        out = []
        for sid, data in sorted(stores.items()):
            ds_id = "ds-" + _hash(data.model_dump(mode="json"))[:12]
            with self._lock:
                self.datasets[ds_id] = data
            out.append({"store_id": sid, "dataset_id": ds_id, "products": len(data.products),
                        "history_days": len({s.date for s in data.sales}), "as_of": data.as_of.isoformat()})
        return {"status": "ok", "currency": cur, "stores": out}

    def plan(self, req: dict[str, Any]) -> dict[str, Any]:
        trace = Trace(uuid.uuid4().hex[:12])
        budget, horizon = _parse_budget_and_horizon(req)

        with self._lock:
            profile = self.profiles.get(req["profile_id"])
        if profile is None:
            raise ApiError(404, "PROFILE_NOT_FOUND", f"No profile {req['profile_id']!r}.")
        language = req.get("language") or (
            profile.language if profile.language in config.SUPPORTED_LANGUAGES else "en")
        if language not in config.SUPPORTED_LANGUAGES:
            raise ApiError(422, "UNSUPPORTED_LANGUAGE",
                           f"Supported languages: {', '.join(config.SUPPORTED_LANGUAGES)}")

        follow = compute_followups(profile) if profile.status != "confirmed" else [
            f for f in compute_followups(profile) if f.reason == "missing"]
        if profile.status != "confirmed" or follow:
            self.audit.write(trace.request_id, "/plan", outcome="needs_confirmation",
                             profile_id=profile.profile_id, follow_ups=[f.field for f in follow])
            return {"status": "needs_confirmation", "request_id": trace.request_id,
                    "profile": _dump(profile), "follow_up_questions": [_dump(f) for f in follow],
                    "message": "Confirm or correct your shop details before a plan is made."}

        dataset_id, data = self._resolve_data(req, profile)
        constraints = req.get("constraints")
        if constraints is not None and not isinstance(constraints, OptimizerConstraints):
            constraints = OptimizerConstraints.model_validate(constraints)
        cur = profile.fields.currency.value
        if cur and cur != data.currency:
            trace.warn("CURRENCY_MISMATCH",
                       f"Profile currency {cur} differs from data currency {data.currency}.")

        # Component A signals are optional input: failure degrades honestly, never blocks.
        signals: SignalOutput | None = None
        try:
            signals = self._call(trace, "signals", "SignalOutput",
                                 self.m.signals.get_signals, data, data.as_of)
        except StepFailed as exc:
            trace.warn("SIGNALS_UNAVAILABLE",
                       f"Market signals unavailable ({exc.error.code}); plan uses sales and context only.")

        # Context: failure falls back to no context features (flagged), never silent.
        try:
            context: ContextFeatures = self._call(
                trace, "context", "ContextFeatures", self.m.context.build_context,
                profile, data.as_of, horizon, signals)
        except StepFailed as exc:
            trace.warn("CONTEXT_FALLBACK",
                       f"Local context unavailable ({exc.error.code}); forecast uses sales history only.")
            context = ContextFeatures(as_of=data.as_of, horizon_days=horizon, features=[])

        key = _hash({"d": data.model_dump(mode="json"), "p": profile.fields.model_dump(mode="json"),
                     "h": horizon, "s": [s.signal_id for s in signals.signals] if signals else []})
        cached = self.forecast_cache.get(key)
        try:
            if cached is not None:
                forecast, hit = cached, True
                trace.steps.append({"module": "forecaster", "status": "cached", "ms": 0.0,
                                    "error": None})
            else:
                forecast = self._call(trace, "forecaster", "ForecastOutput",
                                      self.m.forecaster.forecast, data, profile, context, horizon,
                                      signals)
                with self._lock:
                    self.forecast_cache[key] = forecast
                hit = False
            plan: OptimizerPlan = self._call(trace, "optimizer", "OptimizerPlan",
                                             self.m.optimizer.optimize, forecast, data, budget,
                                             constraints)
        except StepFailed as exc:
            raise self._fail(trace, "/plan", exc) from exc

        explanation = self._explain(trace, plan, forecast, None, language)

        request_id = trace.request_id
        with self._lock:
            self.results[request_id] = StoredResult(plan, forecast, language)
        timings = trace.timings()
        target = config.PLAN_LATENCY_WARM_SECONDS if hit else config.PLAN_LATENCY_COLD_SECONDS
        self.audit.write(request_id, "/plan", outcome="ok", profile_id=profile.profile_id,
                         dataset_id=dataset_id, budget=budget, horizon_days=horizon,
                         language=language, forecast_cache_hit=hit, steps=trace.steps,
                         warnings=trace.warnings, total_cost=plan.total_cost,
                         explanation_present=explanation is not None)
        return {
            "status": "ok",
            "request_id": request_id,
            "dataset_id": dataset_id,
            "profile_id": profile.profile_id,
            "product_names": {x.product_id: x.name for x in data.products},
            "plan": _dump(plan),
            "forecast": _dump(forecast),
            "explanation": _dump(explanation),
            "warnings": trace.warnings,
            "timings_ms": timings,
            "cache": {"forecast_hit": hit},
            "latency": {"target_seconds": target, "within_target": timings["total"] <= target * 1000},
        }

    def _explain(self, trace: Trace, plan: OptimizerPlan, forecast: ForecastOutput,
                 question: str | None, language: str) -> Explanation | None:
        """Explanation failures never block the plan: the numbers come from the optimizer."""
        try:
            exp: Explanation = self._call(trace, "explainer", "Explanation",
                                          self.m.explainer.explain, plan, forecast, question,
                                          language)
        except StepFailed as exc:
            trace.warn("EXPLANATION_UNAVAILABLE",
                       f"Explanation unavailable ({exc.error.code}); the plan figures are still valid.")
            return None
        problems = check_explanation_numbers(exp, plan)
        if problems:
            trace.warn("EXPLANATION_UNGROUNDED",
                       "The explanation contained figures not in the plan, so it was withheld.")
            trace.steps[-1]["integrity_problems"] = problems[:5]
            return None
        return exp

    # --------------------------------------------------------------------- /ask
    def ask(self, request_id: str, question: str, language: str | None) -> dict[str, Any]:
        trace = Trace(uuid.uuid4().hex[:12])
        with self._lock:
            stored = self.results.get(request_id)
        if stored is None:
            raise ApiError(404, "PLAN_NOT_FOUND", f"No plan for request {request_id!r}. Make a plan first.")
        if not question.strip():
            raise ApiError(422, "EMPTY_QUESTION", "Please type a question.")
        lang = language or stored.language
        if lang not in config.SUPPORTED_LANGUAGES:
            raise ApiError(422, "UNSUPPORTED_LANGUAGE",
                           f"Supported languages: {', '.join(config.SUPPORTED_LANGUAGES)}")
        exp = self._explain(trace, stored.plan, stored.forecast, question, lang)
        self.audit.write(trace.request_id, "/ask", outcome="ok" if exp else "error",
                         plan_request_id=request_id, question=question, language=lang,
                         steps=trace.steps, warnings=trace.warnings)
        if exp is None:
            raise ApiError(502, "EXPLANATION_UNAVAILABLE",
                           "I could not produce a grounded answer. The plan figures are unchanged.")
        return {"status": "ok", "request_id": trace.request_id, "plan_request_id": request_id,
                "explanation": _dump(exp), "warnings": trace.warnings}

    # ------------------------------------------------------------- /opportunities
    def opportunities(self, req: dict[str, Any]) -> dict[str, Any]:
        """Component D. Soft inputs (signals) degrade with a warning; the engine itself is the
        hard step. Trial orders come from the optimizer and are omitted (flagged) if it is down."""
        trace = Trace(uuid.uuid4().hex[:12])
        budget, horizon = _parse_budget_and_horizon(req)

        with self._lock:
            profile = self.profiles.get(req["profile_id"])
        if profile is None:
            raise ApiError(404, "PROFILE_NOT_FOUND", f"No profile {req['profile_id']!r}.")
        dataset_id, data = self._resolve_data(req, profile)

        catalogue = req.get("catalogue")
        source = "provided"
        if catalogue is None:
            catalogue, source = sample_catalogue(), "sample_synthetic"

        signals: SignalOutput | None = None
        try:
            signals = self._call(trace, "signals", "SignalOutput",
                                 self.m.signals.get_signals, data, data.as_of)
        except StepFailed as exc:
            trace.warn("SIGNALS_UNAVAILABLE",
                       f"Market signals unavailable ({exc.error.code}); opportunities use sales and "
                       "catalogue only.")

        trials = bool(req.get("include_trial_orders", True))
        engine = DiscoveryEngine(self.m.optimizer if trials else None)
        try:
            out: OpportunityOutput = self._call(
                trace, "opportunities", "OpportunityOutput", engine.discover,
                data, catalogue, signals, budget, horizon, trials)
        except StepFailed as exc:
            raise self._fail(trace, "/opportunities", exc) from exc
        if trials and not out.trial_orders_available and out.opportunities:
            trace.warn("TRIAL_ORDERS_UNAVAILABLE",
                       "Trial order sizes are unavailable right now. Demand ranges are still shown.")

        self.audit.write(trace.request_id, "/opportunities", outcome="ok",
                         profile_id=profile.profile_id, dataset_id=dataset_id, budget=budget,
                         horizon_days=horizon, catalogue_source=source, steps=trace.steps,
                         warnings=trace.warnings, n_opportunities=len(out.opportunities),
                         n_excluded=len(out.excluded))
        return {
            "status": "ok",
            "request_id": trace.request_id,
            "dataset_id": dataset_id,
            "catalogue_source": source,
            "opportunities": _dump(out),
            "warnings": trace.warnings,
            "timings_ms": trace.timings(),
        }

