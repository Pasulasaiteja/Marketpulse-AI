from typing import Dict, List, Literal
import pandas as pd
from pydantic import BaseModel, Field, ConfigDict


# -------------------------------------------------------------------
# 1. Row-Level Pydantic Models
# -------------------------------------------------------------------

class SalesRecord(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    date: pd.Timestamp
    store_id: str = Field(..., min_length=1)
    item_id: str = Field(..., min_length=1)
    sales_quantity: float = Field(ge=0.0)
    price: float = Field(gt=0.0)
    on_promotion: bool


class StoreRecord(BaseModel):
    store_id: str = Field(..., min_length=1)
    store_name: str = Field(..., min_length=1)
    location_type: Literal["urban_flagship", "suburban_medium", "rural_kiosk"]
    population_class: Literal["high_density", "medium_density", "low_density"]
    region_id: str = Field(..., min_length=1)


class ItemRecord(BaseModel):
    item_id: str = Field(..., min_length=1)
    category_id: str = Field(..., min_length=1)
    cost_price: float = Field(gt=0.0)
    selling_price: float = Field(gt=0.0)


class ContextRecord(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    date: pd.Timestamp
    store_id: str = Field(..., min_length=1)
    feature_name: str = Field(..., min_length=1)
    value: float
    source: str = Field(..., min_length=1)
    is_fallback: bool


# -------------------------------------------------------------------
# 2. DataFrame Validation Rules
# -------------------------------------------------------------------

REQUIRED_COLUMNS: Dict[str, List[str]] = {
    "sales": ["date", "store_id", "item_id", "sales_quantity", "price", "on_promotion"],
    "stores": ["store_id", "store_name", "location_type", "population_class", "region_id"],
    "items": ["item_id", "category_id", "cost_price", "selling_price"],
    "context": ["date", "store_id", "feature_name", "value", "source", "is_fallback"],
}


def validate_dataframe(df: pd.DataFrame, schema_type: str) -> pd.DataFrame:
    """Validates required columns, types, and constraints for DataFrames."""
    if schema_type not in REQUIRED_COLUMNS:
        raise ValueError(f"Unknown schema_type '{schema_type}'. Supported: {list(REQUIRED_COLUMNS.keys())}")

    if df.empty:
        raise ValueError(f"DataFrame for '{schema_type}' is empty.")

    missing = [col for col in REQUIRED_COLUMNS[schema_type] if col not in df.columns]
    if missing:
        raise ValueError(f"DataFrame missing columns for '{schema_type}': {missing}")

    validated = df.copy()

    if schema_type == "sales":
        validated["date"] = pd.to_datetime(validated["date"])
        validated["sales_quantity"] = validated["sales_quantity"].astype(float)
        validated["price"] = validated["price"].astype(float)
        validated["on_promotion"] = validated["on_promotion"].astype(bool)

        if (validated["sales_quantity"] < 0).any():
            raise ValueError("Schema error: 'sales_quantity' cannot contain negative values.")
        if (validated["price"] <= 0).any():
            raise ValueError("Schema error: 'price' must be strictly positive.")

    elif schema_type == "stores":
        for col in REQUIRED_COLUMNS["stores"]:
            validated[col] = validated[col].astype(str)

    elif schema_type == "items":
        validated["cost_price"] = validated["cost_price"].astype(float)
        validated["selling_price"] = validated["selling_price"].astype(float)
        if (validated["cost_price"] <= 0).any() or (validated["selling_price"] <= 0).any():
            raise ValueError("Schema error: Prices must be > 0.")

    elif schema_type == "context":
        validated["date"] = pd.to_datetime(validated["date"])
        validated["value"] = validated["value"].astype(float)
        validated["is_fallback"] = validated["is_fallback"].astype(bool)

    return validated


# -------------------------------------------------------------------
# 3. Context Helper
# -------------------------------------------------------------------

def pivot_context(context_df: pd.DataFrame) -> pd.DataFrame:
    """Converts canonical long-format context_df into wide-format indexed by (date, store_id)."""
    validated = validate_dataframe(context_df, "context")

    wide_df = validated.pivot_table(
        index=["date", "store_id"],
        columns="feature_name",
        values="value",
        aggfunc="first"
    ).reset_index()

    wide_df.columns.name = None
    return wide_df