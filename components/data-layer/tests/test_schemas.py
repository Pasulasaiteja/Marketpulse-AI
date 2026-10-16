import pytest
import pandas as pd
from src.canonical_schemas import validate_dataframe, pivot_context


@pytest.fixture
def sample_sales_df():
    return pd.DataFrame([
        {
            "date": "2026-10-01",
            "store_id": "STORE_001",
            "item_id": "ITEM_101",
            "sales_quantity": 15.0,
            "price": 120.0,
            "on_promotion": False,
        }
    ])


@pytest.fixture
def sample_context_df():
    return pd.DataFrame([
        {"date": "2026-10-01", "store_id": "STORE_001", "feature_name": "is_payday", "value": 1.0, "source": "adapter", "is_fallback": False},
        {"date": "2026-10-01", "store_id": "STORE_001", "feature_name": "temperature_c", "value": 30.5, "source": "adapter", "is_fallback": False},
        {"date": "2026-10-01", "store_id": "STORE_002", "feature_name": "is_payday", "value": 1.0, "source": "adapter", "is_fallback": False},
        {"date": "2026-10-01", "store_id": "STORE_002", "feature_name": "temperature_c", "value": 25.0, "source": "fallback", "is_fallback": True},
    ])


def test_sales_df_validation_pass(sample_sales_df):
    validated = validate_dataframe(sample_sales_df, "sales")
    assert pd.api.types.is_datetime64_any_dtype(validated["date"])
    assert validated.loc[0, "sales_quantity"] == 15.0


def test_sales_df_missing_columns_raises():
    invalid_df = pd.DataFrame([{"date": "2026-10-01", "store_id": "STORE_001"}])
    with pytest.raises(ValueError, match="missing columns"):
        validate_dataframe(invalid_df, "sales")


def test_sales_df_negative_quantity_raises(sample_sales_df):
    sample_sales_df.loc[0, "sales_quantity"] = -5.0
    with pytest.raises(ValueError, match="cannot contain negative values"):
        validate_dataframe(sample_sales_df, "sales")


def test_pivot_context_transformation(sample_context_df):
    wide_context = pivot_context(sample_context_df)
    assert "is_payday" in wide_context.columns
    assert "temperature_c" in wide_context.columns
    assert wide_context.shape[0] == 2