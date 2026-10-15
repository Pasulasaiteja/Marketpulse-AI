"""
tests/test_fallbacks.py
Unit tests verifying graceful handling of missing regional adapters and fallback flags.
"""

import pandas as pd
from src.context_layer import ContextEngine


def test_fallback_triggers_for_unknown_region():
    engine = ContextEngine()
    dates = pd.date_range("2026-01-01", periods=2, freq="D")
    
    fallback_df = engine.fetch_context("unknown_region", dates, ["STORE_999"])

    assert not fallback_df.empty
    assert (fallback_df["is_fallback"] == True).all()
    assert (fallback_df["source"] == "default_fallback").all()