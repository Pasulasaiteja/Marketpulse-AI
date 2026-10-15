"""
src/regional_adapters/south_asia.py
Regional context adapter for South Asia (Pakistan/India context, PKR currency).
"""

from typing import List
import pandas as pd
from .base import BaseRegionalAdapter


class SouthAsiaAdapter(BaseRegionalAdapter):
    @property
    def region_id(self) -> str:
        return "south_asia"

    @property
    def currency(self) -> str:
        return "PKR"

    def get_context_features(
        self, 
        dates: pd.DatetimeIndex, 
        store_ids: List[str]
    ) -> pd.DataFrame:
        records = []

        for d in dates:
            # Tier 1: Calendar & Local Events
            is_payday = 1.0 if d.day in [1, 15, 30] or d.is_month_end else 0.0
            is_friday_market = 1.0 if d.dayofweek == 4 else 0.0

            # Tier 2: Economic Indicators
            inflation_rate_pkr = 22.5

            # Tier 3: Regional Shocks / Seasons (Monsoon July-August)
            is_monsoon = 1.0 if d.month in [7, 8] else 0.0

            for store_id in store_ids:
                records.extend([
                    {"date": d, "store_id": store_id, "feature_name": "is_payday", "value": float(is_payday), "source": self.region_id, "is_fallback": False},
                    {"date": d, "store_id": store_id, "feature_name": "is_friday_market", "value": float(is_friday_market), "source": self.region_id, "is_fallback": False},
                    {"date": d, "store_id": store_id, "feature_name": "inflation_rate", "value": float(inflation_rate_pkr), "source": self.region_id, "is_fallback": False},
                    {"date": d, "store_id": store_id, "feature_name": "is_monsoon", "value": float(is_monsoon), "source": self.region_id, "is_fallback": False},
                ])

        return pd.DataFrame(records)