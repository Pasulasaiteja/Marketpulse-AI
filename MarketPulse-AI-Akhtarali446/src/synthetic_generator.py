"""
src/synthetic_generator.py
Advanced synthetic generator with macro-trends, weather, school terms, 
and supplier catalog metadata.
"""

from typing import Dict, Tuple
import numpy as np
import pandas as pd
from pathlib import Path
import yaml

# pyrefly: ignore [missing-import]
from src.canonical_schemas import validate_dataframe

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def _resolve_config_path(config_path: str | Path) -> Path:
    p = Path(config_path)
    if p.exists():
        return p
    alt = _PACKAGE_ROOT / p
    if alt.exists():
        return alt
    return p


def load_config(config_path: str | Path = "config/synthetic_config.yaml") -> Dict:
    path = _resolve_config_path(config_path)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def generate_synthetic_data(
    config_path: str | Path = "config/synthetic_config.yaml"
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    cfg = load_config(config_path)

    seed = cfg["seed"]
    np.random.seed(seed)

    store_ids = [f"STORE_{i+1:03d}" for i in range(cfg["num_stores"])]
    item_ids = [f"ITEM_{i+1:03d}" for i in range(cfg["num_items"])]

    stores_df = pd.DataFrame([
        {
            "store_id": s_id,
            "store_name": f"Store {s_id}",
            "location_type": np.random.choice(["urban_flagship", "suburban_medium", "rural_kiosk"]),
            "population_class": np.random.choice(["high_density", "medium_density", "low_density"]),
            "region_id": "south_asia" if i % 2 == 0 else "ecuador",
        }
        for i, s_id in enumerate(store_ids)
    ])

    suppliers = cfg.get("suppliers", [{"id": "SUPPLIER_A", "lead_time_days": 3}])
    
    items_df = pd.DataFrame([
        {
            "item_id": i_id,
            "category_id": f"CAT_{ (i % 4) + 1 }",
            "cost_price": float(np.round(np.random.uniform(20.0, 100.0), 2)),
            "selling_price": float(np.round(np.random.uniform(110.0, 250.0), 2)),
            "supplier_id": suppliers[i % len(suppliers)]["id"],
            "lead_time_days": suppliers[i % len(suppliers)]["lead_time_days"],
        }
        for i, i_id in enumerate(item_ids)
    ])

    dates = pd.date_range(start=cfg["start_date"], end=cfg["end_date"], freq="D")
    mults = cfg["multipliers"]
    probs = cfg["probabilities"]
    weather_cfg = cfg.get("weather", {})

    sales_list = []
    context_list = []

    total_days = len(dates)

    for idx, d in enumerate(dates):
        # Time Signals
        is_payday = 1.0 if d.day in [1, 15] else 0.0
        is_market_day = 1.0 if d.dayofweek == 4 else 0.0
        is_festival = 1.0 if (d.month == 3 and d.day in [10, 11, 12]) or (d.month == 11 and d.day in [1, 2]) else 0.0
        is_school_term = 1.0 if (d.month in [1, 8] and d.day <= 14) else 0.0

        # Simulated Weather Features
        temp_c = float(np.round(weather_cfg.get("base_temp_c", 28.0) + np.sin(2 * np.pi * idx / 365.0) * 8.0 + np.random.normal(0, 2), 1))
        is_rain = 1.0 if np.random.rand() < weather_cfg.get("rain_probability", 0.15) else 0.0

        # Macro growth drift over time
        macro_drift = 1.0 + (idx / total_days) * 0.15  # 15% annual demand growth trend

        for s_id in store_ids:
            context_list.extend([
                {"date": d, "store_id": s_id, "feature_name": "is_payday", "value": is_payday, "source": "synthetic_generator", "is_fallback": False},
                {"date": d, "store_id": s_id, "feature_name": "is_market_day", "value": is_market_day, "source": "synthetic_generator", "is_fallback": False},
                {"date": d, "store_id": s_id, "feature_name": "is_festival", "value": is_festival, "source": "synthetic_generator", "is_fallback": False},
                {"date": d, "store_id": s_id, "feature_name": "is_school_term", "value": is_school_term, "source": "synthetic_generator", "is_fallback": False},
                {"date": d, "store_id": s_id, "feature_name": "temperature_c", "value": temp_c, "source": "synthetic_generator", "is_fallback": False},
                {"date": d, "store_id": s_id, "feature_name": "is_rain", "value": is_rain, "source": "synthetic_generator", "is_fallback": False},
            ])

            for i_id in item_ids:
                if np.random.rand() < probs["sparsity_rate"]:
                    continue

                base_demand = np.random.poisson(lam=18.0)

                multiplier = macro_drift
                if is_payday: multiplier *= mults["payday_boost"]
                if is_market_day: multiplier *= mults["market_day_boost"]
                if is_festival: multiplier *= mults["festival_boost"]
                if is_school_term: multiplier *= mults["school_term_boost"]
                if is_rain: multiplier *= weather_cfg.get("rain_demand_penalty", 0.85)

                on_promo = np.random.rand() < probs["promotion_rate"]
                if on_promo: multiplier *= mults["promotion_boost"]

                latent_demand = base_demand * multiplier

                is_stockout = np.random.rand() < probs["stockout_rate"]
                observed_sales = 0.0 if is_stockout else float(np.round(latent_demand))

                item_price = items_df.loc[items_df["item_id"] == i_id, "selling_price"].values[0]

                sales_list.append({
                    "date": d,
                    "store_id": s_id,
                    "item_id": i_id,
                    "sales_quantity": float(observed_sales),
                    "price": float(item_price),
                    "on_promotion": bool(on_promo),
                })

    sales_df = validate_dataframe(pd.DataFrame(sales_list), "sales")
    stores_df = validate_dataframe(stores_df, "stores")
    items_df = validate_dataframe(items_df, "items")
    context_df = validate_dataframe(pd.DataFrame(context_list), "context")

    return sales_df, stores_df, items_df, context_df