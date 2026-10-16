"""
Component A: Market Signal Intelligence.
Provides statistical change-point detection and NLP customer review intent classification.
"""

from .pipeline import MarketSignalPipeline, detect_all_signals
from .change_point import ChangePointDetector
from .nlp_classifier import CustomerReviewClassifier

__all__ = [
    "MarketSignalPipeline",
    "detect_all_signals",
    "ChangePointDetector",
    "CustomerReviewClassifier"
]
