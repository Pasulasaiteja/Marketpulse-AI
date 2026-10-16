"""
src/regional_adapters/base.py
Abstract base class defining interface contracts for regional context adapters.
"""

from abc import ABC, abstractmethod
from typing import List
import pandas as pd


class BaseRegionalAdapter(ABC):
    """Abstract Base Class for all regional context adapters."""

    @property
    @abstractmethod
    def region_id(self) -> str:
        """Returns the unique region identifier (e.g., 'south_asia', 'ecuador')."""
        pass

    @property
    @abstractmethod
    def currency(self) -> str:
        """Returns the regional standard currency code (e.g., 'PKR', 'USD')."""
        pass

    @abstractmethod
    def get_context_features(
        self, 
        dates: pd.DatetimeIndex, 
        store_ids: List[str]
    ) -> pd.DataFrame:
        """
        Generates canonical long-format context records for requested dates and store IDs.
        Returns DataFrame with schema: [date, store_id, feature_name, value, source, is_fallback]
        """
        pass