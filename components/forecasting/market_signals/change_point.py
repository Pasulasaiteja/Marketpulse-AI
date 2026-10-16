"""
Statistical Change-Point & Pattern Shift Detector for Retail Sales.
Uses two-sided CUSUM (Cumulative Sum Control Chart) and rolling velocity z-score
to identify structural shifts in demand.
"""

import numpy as np
import pandas as pd
from typing import Any


class ChangePointDetector:
    """
    Statistical Change-Point Detector using CUSUM and rolling z-scores.
    Detects persistent upward and downward structural breaks in product sales velocity.
    """
    def __init__(
        self,
        baseline_window: int = 14,
        drift_allowance: float = 0.5,
        decision_threshold: float = 4.0
    ):
        self.baseline_window = baseline_window
        self.drift_allowance = drift_allowance
        self.decision_threshold = decision_threshold

    def detect_shifts(
        self,
        df_sales: pd.DataFrame,
        store_id: str | None = None,
        product_id: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Scans sales time series for statistically significant change points.
        
        Returns:
        --------
        list of signal dicts:
            product_or_category, type, evidence, confidence, date
        """
        df = df_sales.copy()
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values(["store_id", "product_id", "date"]).reset_index(drop=True)
        
        if store_id:
            df = df[df["store_id"] == store_id]
        if product_id:
            df = df[df["product_id"] == product_id]
            
        signals = []
        
        for (st, pid), group in df.groupby(["store_id", "product_id"]):
            y = group["units_sold"].values
            dates = group["date"].dt.strftime("%Y-%m-%d").values
            n = len(y)
            
            w = self.baseline_window
            if n < w + 7:
                continue
                
            # Running CUSUM algorithm
            s_pos = 0.0
            s_neg = 0.0
            k = self.drift_allowance
            h = self.decision_threshold
            
            for t in range(w, n):
                # Baseline mean and standard deviation from previous w days
                base_window = y[t - w:t]
                mu_0 = np.mean(base_window)
                sigma_0 = np.std(base_window)
                if sigma_0 < 1e-4:
                    sigma_0 = max(1.0, 0.2 * mu_0) if mu_0 > 0 else 1.0
                    
                val_t = y[t]
                z_t = (val_t - mu_0) / sigma_0
                
                s_pos = max(0.0, s_pos + z_t - k)
                s_neg = max(0.0, s_neg - z_t - k)
                
                dt_str = dates[t]
                
                # Check upward change point
                if s_pos >= h:
                    pct_shift = ((val_t - mu_0) / max(1.0, mu_0)) * 100.0
                    conf = min(0.98, float(0.50 + 0.08 * (s_pos - h + 1.0)))
                    signals.append({
                        "product_or_category": pid,
                        "type": "CHANGE_POINT_SPIKE",
                        "evidence": f"Upward sales velocity shift detected: +{pct_shift:.1f}% vs {w}d baseline (CUSUM score={s_pos:.2f}, z={z_t:.2f})",
                        "confidence": round(conf, 2),
                        "date": dt_str
                    })
                    s_pos = 0.0 # Reset accumulator after signal firing
                    
                # Check downward change point
                elif s_neg >= h:
                    pct_drop = ((mu_0 - val_t) / max(1.0, mu_0)) * 100.0
                    conf = min(0.98, float(0.50 + 0.08 * (s_neg - h + 1.0)))
                    signals.append({
                        "product_or_category": pid,
                        "type": "CHANGE_POINT_DROP",
                        "evidence": f"Downward sales collapse detected: -{pct_drop:.1f}% vs {w}d baseline (CUSUM score={s_neg:.2f}, z={z_t:.2f})",
                        "confidence": round(conf, 2),
                        "date": dt_str
                    })
                    s_neg = 0.0 # Reset accumulator
                    
        return signals
