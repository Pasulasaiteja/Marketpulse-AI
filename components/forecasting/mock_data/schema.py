"""
Schema definitions for Member 1 mock datasets.
"""

from pydantic import BaseModel, Field
from typing import Optional


class DailySalesRecord(BaseModel):
    date: str = Field(..., description="Date YYYY-MM-DD")
    store_id: str = Field(..., description="Store identifier")
    product_id: str = Field(..., description="Product identifier")
    category: str = Field(..., description="Product category")
    units_sold: float = Field(..., ge=0, description="Observed units sold")
    on_promotion: int = Field(default=0, ge=0, le=1)


class ContextRecord(BaseModel):
    date: str
    day_of_week: int = Field(..., ge=0, le=6)
    is_weekend: int = Field(..., ge=0, le=1)
    month: int = Field(..., ge=1, le=12)
    day_of_month: int = Field(..., ge=1, le=31)
    payday_flag: int = Field(default=0, ge=0, le=1)
    holiday_flag: int = Field(default=0, ge=0, le=1)
    inflation_index: float = Field(default=100.0)
    fuel_price_index: float = Field(default=100.0)
    shock_flag: int = Field(default=0, ge=0, le=1)
    shock_type: str = Field(default="NONE")


class ReviewRecord(BaseModel):
    review_id: str
    date: str
    store_id: str
    product_or_category: str
    text: str
    ground_truth_intent: Optional[str] = None  # "NEED", "COMPLAINT", "PREFERENCE", "NEUTRAL"
