"""
src/regional_adapters/ecuador_stub.py
Stub regional context adapter for Ecuador (USD currency, Ecuadorian holiday calendar).
"""

from typing import List
import pandas as pd
from .base import BaseRegionalAdapter


class EcuadorAdapterStub(BaseRegionalAdapter):
    @property
    def region_id(self) -> str:
        return "ecuador"

    @property
    def currency(self) -> str:
        return "USD"

    def get_context_features(
        self, 
        dates: pd.DatetimeIndex, 
        store_ids: List[str]
    ) -> pd.DataFrame:
        records = []

        for d in dates:
            is_payday = 1.0 if d.day == 15 or d.is_month_end else 0.0
            inflation_rate_usd = 2.1

            for store_id in store_ids:
                records.extend([
                    {"date": d, "store_id": store_id, "feature_name": "is_payday", "value": float(is_payday), "source": self.region_id, "is_fallback": False},
                    {"date": d, "store_id": store_id, "feature_name": "inflation_rate", "value": float(inflation_rate_usd), "source": self.region_id, "is_fallback": False},
                ])

        return pd.DataFrame(records)