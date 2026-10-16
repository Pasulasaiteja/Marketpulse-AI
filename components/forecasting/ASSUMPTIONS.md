# Documented System Assumptions

**Module:** Member 2 — Demand Forecasting & Market Signals  
**Compliance Requirement:** Never silently pick constants, multipliers, or effect sizes; every parameter must be recorded with its rationale and testable assumption.

---

## 1. Shock Interval Widening Rule

### Rationale
During localized disruptions (transport strikes, violent protests, extreme weather, sudden supply curfews), future demand volatility spikes unpredictably. A standard forecast model trained on normal historical data would produce overconfident (narrow) prediction intervals, leading retailers to risk catastrophic stockouts or tied-up capital.

### Explicit Assumption
- **Shock Multiplier Formulation:**
  When `shock_flag == 1` (or active for the horizon period):
  $$\text{Interval Width}_{\text{shock}} = \text{Interval Width}_{\text{baseline}} \times \mathbf{\Omega}_{\text{shock}}$$
  Where $\mathbf{\Omega}_{\text{shock}} = 1.50$ (a 50% widening of the interquantile range $[p_{10}, p_{90}]$).
- **Quantile Transformation:**
  Let $p_{50}$ remain the point estimate of central tendency.
  $$p_{10}^{\text{shock}} = \max\left(0.0, p_{50} - \mathbf{\Omega}_{\text{shock}} \cdot (p_{50} - p_{10})\right)$$
  $$p_{90}^{\text{shock}} = p_{50} + \mathbf{\Omega}_{\text{shock}} \cdot (p_{90} - p_{50})$$
  Grid quantiles $q_{\tau}$ are similarly stretched around $p_{50}$.
- **Status:** Explicit Assumption (Hand-set default $\mathbf{\Omega}=1.50$, configurable in `config.yaml` / model registry). Tested in `tests/test_sparse_and_shocks.py`.

---

## 2. Sparse Products and Cold-Start Prior Pooling

### Rationale
A product with little or no sales history (< 14 days of data in a given store) cannot have its seasonal and autoregressive parameters reliably fit with GBDT without extreme overfitting.

### Explicit Assumption
- **Minimum History Threshold:** Products with fewer than 14 non-zero sales observations are classified as **Sparse / Cold-Start**.
- **Hierarchical Pooling Prior:**
  The baseline rate $\lambda_{\text{prior}}$ is computed from the store-category mean:
  $$\lambda_{\text{prior}} = \frac{1}{|P_{\text{cat}}|} \sum_{j \in P_{\text{cat}}} \bar{y}_j$$
  For a sparse product with $n$ observed days ($n < 14$) and sample mean $\bar{y}$, the blended rate is:
  $$\hat{\mu}_{\text{sparse}} = \alpha \bar{y} + (1 - \alpha) \lambda_{\text{prior}}, \quad \text{where } \alpha = \frac{n}{14}$$
- **Uncertainty Inflation for Sparse Items:**
  Because parameters are uncertain, the coefficient of variation for sparse items is assumed to be at least $CV_{\text{sparse}} = 0.60$ (producing wider, honest intervals $[p_{10}, p_{90}]$).

---

## 3. Conformal Prediction & Calibration Rule

### Rationale
Quantile regression models (such as LightGBM with quantile objective $\alpha \in \{0.1, 0.5, 0.9\}$) can suffer from quantile crossing or empirical undercoverage on non-stationary retail time series.

### Explicit Assumption
- We apply split-conformal calibration on a rolling validation holdout.
- The target 80% coverage interval is $[p_{10}, p_{90}]$.
- If empirical coverage on validation set $C_{\text{val}} = P(y \in [\hat{q}_{0.10}, \hat{q}_{0.90}]) < 0.75$, a conformal additive non-conformity score quantile $\hat{s}_{1-\alpha}$ is computed to widen bounds until empirical coverage reaches $80\% \pm 5\%$.
- Strictly positive lower bound constraint: $\text{Lower Bound} = \max(0.0, \hat{q}_{0.10} - \hat{s})$.

---

## 4. Market Signal Influence in Forecasts (Earning Its Place)

### Rationale
Online sentiment, foot-traffic reviews, or social media buzz often do not translate to cash-register sales in local neighborhood retail. Letting unverified signals directly adjust sales forecasts degrades accuracy.

### Explicit Assumption
- **Gating Rule:** A market signal (NLP classification or change point) enters the feature store **only if** it demonstrates a statistically significant out-of-sample error reduction (WAPE decrease $> 1.0\%$ or Pinball loss improvement) during the ablation study.
- **Null Result Policy:** If a signal shows zero or negative impact during validation, its weight in the final forecast model is clamped to 0. A null result is recorded and reported to the team as a valid, useful finding.

---

## 5. Non-Negative Demand & Integer Rounding for Quantiles

### Rationale
Retail units cannot be negative.
- Every quantile produced by any model is truncated at $0.0$:
  $$q_{\tau} = \max(0.0, q_{\tau})$$
- Quantile monotonicity is enforced via sorting:
  $$q_{\tau_1} \le q_{\tau_2} \quad \forall \tau_1 < \tau_2$$
