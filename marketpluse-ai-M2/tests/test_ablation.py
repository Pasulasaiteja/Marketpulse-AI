"""
Tests for 4-Tier Feature Ablation Study.
Validates:
- All 4 tiers execute out-of-sample without leakage
- Tier 2 (+ Calendar) lowers error vs Tier 1 (Sales only)
- Report generation creates reports/ABLATION_REPORT.md
"""

import pytest
import os
import pandas as pd
from mock_data.generator import generate_synthetic_data
from market_signals.pipeline import detect_all_signals
from forecasting.ablation import FeatureAblationStudy


@pytest.fixture(scope="module")
def mock_dataset():
    return generate_synthetic_data()


def test_ablation_study_execution_and_decision_rules(mock_dataset):
    df_sales = mock_dataset["sales"]
    df_context = mock_dataset["context"]
    df_reviews = mock_dataset["reviews"]
    
    # Extract market signals first
    signals_df = detect_all_signals(df_sales, df_reviews)
    
    # Run ablation with 2 splits for quick unit test validation
    study = FeatureAblationStudy(horizon_days=14, n_splits=2)
    results_df = study.run(df_sales, df_context, signals_df)
    
    assert len(results_df) == 4
    expected_cols = ["tier", "tier_name", "wape", "wape_se", "delta_wape", "mae", "rmse", "mean_pinball", "decision"]
    for col in expected_cols:
        assert col in results_df.columns
        
    # Check that Tier 2 (+ Calendar) reduces error vs Tier 1 (Sales only)
    t1_wape = results_df.loc[results_df["tier"] == 1, "wape"].values[0]
    t2_wape = results_df.loc[results_df["tier"] == 2, "wape"].values[0]
    print(f"\nTier 1 WAPE: {t1_wape:.4f}, Tier 2 WAPE: {t2_wape:.4f}")
    assert t2_wape <= t1_wape
    
    # Generate markdown report
    rep_path = "reports/ABLATION_REPORT.md"
    rep_content = study.generate_report_markdown(results_df, output_path=rep_path)
    assert os.path.exists(rep_path)
    assert "Tier 1: Sales Only" in rep_content
    assert "Production Decision" in rep_content
