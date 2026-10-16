"""
Generate calibration and interval visualization plots for reports.

PLOTS GENERATED:
  reports/calibration_plot.png — Two-panel figure:
    LEFT:  14-day demand fan-chart (daily forecast bands with historical actuals
           showing real highs and lows — weekends, paydays, shocks).
    RIGHT: Empirical coverage verification — fraction of actuals inside [p10, p90]
           per quantile level, compared to the perfect diagonal.

WHY A FAN CHART?
  The previous CDF plot was mathematically correct (a CDF must be monotonically
  non-decreasing) but gave no visual sense of day-to-day variation.
  Real retail demand has clear highs (weekends, payday, promotions) and lows
  (weekdays, post-shock disruption). A fan chart communicates BOTH:
    1. The best-estimate daily trajectory with its natural ups/downs.
    2. The uncertainty around each day's prediction.
"""

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd

from mock_data.generator import generate_synthetic_data
from forecasting.gb_quantile import GradientBoostedQuantileForecaster, FeatureBuilder
from forecasting.calibration import ConformalCalibrator


# ── colour palette ──────────────────────────────────────────────────────────
C_HIST    = "#64748b"   # historical actual
C_MEDIAN  = "#2563eb"   # forecast median (p50)
C_BAND50  = "#3b82f6"   # p25–p75 band
C_BAND80  = "#93c5fd"   # p10–p90 band
C_ACTUAL  = "#f97316"   # actuals overlaid in forecast window
C_SHOCK   = "#fca5a5"   # shock period tint


def make_plots() -> None:
    os.makedirs("reports", exist_ok=True)

    # ── 1. Load data and train model ─────────────────────────────────────────
    data       = generate_synthetic_data(seed=42)
    df_sales   = data["sales"]
    df_context = data["context"]

    store   = "STORE_001"
    product = "PROD_MILK_1L"
    HORIZON = 14   # days to forecast
    HIST_W  = 30   # days of history to show

    prod_sales = (
        df_sales[(df_sales["store_id"] == store) & (df_sales["product_id"] == product)]
        .sort_values("date")
        .reset_index(drop=True)
    )
    prod_sales["date"] = pd.to_datetime(prod_sales["date"])

    # Temporal split: train on all but last HORIZON days; "test" is the last window
    cutoff    = prod_sales["date"].max() - pd.Timedelta(days=HORIZON)
    train_df  = prod_sales[prod_sales["date"] <= cutoff].copy()
    test_df   = prod_sales[prod_sales["date"] >  cutoff].copy()
    ctx_train = df_context[pd.to_datetime(df_context["date"]) <= cutoff].copy()

    # Full quantile grid for fan chart: 5 % steps
    ALL_Q = [0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95]

    model = GradientBoostedQuantileForecaster(
        quantiles=ALL_Q,
        n_estimators=80,
        learning_rate=0.05,
        feature_builder=FeatureBuilder(include_calendar=True, include_economic=True),
        seed=42,
    )
    model.fit(train_df, ctx_train)

    preds = model.predict_product_horizon(
        store_id=store,
        product_id=product,
        horizon_days=HORIZON,
        quantiles=ALL_Q,
    )  # dict: {q: np.ndarray shape (HORIZON,)}

    # Build forecast date index
    forecast_dates = pd.date_range(
        start=cutoff + pd.Timedelta(days=1),
        periods=HORIZON,
        freq="D",
    )

    # Historical window
    hist = train_df.tail(HIST_W).copy()

    # Conformal calibration on validation stub
    calib = ConformalCalibrator(target_coverage=0.80)
    y_val_arr = hist["units_sold"].values
    mu_v, sd_v = np.mean(y_val_arr), np.std(y_val_arr) + 1e-6
    calib.calibrate(y_val_arr, mu_v - 1.28 * sd_v, mu_v + 1.28 * sd_v)
    preds = calib.adjust_intervals(preds)

    # ── 2. Coverage verification (right panel) ───────────────────────────────
    actuals = test_df["units_sold"].values
    n_act   = len(actuals)
    aligned_len = min(n_act, HORIZON)
    actuals_aligned = actuals[:aligned_len]

    tau_levels   = [0.05, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 0.95]
    empirical_cov = []
    for tau in tau_levels:
        # symmetrical: upper quantile = (1 - lower), centred on p50
        lower_q = (1.0 - tau) / 2.0
        upper_q = 1.0 - lower_q
        # find closest available quantile
        avail = sorted(preds.keys())
        lo_q  = min(avail, key=lambda q: abs(q - lower_q))
        hi_q  = min(avail, key=lambda q: abs(q - upper_q))
        lo    = preds[lo_q][:aligned_len]
        hi    = preds[hi_q][:aligned_len]
        if len(actuals_aligned) > 0 and len(lo) > 0:
            cov = float(np.mean((actuals_aligned >= lo) & (actuals_aligned <= hi)))
        else:
            cov = tau  # fallback to nominal
        empirical_cov.append(cov)

    # ── 3. Build the figure ──────────────────────────────────────────────────
    fig, (ax_fan, ax_cov) = plt.subplots(
        1, 2,
        figsize=(14, 5.5),
        gridspec_kw={"width_ratios": [2, 1]},
    )

    # ── LEFT: Fan chart ──────────────────────────────────────────────────────
    hist_dates = hist["date"].values
    hist_vals  = hist["units_sold"].values

    # Shade any shock period in the historical window
    shock_df = df_context[df_context["shock_flag"] == 1].copy()
    shock_df["date"] = pd.to_datetime(shock_df["date"])
    for dt in shock_df["date"]:
        if hist["date"].min() <= dt <= hist["date"].max():
            ax_fan.axvspan(dt - pd.Timedelta(hours=12), dt + pd.Timedelta(hours=12),
                           color=C_SHOCK, alpha=0.35, zorder=0)

    # Historical actual demand — with visible daily variation
    ax_fan.plot(hist_dates, hist_vals,
                color=C_HIST, linewidth=1.3, alpha=0.85, zorder=2,
                label="Historical actuals (daily)")

    # Divider between history and forecast
    ax_fan.axvline(cutoff, color="#94a3b8", linestyle="--", linewidth=1.2, zorder=3)
    ax_fan.text(cutoff + pd.Timedelta(hours=6), ax_fan.get_ylim()[1] if ax_fan.get_ylim()[1] != 1.0 else max(hist_vals) * 1.1,
                "▶ Forecast", fontsize=8, color="#475569", va="top")

    # Forecast p05-p95 outer band (widest)
    ax_fan.fill_between(
        forecast_dates,
        preds[0.05], preds[0.95],
        color=C_BAND80, alpha=0.30, zorder=1,
        label="p05-p95 band",
    )
    # Forecast p10-p90 band
    ax_fan.fill_between(
        forecast_dates,
        preds[0.10], preds[0.90],
        color=C_BAND50, alpha=0.40, zorder=2,
        label="p10-p90 band (80% CI)",
    )
    # Forecast p25-p75 inner band (most confident)
    ax_fan.fill_between(
        forecast_dates,
        preds[0.25], preds[0.75],
        color=C_MEDIAN, alpha=0.30, zorder=3,
        label="p25-p75 band (50% CI)",
    )
    # Median forecast line — shows natural daily ups/downs
    ax_fan.plot(
        forecast_dates, preds[0.50],
        color=C_MEDIAN, linewidth=2.2, zorder=4,
        label="Median forecast (p50)",
    )
    # Overlay actuals in the forecast window (if any)
    if aligned_len > 0:
        ax_fan.plot(
            forecast_dates[:aligned_len],
            actuals_aligned,
            color=C_ACTUAL, linewidth=1.8, linestyle="--",
            marker="o", markersize=4, zorder=5,
            label="Actual demand (held-out)",
        )

    ax_fan.set_title(
        f"Demand Forecast Fan Chart - {product} @ {store}",
        fontsize=11, fontweight="bold", pad=10,
    )
    ax_fan.set_xlabel("Date", fontsize=9)
    ax_fan.set_ylabel("Units Sold (daily)", fontsize=9)
    ax_fan.tick_params(axis="x", rotation=30, labelsize=8)
    ax_fan.grid(True, linestyle=":", alpha=0.55)
    ax_fan.set_facecolor("#f8fafc")

    # Shock annotation & Legend combining all handles + labels
    shock_patch = mpatches.Patch(color=C_SHOCK, alpha=0.5, label="Active shock period")
    fan_handles, fan_labels = ax_fan.get_legend_handles_labels()
    fan_handles.append(shock_patch)
    fan_labels.append("Active shock period")
    ax_fan.legend(
        handles=fan_handles,
        labels=fan_labels,
        fontsize=7.5, loc="upper left", framealpha=0.9,
    )

    # ── RIGHT: Coverage verification ─────────────────────────────────────────
    nom_cov = tau_levels  # perfect calibration diagonal
    ax_cov.plot([0, 1], [0, 1], "k--", linewidth=1.2, label="Perfect calibration")
    ax_cov.plot(nom_cov, empirical_cov,
                color="#2563eb", marker="o", markersize=5, linewidth=2.0,
                label="Empirical coverage")
    ax_cov.fill_between(nom_cov, nom_cov, empirical_cov,
                        color="#3b82f6", alpha=0.15)

    ax_cov.set_title("Interval Coverage Verification", fontsize=11, fontweight="bold", pad=10)
    ax_cov.set_xlabel("Nominal Coverage Level", fontsize=9)
    ax_cov.set_ylabel("Empirical Coverage", fontsize=9)
    ax_cov.legend(fontsize=8)
    ax_cov.set_xlim(0, 1); ax_cov.set_ylim(0, 1)
    ax_cov.grid(True, linestyle=":", alpha=0.55)
    ax_cov.set_facecolor("#f8fafc")
    ax_cov.set_aspect("equal")

    # ── 4. Save ───────────────────────────────────────────────────────────────
    plt.suptitle(
        "MarketPulse AI — Probabilistic Demand Forecast (Member 2)",
        fontsize=12, fontweight="bold", y=1.01,
    )
    plt.tight_layout()
    plt.savefig("reports/calibration_plot.png", dpi=200, bbox_inches="tight")
    plt.close()
    print("DONE: Calibration fan-chart saved -> reports/calibration_plot.png")


if __name__ == "__main__":
    make_plots()
