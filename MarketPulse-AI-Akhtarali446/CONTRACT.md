# Shared Data Contract Specification (`CONTRACT.md`)

This document defines the canonical schemas, data contracts, and public API interfaces across the data and context layer.

---

## 1. Primary Entity Schemas

### A. Sales Transactions (`sales_df`)
| Column | Data Type | Constraints / Description |
| :--- | :--- | :--- |
| `date` | `datetime64[ns]` | Transaction timestamp (`YYYY-MM-DD`). |
| `store_id` | `str` | Unique identifier for store location. |
| `item_id` | `str` | Unique identifier for product item. |
| `sales_quantity` | `float64` | Observed sales volume. Must be >= 0.0. |
| `price` | `float64` | Unit selling price. Must be > 0.0. |
| `on_promotion` | `bool` | Flag indicating active discount/promotion. |

### B. Store Metadata (`stores_df`)
| Column | Data Type | Constraints / Description |
| :--- | :--- | :--- |
| `store_id` | `str` | Unique store identifier. Primary key. |
| `store_name` | `str` | Human-readable store name. |
| `location_type` | `str` | Enum: `urban_flagship`, `suburban_medium`, `rural_kiosk`. |
| `population_class` | `str` | Enum: `high_density`, `medium_density`, `low_density`. |
| `region_id` | `str` | Regional adapter key (e.g., `south_asia`, `ecuador`). |

### C. Item Master (`items_df`)
| Column | Data Type | Constraints / Description |
| :--- | :--- | :--- |
| `item_id` | `str` | Unique product identifier. Primary key. |
| `category_id` | `str` | Category classification. |
| `cost_price` | `float64` | Wholesale acquisition cost. Must be > 0.0. |
| `selling_price` | `float64` | Baseline retail list price. Must be > 0.0. |

### D. Canonical Context (`context_df` - Long Format)
| Column | Data Type | Constraints / Description |
| :--- | :--- | :--- |
| `date` | `datetime64[ns]` | Observation date. |
| `store_id` | `str` | Store ID or `'GLOBAL'` for regional signals. |
| `feature_name` | `str` | Feature indicator key (e.g., `is_payday`, `temperature_c`). |
| `value` | `float64` | Numerical feature value. |
| `source` | `str` | System/adapter origin (e.g., `south_asia_adapter`, `default_fallback`). |
| `is_fallback` | `bool` | `True` if feature was filled using baseline default due to missing data. |

---

## 2. API Helper Signatures

```python
def pivot_context(context_df: pd.DataFrame) -> pd.DataFrame:
    """Converts long-format context_df into wide-format indexed by (date, store_id)."""