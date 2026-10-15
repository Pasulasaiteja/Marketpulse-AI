"""
src/context_layer.py
Unified context enrichment engine with audit timestamps and fallback resilience.
"""

from typing import Dict, List
import pandas as pd

from src.canonical_schemas import validate_dataframe
from src.regional_adapters import BaseRegionalAdapter, SouthAsiaAdapter, EcuadorAdapterStub


class ContextEngine:
    def __init__(self):
        self.adapters: Dict[str, BaseRegionalAdapter] = {
            "south_asia": SouthAsiaAdapter(),
            "ecuador": EcuadorAdapterStub(),
        }

    def register_adapter(self, adapter: BaseRegionalAdapter) -> None:
        self.adapters[adapter.region_id] = adapter

    def build_default_fallback_context(
        self, 
        dates: pd.DatetimeIndex, 
        store_ids: List[str]
    ) -> pd.DataFrame:
        records = []
        fetch_ts = pd.Timestamp.now().isoformat()
        
        for d in dates:
            for store_id in store_ids:
                records.extend([
                    {"date": d, "store_id": store_id, "feature_name": "is_payday", "value": 0.0, "source": "default_fallback", "is_fallback": True, "fetch_timestamp": fetch_ts},
                    {"date": d, "store_id": store_id, "feature_name": "inflation_rate", "value": 0.0, "source": "default_fallback", "is_fallback": True, "fetch_timestamp": fetch_ts},
                ])
        return pd.DataFrame(records)

    def fetch_context(
        self, 
        region_id: str, 
        dates: pd.DatetimeIndex, 
        store_ids: List[str]
    ) -> pd.DataFrame:
        fetch_ts = pd.Timestamp.now().isoformat()
        
        if region_id in self.adapters:
            try:
                adapter = self.adapters[region_id]
                context_df = adapter.get_context_features(dates, store_ids)
                context_df["fetch_timestamp"] = fetch_ts
                return validate_dataframe(context_df, "context")
            except Exception:
                pass

        fallback_df = self.build_default_fallback_context(dates, store_ids)
        return validate_dataframe(fallback_df, "context")