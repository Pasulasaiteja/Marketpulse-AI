"""Function signatures every module must expose (see CONTRACT.md).

Real modules and mocks both satisfy these Protocols, so the API swaps them
without code changes. Each function is pure with respect to its arguments.
Modules raise ``ModuleFailure`` on error; they never return partial garbage.
"""

from __future__ import annotations

import datetime as dt
from typing import Protocol, runtime_checkable

from marketpulse.contracts.models import (
    CanonicalData,
    ContextFeatures,
    Explanation,
    ExtractionProfile,
    ForecastOutput,
    OptimizerConstraints,
    OptimizerPlan,
    SignalOutput,
)


@runtime_checkable
class Extractor(Protocol):
    def extract_profile(
        self, description: str, language_hint: str | None = None
    ) -> ExtractionProfile: ...


@runtime_checkable
class ContextBuilder(Protocol):
    def build_context(
        self,
        profile: ExtractionProfile,
        as_of: dt.date,
        horizon_days: int,
        signals: SignalOutput | None = None,
    ) -> ContextFeatures: ...


@runtime_checkable
class Forecaster(Protocol):
    def forecast(
        self,
        data: CanonicalData,
        profile: ExtractionProfile,
        context: ContextFeatures,
        horizon_days: int,
        signals: SignalOutput | None = None,
    ) -> ForecastOutput: ...


@runtime_checkable
class Optimizer(Protocol):
    def optimize(
        self,
        forecast: ForecastOutput,
        data: CanonicalData,
        budget: float,
        constraints: OptimizerConstraints | None = None,
    ) -> OptimizerPlan: ...


@runtime_checkable
class Explainer(Protocol):
    def explain(
        self,
        plan: OptimizerPlan,
        forecast: ForecastOutput,
        question: str | None = None,
        language: str = "en",
    ) -> Explanation: ...


@runtime_checkable
class SignalProvider(Protocol):
    def get_signals(self, data: CanonicalData | None, as_of: dt.date) -> SignalOutput: ...
