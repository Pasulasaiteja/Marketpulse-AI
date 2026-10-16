# Component A: Market Signal Intelligence

**Module:** MarketPulse AI — Member 2  
**Role:** Identifies statistical shifts in sales velocity and extracts customer intent from unstructured reviews.

---

## 1. Capabilities

1. **Statistical Change-Point Detection (`change_point.py`):**
   - Implements two-sided CUSUM (Cumulative Sum Control Chart) on rolling standardized velocity residuals ($z$-scores).
   - Flags persistent structural shifts (`CHANGE_POINT_SPIKE` and `CHANGE_POINT_DROP`) rather than transitory noise.
   - Outputs quantitative evidence (percentage shift vs baseline, CUSUM score, $z$-score).

2. **NLP Customer Feedback Classifier (`nlp_classifier.py`):**
   - Classifies customer text into actionable categories:
     - `CUSTOMER_NEED`: Missing stock, requests for specific pack sizes, dietary options.
     - `CUSTOMER_COMPLAINT`: Repeated stockouts, spoiled goods, price gouging.
     - `EMERGING_PREFERENCE`: Local trends, health foods, student/gym consumer preferences.
   - Generates confidence scores and excerpt evidence.

3. **Output Contract Schema:**
   Conforms 100% to `CONTRACT.md`:
   - `signal_id`: Unique identifier (e.g. `SIG_20261014_0001`)
   - `product_or_category`: Product ID or category tag
   - `type`: Signal classification
   - `evidence`: Detailed string explanation
   - `confidence`: Confidence score in $[0.0, 1.0]$
   - `date`: YYYY-MM-DD

---

## 2. Shared Gating Rule

Per `ASSUMPTIONS.md` and the core philosophy:
> *Online attention does not necessarily mean local sales. Signals influence demand estimates only once their predictive value has been established in the feature ablation study.*

If a signal does not improve held-out forecast accuracy, its ablation weight remains 0. A null result is recorded as a valid finding.
