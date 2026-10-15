"""The ONE place where modules are chosen.

To swap a mock for a real module, change the matching line in
``default_modules()`` (or pass your own ``Modules`` to ``create_app``).
"""

from __future__ import annotations

from dataclasses import dataclass

from marketpulse.contracts import interfaces as i
from marketpulse.mocks.context import MockContextBuilder
from marketpulse.mocks.explainer import MockExplainer
from marketpulse.mocks.extractor import MockExtractor
from marketpulse.mocks.forecaster import MockForecaster
from marketpulse.mocks.optimizer import MockOptimizer
from marketpulse.mocks.signals import MockSignalProvider


@dataclass
class Modules:
    extractor: i.Extractor
    context: i.ContextBuilder
    forecaster: i.Forecaster
    optimizer: i.Optimizer
    explainer: i.Explainer
    signals: i.SignalProvider


def mock_modules() -> Modules:
    """Mock modules for testing against stubs."""
    return Modules(
        extractor=MockExtractor(),
        context=MockContextBuilder(),
        forecaster=MockForecaster(),
        optimizer=MockOptimizer(),
        explainer=MockExplainer(),
        signals=MockSignalProvider(),
    )


def default_modules() -> Modules:
    """Returns the live integrated team modules by default, with mock fallback if explicitly requested.

    Enforces strict posture: never silently falls back to mocks on initialization failure.
    Mocks are only loaded when MARKETPULSE_USE_MOCKS=1 (or true/yes) is explicitly set.
    """
    import os
    if os.environ.get("MARKETPULSE_USE_MOCKS", "").strip().lower() in {"1", "true", "yes"}:
        return mock_modules()
    from marketpulse.adapters.team_modules import integrated_modules
    return Modules(**integrated_modules())


