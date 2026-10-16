"""
tests/test_reproducibility.py
Verifies that the synthetic generator produces bit-for-bit identical outputs given the same seed.
"""

import pandas as pd
from src.synthetic_generator import generate_synthetic_data


def test_reproducibility_identical_runs():
    sales_1, stores_1, items_1, context_1 = generate_synthetic_data("config/synthetic_config.yaml")
    sales_2, stores_2, items_2, context_2 = generate_synthetic_data("config/synthetic_config.yaml")

    pd.testing.assert_frame_equal(sales_1, sales_2)
    pd.testing.assert_frame_equal(stores_1, stores_2)
    pd.testing.assert_frame_equal(items_1, items_2)
    pd.testing.assert_frame_equal(context_1, context_2)