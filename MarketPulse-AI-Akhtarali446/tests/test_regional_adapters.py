"""
tests/test_regional_adapters.py
Unit tests for regional adapters swapping and regional output verification.
"""

import pandas as pd
from src.regional_adapters import SouthAsiaAdapter, EcuadorAdapterStub


def test_south_asia_adapter():
    adapter = SouthAsiaAdapter()
    assert adapter.region_id == "south_asia"
    assert adapter.currency == "PKR"

    dates = pd.date_range("2026-01-01", periods=2, freq="D")
    df = adapter.get_context_features(dates, ["STORE_001"])

    assert not df.empty
    assert "is_friday_market" in df["feature_name"].values
    assert (df["source"] == "south_asia").all()


def test_ecuador_adapter_stub():
    adapter = EcuadorAdapterStub()
    assert adapter.region_id == "ecuador"
    assert adapter.currency == "USD"

    dates = pd.date_range("2026-01-01", periods=2, freq="D")
    df = adapter.get_context_features(dates, ["STORE_003"])

    assert not df.empty
    assert (df["source"] == "ecuador").all()