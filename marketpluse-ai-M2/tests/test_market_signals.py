"""
Tests for Component A: Market Signal Intelligence.
Validates:
- Statistical change-point detection (CUSUM)
- NLP intent classification on customer reviews
- Contract schema compliance for signals
"""

import pytest
import numpy as np
import pandas as pd
from mock_data.generator import generate_synthetic_data
from market_signals.change_point import ChangePointDetector
from market_signals.nlp_classifier import CustomerReviewClassifier
from market_signals.pipeline import MarketSignalPipeline, detect_all_signals


@pytest.fixture(scope="module")
def mock_dataset():
    return generate_synthetic_data()


def test_change_point_detection(mock_dataset):
    df_sales = mock_dataset["sales"]
    detector = ChangePointDetector(baseline_window=14, decision_threshold=3.5)
    
    # Run detector on STORE_001 cooking oil (which had historical transport shock spike)
    signals = detector.detect_shifts(df_sales, store_id="STORE_001", product_id="PROD_COOKING_OIL_1L")
    assert len(signals) > 0
    
    first_sig = signals[0]
    assert "product_or_category" in first_sig
    assert first_sig["type"] in ["CHANGE_POINT_SPIKE", "CHANGE_POINT_DROP"]
    assert "CUSUM" in first_sig["evidence"]
    assert 0.0 <= first_sig["confidence"] <= 1.0


def test_nlp_customer_review_classification(mock_dataset):
    df_reviews = mock_dataset["reviews"]
    clf = CustomerReviewClassifier()
    clf.fit(df_reviews["text"].tolist(), df_reviews["ground_truth_intent"].tolist())
    
    # Test unseen sample sentences
    need_text = "Can you please stock almond milk or vegan butter?"
    comp_text = "The bread was expired and moldy, very disappointed with the quality."
    pref_text = "Zero sugar hydration drinks are trending everywhere right now."
    
    pred_need, conf_need, ev_need = clf.predict_one(need_text)
    pred_comp, conf_comp, ev_comp = clf.predict_one(comp_text)
    pred_pref, conf_pref, ev_pref = clf.predict_one(pref_text)
    
    assert pred_need == "CUSTOMER_NEED"
    assert pred_comp == "CUSTOMER_COMPLAINT"
    assert pred_pref == "EMERGING_PREFERENCE"
    
    assert conf_need >= 0.50
    assert conf_comp >= 0.50
    assert conf_pref >= 0.50


def test_market_signal_output_contract(mock_dataset):
    df_sales = mock_dataset["sales"]
    df_reviews = mock_dataset["reviews"]
    
    pipeline = MarketSignalPipeline()
    pipeline.fit_nlp(df_reviews)
    signals_df = pipeline.extract_signals(df_sales, df_reviews, store_id="STORE_001")
    
    # Strict Contract Validation
    expected_cols = ["signal_id", "product_or_category", "type", "evidence", "confidence", "date"]
    assert list(signals_df.columns) == expected_cols
    assert len(signals_df) > 0
    
    # Verify field formats
    for _, row in signals_df.iterrows():
        assert row["signal_id"].startswith("SIG_")
        assert isinstance(row["product_or_category"], str)
        assert row["type"] in ["CHANGE_POINT_SPIKE", "CHANGE_POINT_DROP", "CUSTOMER_NEED", "CUSTOMER_COMPLAINT", "EMERGING_PREFERENCE"]
        assert len(row["evidence"]) > 10
        assert 0.0 <= row["confidence"] <= 1.0
        # Valid date format YYYY-MM-DD
        pd.to_datetime(row["date"])
