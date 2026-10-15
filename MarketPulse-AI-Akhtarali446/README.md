# MarketPulse AI --- Data and Context Layer

The **Data and Context Layer** prepares retail sales, product, store,
and contextual data for the MarketPulse AI forecasting and
inventory-optimization pipeline. It provides dataset adapters, schema
validation, preprocessing, stockout handling, calendar/context features,
and cold-start priors.

## Contents

-   [Overview](#overview)
-   [Architecture](#architecture)
-   [Repository Structure](#repository-structure)
-   [Requirements](#requirements)
-   [Setup](#setup)
-   [Loading a Dataset](#loading-a-dataset)
-   [Data and Feature Pipeline](#data-and-feature-pipeline)
-   [Data Quality and Testing](#data-quality-and-testing)
-   [Data Files and Git](#data-files-and-git)
-   [Data Files and Git](#data-files-and-git)
-   [How to Add a New Region](#How-to-Add-a-New-Region)
-   [Integration Notes](#Integration-Notes)
-   [Troubleshooting](#troubleshooting)

## Overview

This component is intended to provide downstream forecasting,
optimization, and evaluation modules with consistent retail data.

Key responsibilities include:
- Loading supported datasets through a unified `load_dataset()` loader.
- Producing and validating canonical `sales`, `stores`, `items`, and `context` tables.
- Generating synthetic retail data with configurable market effects (paydays, festivals, weather, school terms).
- Supporting public-dataset adapters (Favorita and M5).
- Handling stockout censoring so zero sales during out-of-stock days are not misread as zero demand.
- Extracting cyclical calendar maps, price elasticity signals, EWMA, and non-leaking rolling statistics.
- Generating cold-start store demand priors using `scikit-learn` KMeans clustering.
- Enforcing strict chronological time-series splitting to eliminate data leakage.

## Architecture

``` text
Raw or generated data
        |
        v
Dataset adapter / synthetic generator
        |
        v
Schema validation and data-quality checks
        |
        v
Cleaning, stockout handling, and context features
        |
        v
Processed tables and feature matrix
        |
        v
Forecasting, inventory optimization, and evaluation
```

## Repository Structure

``` text
data_and_context_layer/
├── config/
│   └── synthetic_config.yaml         # Synthetic demand parameters
├── data/
│   ├── raw/                          # Lightweight source CSV fixtures (.gitkeep tracked)
│   └── processed/                    # Generated ML feature matrix (ignored by Git)
├── src/
│   ├── __init__.py                   # Package exports
│   ├── canonical_schemas.py          # Pydantic & Pandas schema validators
│   ├── synthetic_generator.py        # Reproducible synthetic demand generator
│   ├── pipeline.py                   # Feature pipeline (Lags, EWMA, Calendar, Elasticity)
│   ├── context_layer.py              # Context engine with audit logs and fallbacks
│   ├── regional_adapters/            # Regional calendar & currency plug-ins
│   ├── cold_start.py                 # Scikit-learn KMeans store demographic clustering
│   ├── public_dataset_adapters.py    # M5 and Favorita benchmark adapters
│   └── loader.py                     # Unified dataset loading entrypoint
├── tests/                            # Automated pytest test suite
├── CONTRACT.md                       # Canonical data contract specifications
├── DATA_QUALITY_REPORT.md            # Data governance & quality audit
├── README.md                         # Project documentation & integration guide
├── requirements.txt                  # Pinned Python dependencies
├── export_processed.py              # Exports local feature matrix to data/processed/
└── verify_high_class.py              # Feature matrix execution check script


## Requirements

-   Python 3.10 or newer is recommended; use the version tested by your
    team.
-   Git
-   Python packages listed in `requirements.txt`

## Setup

### 1. Clone the repository

``` bash
git clone [https://github.com/Akhtarali446/MarketPulse-AI.git](https://github.com/Akhtarali446/MarketPulse-AI.git)
cd data_and_context_layer
```

### 2. Create and activate a virtual environment

**Windows PowerShell:**

``` powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**Git Bash:**

``` bash
python -m venv venv
source venv/Scripts/activate
```

### 3. Install dependencies

``` bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Loading a Dataset

The central entry point is load_dataset() in src/loader.py.

It returns four canonical DataFrames: (sales_df, stores_df, items_df, context_df).

Supported dataset names:
synthetic: Reproducible full synthetic retail dataset
synthetic_sparse: Synthetic sales with randomly omitted records
m5: Subsampled M5 benchmark adapter
favorita: Subsampled Favorita benchmark adapter

Check `src/loader.py` for the exact names, adapter requirements, and
current function signature before running a dataset. The implementation
may require local source data for public datasets.

Example pattern:

``` python
from src.loader import load_dataset

sales_df, stores_df, items_df, context_df = load_dataset("synthetic")

print(f"Sales Shape: {sales_df.shape}")
print(f"Stores Shape: {stores_df.shape}")
print(f"Items Shape: {items_df.shape}")
print(f"Context Shape: {context_df.shape}")
```

Inspect the implementation to determine the returned tables and their
order. The current local implementation may return **four**
DataFrames---sales, stores, items, and context---so do not assume a
three-table return signature unless the team contract and implementation
have been aligned.

## Data and Feature Pipeline

To build the complete 35-feature ML matrix for training forecasters:

``` python
import pandas as pd
from src.loader import load_dataset
from src.canonical_schemas import pivot_context
from src.pipeline import (
    reindex_continuous_dates,
    flag_stockouts,
    cap_outliers_iqr,
    add_cyclical_calendar_features,
    add_price_features,
    add_lag_and_rolling_features,
)

# 1. Load source tables
sales_df, stores_df, items_df, context_df = load_dataset("synthetic")

# 2. Reindex dates & compute features
clean_sales = reindex_continuous_dates(sales_df)
stockout_sales = flag_stockouts(clean_sales)
capped_sales = cap_outliers_iqr(stockout_sales)
calendar_sales = add_cyclical_calendar_features(capped_sales)
price_sales = add_price_features(calendar_sales)
sales_features = add_lag_and_rolling_features(price_sales)

# 3. Pivot context & merge
wide_context_df = pivot_context(context_df)
full_ml_matrix = pd.merge(sales_features, wide_context_df, on=["date", "store_id"], how="left")

print(f"Final ML Feature Matrix Shape: {full_ml_matrix.shape}")
```

## Exporting Local CSV Deliverables

Run the export script to build and save all tables locally in data/processed/:

``` python
python export_processed.py
```
This generates:

data/processed/full_ml_feature_matrix.csv (73,000 rows x 35 columns)

data/processed/cold_start_priors.csv (Demographic store prior demand profiles)

data/processed/stores_metadata.csv (Store demographic metadata)

data/processed/items_catalog.csv (Product pricing and supplier lead times)


### Stockout handling

A recorded sale of zero does not necessarily mean demand was zero if the
product was unavailable. Stock availability should be considered when
interpreting sales and constructing demand-related features.

### Context features

Context may include calendar indicators such as weekdays, weekends,
paydays, market days, school terms, or local events, depending on the
adapter and available source data. When context data is unavailable,
fallback behavior should be explicitly flagged rather than silently
treated as observed data.

### Cold-start support

Cold-start priors can provide initial estimates for products or stores
with little or no historical sales. These estimates should be derived
only from information available at the forecast cutoff.

### Time-series safety

Feature generation and train/validation/test splitting should respect
time order. Rolling statistics, lags, and other predictive features must
not use future information.

Refer to `CONTRACT.md` for the agreed data contract and
`DATA_QUALITY_REPORT.md` for documented quality checks and known
limitations.

## Data Quality and Testing

The `tests/` directory contains tests for areas such as:

-   Canonical schemas
-   Reproducibility of synthetic data
-   Synthetic ground-truth behavior
-   Time leakage
-   Stockout handling
-   Regional adapters and fallback behavior
-   Cold-start priors

Run the test suite from the repository root:

``` bash
python -m pytest -q
```

If pytest is not installed in your environment:

``` bash
python -m pip install pytest
python -m pytest -q
```

Use the test results as the source of truth for what currently passes;
this README does not claim that every test has already passed in every
environment.

## Data Files and Git

The repository may contain raw CSV inputs and processed outputs such as:

-   `data/raw/sales.csv`
-   `data/raw/stores.csv`
-   `data/raw/items.csv`
-   `data/raw/context.csv`
-   `data/processed/full_ml_feature_matrix.csv`
-   `data/processed/cold_start_priors.csv`
-   `data/processed/items_catalog.csv`
-   `data/processed/stores_metadata.csv`

Before committing datasets, check:

1.  **Size:** GitHub blocks individual files larger than 100 MiB in
    ordinary Git pushes. Large files may need Git LFS or external
    storage.
2.  **Licensing:** Verify that any public dataset can be redistributed
    under its license.
3.  **Privacy:** Do not commit personal, confidential, or restricted
    data.
4.  **Reproducibility:** Document how generated outputs can be
    recreated, including relevant configuration and random seeds.
5.  **Repository scope:** Decide with the team whether processed CSVs
    should be versioned or generated locally. Avoid committing duplicate
    or unnecessary outputs.

To review what Git will commit:

``` bash
git status
git diff --cached --stat
```

To commit selected files:

``` bash
git add README.md CONTRACT.md DATA_QUALITY_REPORT.md
git commit -m "docs: add project documentation"
git push origin main
```

Adjust the branch name if your repository uses a different default
branch.

## How to Add a New Region

The Context Layer uses a pluggable adapter pattern. To support a new region (e.g., East Africa):

Step 1: Create a New Regional Adapter File
Create src/regional_adapters/east_africa.py and inherit from BaseRegionalAdapter:

``` python
"""
src/regional_adapters/east_africa.py
Regional context adapter for East Africa (Kenya/Tanzania).
"""

from typing import List
import pandas as pd
from src.regional_adapters.base import BaseRegionalAdapter


class EastAfricaAdapter(BaseRegionalAdapter):
    def __init__(self):
        super().__init__(region_id="east_africa", currency="KES")

    def get_context_features(self, dates: pd.DatetimeIndex, store_ids: List[str]) -> pd.DataFrame:
        records = []
        for d in dates:
            # Regional context logic (paydays, public holidays, market days)
            is_payday = 1.0 if d.day in [28, 29, 30, 31] else 0.0
            is_market_day = 1.0 if d.dayofweek == 2 else 0.0  # Wednesday market
            
            for s_id in store_ids:
                records.extend([
                    {"date": d, "store_id": s_id, "feature_name": "is_payday", "value": is_payday, "source": self.region_id, "is_fallback": False},
                    {"date": d, "store_id": s_id, "feature_name": "is_market_day", "value": is_market_day, "source": self.region_id, "is_fallback": False},
                ])
        return pd.DataFrame(records)
```
Step 2: Export in src/regional_adapters/__init__.py
Add the new adapter to the module exports:

``` python
from .base import BaseRegionalAdapter
from .south_asia import SouthAsiaAdapter
from .ecuador_stub import EcuadorAdapterStub
from .east_africa import EastAfricaAdapter

__all__ = ["BaseRegionalAdapter", "SouthAsiaAdapter", "EcuadorAdapterStub", "EastAfricaAdapter"]
```
Step 3: Register in ContextEngine (src/context_layer.py)
Add the adapter to ContextEngine.__init__():

``` python
from src.regional_adapters import SouthAsiaAdapter, EcuadorAdapterStub, EastAfricaAdapter

class ContextEngine:
    def __init__(self):
        self.adapters = {
            "south_asia": SouthAsiaAdapter(),
            "ecuador": EcuadorAdapterStub(),
            "east_africa": EastAfricaAdapter(),  # Registered new region
        }
```

## Integration Notes

Before connecting this component to forecasting, optimization, or
evaluation modules, agree on:

-   The exact `load_dataset(name)` signature and return order.
-   Canonical names, data types, and nullability of columns.
-   The forecast target column (for example, `units_sold` if that is the
    approved team contract).
-   The meaning of unknown stock and missing context.
-   The handling of duplicate store--item--date records.
-   Which features are safe at prediction time.
-   How cold-start priors and fallback context are represented.

The contract and implementation should agree. If the team contract
specifies three tables but the loader returns four, resolve that
mismatch before integration rather than silently dropping a table.

## Troubleshooting

### `ModuleNotFoundError`

Run commands from the repository root and ensure the virtual environment
is active. Confirm dependencies are installed and that the project
package/import structure matches the command being run.

### Dataset adapter cannot find source data

Check the adapter documentation and expected source-data location.
Public datasets may require separate download, extraction, or
configuration steps.

### Tests fail

Run the failing test alone for a clearer error:

``` bash
python -m pytest tests/test_schemas.py -q
```

Replace the test path with the failing test. Do not mark a test as
passed until it has been run successfully.

### Processed files do not appear on GitHub

Check `git status` and `git diff --cached --stat`, commit the intended
files, and push the branch. Also check `.gitignore` rules and the size
of each file.

## Contributing

1.  Keep schema and contract changes documented in CONTRACT.md.
2.  Add or update unit tests in tests/ whenever feature engineering logic changes.
3.  Prevent future-data leakage in all rolling and lag statistics.
4.  Update DATA_QUALITY_REPORT.md when data generation or cleaning rules change.

------------------------------------------------------------------------
