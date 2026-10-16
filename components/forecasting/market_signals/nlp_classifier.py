"""
NLP Pipeline for Retail Review & Feedback Intent Classification.
Classifies text into:
- CUSTOMER_NEED: Inquiries for missing stock, unavailable pack sizes, out-of-stock essentials.
- CUSTOMER_COMPLAINT: Shelf stockouts, spoiled goods, price gouging, bad service.
- EMERGING_PREFERENCE: Trending products, health food shifts, regional demand patterns.
- NEUTRAL: General feedback.
"""

import numpy as np
import pandas as pd
from typing import Any
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline


class CustomerReviewClassifier:
    """
    Hybrid NLP Classifier combining domain lexicon features with a calibrated ML pipeline.
    """
    def __init__(self):
        self.pipeline: Pipeline | None = None
        self.is_fitted: bool = False
        
        # Domain seed keywords
        self.need_keywords = [
            "need", "do you carry", "please stock", "looking for", "out of stock",
            "bring", "lactose free", "gluten free", "smaller bottle", "available"
        ]
        self.complaint_keywords = [
            "empty", "empty shelf", "leaking", "stale", "expired", "expensive",
            "terrible", "bad", "high price", "complaint", "rude", "poor"
        ]
        self.preference_keywords = [
            "trending", "popular", "gym", "clean", "zero sugar", "organic",
            "plant based", "students", "everyone is talking", "cold brew", "sparkling", "hydration"
        ]

    def _rule_predict(self, text: str) -> tuple[str, float]:
        """Heuristic rule matcher for zero-shot or cold-start fallback."""
        lower = text.lower()
        score_need = sum(1 for kw in self.need_keywords if kw in lower)
        score_comp = sum(1 for kw in self.complaint_keywords if kw in lower)
        score_pref = sum(1 for kw in self.preference_keywords if kw in lower)
        
        scores = {
            "CUSTOMER_NEED": score_need,
            "CUSTOMER_COMPLAINT": score_comp,
            "EMERGING_PREFERENCE": score_pref
        }
        max_intent, max_score = max(scores.items(), key=lambda x: x[1])
        if max_score == 0:
            return "NEUTRAL", 0.50
        conf = min(0.95, 0.65 + 0.10 * max_score)
        return max_intent, conf

    def fit(self, labeled_texts: list[str], labels: list[str]) -> "CustomerReviewClassifier":
        """
        Fits a TF-IDF + Logistic Regression pipeline on labeled examples.
        Maps labels (e.g. NEED, COMPLAINT, PREFERENCE) to target classes.
        """
        clean_labels = []
        for l in labels:
            if "NEED" in l:
                clean_labels.append("CUSTOMER_NEED")
            elif "COMPLAINT" in l:
                clean_labels.append("CUSTOMER_COMPLAINT")
            elif "PREF" in l:
                clean_labels.append("EMERGING_PREFERENCE")
            else:
                clean_labels.append("NEUTRAL")
                
        self.pipeline = Pipeline([
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=1, lowercase=True)),
            ("clf", LogisticRegression(C=2.0, max_iter=200, random_state=42))
        ])
        self.pipeline.fit(labeled_texts, clean_labels)
        self.is_fitted = True
        return self

    def predict_one(self, text: str) -> tuple[str, float, str]:
        """
        Classifies a single review string.
        Returns: (intent_type, confidence, evidence_snippet)
        """
        if self.is_fitted and self.pipeline is not None:
            pred_class = self.pipeline.predict([text])[0]
            probs = self.pipeline.predict_proba([text])[0]
            conf = float(np.max(probs))
            # Blended with rule score for high reliability on short retail texts
            rule_class, rule_conf = self._rule_predict(text)
            if rule_class != "NEUTRAL":
                final_class = rule_class if rule_conf > conf else pred_class
                final_conf = max(conf, rule_conf)
            else:
                final_class = pred_class
                final_conf = conf
        else:
            final_class, final_conf = self._rule_predict(text)
            
        evidence = f"Customer review excerpt: \"{text.strip()}\""
        return final_class, round(float(final_conf), 2), evidence
