# Model card: PSA50 response from baseline PSMA-PET and PSA

**Intended use.** Research only: to study whether baseline PSMA expression and tumour burden predict PSA50 response to [177Lu]Lu-PSMA therapy. Not for treatment decisions.

**Data.** 117 patients with a usable baseline scan and two PSA values from the documents, 32 responders, 4 sites. Simulated cohort (see README, Limits).

**Model.** Logistic regression on standardised features, fixed in the analysis plan before validation: suv_mean, log_tv, liver_involved, log_psa.

**Validation.** Leave-one-site-out. AUC 0.618 (95% CI 0.494-0.743, DeLong); calibration slope 0.48; Brier 0.189. Gradient boosting as a secondary analysis: AUC 0.533. The same cohort's true response probabilities reach AUC 0.813: the ceiling for this data.

**Explanation (mean |SHAP| on the standardised scale).**

| Feature | Mean abs SHAP | Coefficient |
|---|---:|---:|
| suv_mean | 0.641 | +0.864 |
| log_tv | 0.485 | -0.601 |
| log_psa | 0.403 | -0.514 |
| liver_involved | 0.226 | -0.476 |

**Limits.** Synthetic patients; 5 features; no external validation; sites differ in tracer and protocol only as simulated.
