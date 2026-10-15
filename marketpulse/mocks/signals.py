"""MOCK signal provider (stands in for Component A / Member 1)."""

from __future__ import annotations

import datetime as dt

from marketpulse.contracts.models import CanonicalData, Evidence, Signal, SignalOutput


class MockSignalProvider:
    def get_signals(self, data: CanonicalData | None, as_of: dt.date) -> SignalOutput:
        return SignalOutput(
            generated_at=as_of,
            signals=[
                Signal(
                    signal_id="S-001", type="demand_shift", product_id="P002",
                    direction="up", magnitude=0.15, confidence=0.6,
                    predictive_value_established=False, observed=True,
                    evidence=[Evidence(source="sales_history", summary="MOCK evidence")],
                ),
                Signal(
                    signal_id="S-002", type="unmet_demand", category="beverages",
                    direction="up", magnitude=None, confidence=0.5,
                    predictive_value_established=False, observed=True,
                    evidence=[Evidence(source="reviews", summary="MOCK: customers ask for juice")],
                ),
                Signal(
                    signal_id="S-003", type="category_growth", category="beverages",
                    direction="up", magnitude=0.2, confidence=0.55,
                    predictive_value_established=False, observed=True,
                    evidence=[Evidence(source="catalogue", summary="MOCK category trend")],
                ),
            ],
        )
