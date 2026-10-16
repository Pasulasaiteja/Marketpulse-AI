"""
tests/test_stockouts.py
Unit tests verifying stockout flagging and missing date reindexing.
"""

import pandas as pd
from src.pipeline import flag_stockouts, reindex_continuous_dates


def test_flag_stockouts():
    df = pd.DataFrame([
        {"date": "2026-01-01", "store_id": "S1", "item_id": "I1", "sales_quantity": 10.0, "price": 100.0, "on_promotion": False},
        {"date": "2026-01-02", "store_id": "S1", "item_id": "I1", "sales_quantity": 0.0, "price": 100.0, "on_promotion": False},
    ])
    
    flagged = flag_stockouts(df)
    assert "is_stockout" in flagged.columns
    assert flagged.loc[0, "is_stockout"] == False
    assert flagged.loc[1, "is_stockout"] == True


def test_reindex_continuous_dates_fills_gaps():
    # Gap between 2026-01-01 and 2026-01-03
    df = pd.DataFrame([
        {"date": "2026-01-01", "store_id": "S1", "item_id": "I1", "sales_quantity": 10.0, "price": 100.0, "on_promotion": False},
        {"date": "2026-01-03", "store_id": "S1", "item_id": "I1", "sales_quantity": 20.0, "price": 100.0, "on_promotion": False},
    ])
    
    reindexed = reindex_continuous_dates(df)
    assert len(reindexed) == 3  # Jan 1, Jan 2 (filled), Jan 3
    assert reindexed.loc[reindexed["date"] == "2026-01-02", "sales_quantity"].values[0] == 0.0