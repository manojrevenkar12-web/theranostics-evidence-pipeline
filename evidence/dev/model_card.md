# Model card: PSA50 response from baseline PSMA-PET and PSA

**Intended use.** Research only: to study whether baseline PSMA expression and tumour burden predict PSA50 response to [177Lu]Lu-PSMA therapy. Not for treatment decisions.

**Data.** 119 patients with a usable baseline scan and two PSA values from the documents, 48 responders, 6 sites. Simulated cohort (see README, Limits).

**Model.** Logistic regression on standardised features, fixed in the analysis plan before validation: suv_mean, log_tv, liver_involved, log_psa.

**Validation.** Leave-one-site-out. AUC 0.710 (95% CI 0.614-0.806, DeLong); calibration slope 0.83; Brier 0.205. Gradient boosting as a secondary analysis: AUC 0.696. The same cohort's true response probabilities reach AUC 0.836: the ceiling for this data.

**Explanation (mean |SHAP| on the standardised scale).**

| Feature | Mean abs SHAP | Coefficient |
|---|---:|---:|
| suv_mean | 1.083 | +1.533 |
| log_tv | 0.422 | -0.535 |
| liver_involved | 0.272 | -0.543 |
| log_psa | 0.002 | -0.003 |

**Limits.** Synthetic patients; 5 features; no external validation; sites differ in tracer and protocol only as simulated.
