"""
Mock Data Module for Member 1 Contracts.
Provides synthetic retail datasets with ground-truth seasonal, payday, shock, and sparse effects.
"""

from .generator import generate_synthetic_data, load_or_generate_mock_dataset
from .schema import DailySalesRecord, ContextRecord, ReviewRecord

__all__ = [
    "generate_synthetic_data",
    "load_or_generate_mock_dataset",
    "DailySalesRecord",
    "ContextRecord",
    "ReviewRecord"
]
