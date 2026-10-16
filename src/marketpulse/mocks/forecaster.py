"""MOCK forecaster (stands in for Member 2's module).

Method: trailing-window mean of daily units (days with no record count as 0),
normal-approximation quantiles, multiplicative context effects.
All constants below are ASSUMPTIONS, not learned from data.
"""

from __future__ import annotations

import datetime as dt
import math
from statistics import NormalDist, mean, pstdev

from marketpulse import config
from marketpulse.contracts.models import (
    CanonicalData,
    ContextFeatures,
    ExtractionProfile,
    ForecastOutput,
    ProductForecast,
    QuantilePoint,
    SignalOutput,
)

WINDOW_DAYS = 28  # ASSUMPTION: trailing window length
LOW_DATA_DAYS = 28  # ASSUMPTION: fewer observed days than this => low_data
EFFECTS = {  # ASSUMPTION: hand-set multiplicative effects, wide uncertainty, NOT learned
    "near_school": 0.05,
    "near_market": 0.08,
    "payday_in_horizon": 0.10,
}
INTERVAL_PAD = 1.25  # ASSUMPTION: widen sigma to reflect unvalidated effects


class MockForecaster:
    def forecast(
        self,
        data: CanonicalData,
        profile: ExtractionProfile,
        context: ContextFeatures,
        horizon_days: int,
        signals: SignalOutput | None = None,
    ) -> ForecastOutput:
        start = data.as_of - dt.timedelta(days=WINDOW_DAYS - 1)
        feat = {f.name: f.value for f in context.features}
        mult = 1.0 + sum(EFFECTS[k] * feat.get(k, 0.0) for k in EFFECTS)
        sigma_pad = INTERVAL_PAD
        for a in context.alerts:
            sigma_pad *= a.widen_interval_factor
        out = []
        for p in data.products:
            rows = [s for s in data.sales if s.product_id == p.product_id and s.date <= data.as_of]
            hist_days = len({s.date for s in rows})
            daily: dict[dt.date, float] = {}
            for s in rows:
                if s.date >= start:
                    daily[s.date] = daily.get(s.date, 0.0) + s.units_sold
            series = [daily.get(start + dt.timedelta(days=i), 0.0) for i in range(WINDOW_DAYS)]
            mu_d, sd_d = (mean(series), pstdev(series)) if hist_days else (0.0, 0.0)
            mu = mu_d * horizon_days * mult
            sd = sd_d * math.sqrt(horizon_days) * sigma_pad
            nd = NormalDist(mu, sd) if sd > 0 else None
            qs = [
                QuantilePoint(
                    p=q,
                    value=round(max(0.0, nd.inv_cdf(q) if nd else mu), 2),
                )
                for q in config.QUANTILE_GRID
            ]
            out.append(
                ProductForecast(
                    product_id=p.product_id,
                    mean=round(max(0.0, mu), 2),
                    quantiles=qs,
                    history_days=hist_days,
                    low_data=hist_days < LOW_DATA_DAYS,
                    cold_start=hist_days == 0,
                )
            )
        used = [f.name for f in context.features if f.name in EFFECTS and f.value]
        return ForecastOutput(
            as_of=data.as_of,
            horizon_days=horizon_days,
            model_name="MOCK-trailing-mean-normal",
            context_features_used=used,
            signals_used=[],  # mock never lets unvalidated signals move forecasts
            forecasts=out,
        )
