"""
Market Signal Intelligence Pipeline (Component A).
Connects statistical change-point detection and NLP feedback classification.
Outputs structured signals conforming strictly to CONTRACT.md.
"""

import numpy as np
import pandas as pd
from typing import Any
import uuid
from .change_point import ChangePointDetector
from .nlp_classifier import CustomerReviewClassifier


class MarketSignalPipeline:
    """
    Orchestrates Component A: extracts structured market signals with evidence and confidence.
    """
    def __init__(
        self,
        change_point_detector: ChangePointDetector | None = None,
        nlp_classifier: CustomerReviewClassifier | None = None
    ):
        self.cp_detector = change_point_detector or ChangePointDetector()
        self.nlp_classifier = nlp_classifier or CustomerReviewClassifier()

    def fit_nlp(self, df_reviews: pd.DataFrame) -> "MarketSignalPipeline":
        """Fits the NLP classifier if labeled reviews are available."""
        if "text" in df_reviews.columns and "ground_truth_intent" in df_reviews.columns:
            valid = df_reviews.dropna(subset=["text", "ground_truth_intent"])
            if len(valid) > 0:
                self.nlp_classifier.fit(valid["text"].tolist(), valid["ground_truth_intent"].tolist())
        return self

    def extract_signals(
        self,
        df_sales: pd.DataFrame,
        df_reviews: pd.DataFrame | None = None,
        store_id: str | None = None
    ) -> pd.DataFrame:
        """
        Extracts both statistical sales pattern shifts and NLP review signals.
        Returns a DataFrame strictly conforming to the contract:
        [signal_id, product_or_category, type, evidence, confidence, date]
        """
        records = []
        sig_counter = 1
        
        # 1. Statistical Change-Point Signals
        cp_signals = self.cp_detector.detect_shifts(df_sales, store_id=store_id)
        for s in cp_signals:
            date_clean = s["date"].replace("-", "")
            sig_id = f"SIG_{date_clean}_{sig_counter:04d}"
            sig_counter += 1
            records.append({
                "signal_id": sig_id,
                "product_or_category": s["product_or_category"],
                "type": s["type"],
                "evidence": s["evidence"],
                "confidence": s["confidence"],
                "date": s["date"]
            })
            
        # 2. NLP Feedback Signals
        if df_reviews is not None and not df_reviews.empty:
            rev_df = df_reviews.copy()
            if store_id and "store_id" in rev_df.columns:
                rev_df = rev_df[rev_df["store_id"] == store_id]
                
            for _, r in rev_df.iterrows():
                text = r["text"]
                intent, conf, evidence = self.nlp_classifier.predict_one(text)
                if intent != "NEUTRAL":
                    dt_str = str(r["date"])
                    date_clean = dt_str.replace("-", "")
                    sig_id = f"SIG_{date_clean}_{sig_counter:04d}"
                    sig_counter += 1
                    
                    prod_or_cat = r.get("product_or_category", "GENERAL")
                    records.append({
                        "signal_id": sig_id,
                        "product_or_category": prod_or_cat,
                        "type": intent,
                        "evidence": evidence,
                        "confidence": conf,
                        "date": dt_str
                    })
                    
        schema_cols = ["signal_id", "product_or_category", "type", "evidence", "confidence", "date"]
        if not records:
            return pd.DataFrame(columns=schema_cols)
            
        df_res = pd.DataFrame(records)[schema_cols]
        return df_res.sort_values("date").reset_index(drop=True)


def detect_all_signals(
    df_sales: pd.DataFrame,
    df_reviews: pd.DataFrame | None = None,
    store_id: str | None = None
) -> pd.DataFrame:
    """Convenience helper function to run the full signal pipeline."""
    pipeline = MarketSignalPipeline()
    if df_reviews is not None:
        pipeline.fit_nlp(df_reviews)
    return pipeline.extract_signals(df_sales, df_reviews, store_id=store_id)
