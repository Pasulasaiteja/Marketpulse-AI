"""MOCK context builder: profile -> horizon-level context features.

No external data source is called. Economic features report
``source_available=False`` and ``fallback_used=True`` to exercise the
fallback path.
"""

from __future__ import annotations

import datetime as dt

from marketpulse.contracts.models import (
    ContextFeature,
    ContextFeatures,
    ExtractionProfile,
    SignalOutput,
)


class MockContextBuilder:
    def build_context(
        self,
        profile: ExtractionProfile,
        as_of: dt.date,
        horizon_days: int,
        signals: SignalOutput | None = None,
    ) -> ContextFeatures:
        anchors = profile.fields.nearby_anchors.value or []
        payday = profile.fields.payday_day.value
        in_window = 0.0
        if payday:
            for i in range(1, horizon_days + 1):
                if (as_of + dt.timedelta(days=i)).day == payday:
                    in_window = 1.0
        feats = [
            ContextFeature(name="near_school", value=float("school" in anchors),
                           tier="profile", is_assumption=False),
            ContextFeature(name="near_market", value=float("market" in anchors),
                           tier="profile", is_assumption=False),
            ContextFeature(name="payday_in_horizon", value=in_window,
                           tier="calendar", is_assumption=False),
            ContextFeature(name="inflation_rate", value=0.0, tier="economic",
                           is_assumption=True, source_available=False, fallback_used=True),
        ]
        return ContextFeatures(as_of=as_of, horizon_days=horizon_days, features=feats)
