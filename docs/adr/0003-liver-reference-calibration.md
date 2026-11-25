# 3. Compare liver reference uptake across sites

**Decision.** For each site, the median SUV in an eroded liver region is compared with the median of all scans.
A deviation over 8% with at least 5 scans flags the site and triggers a query for the phantom cross-calibration
factor. Without an answer the site's scans are kept out of quantitative endpoints.

**Why.** Liver uptake is a common reference region in PSMA-PET reading (e.g. for miPSMA expression scores). A
miscalibrated scanner shifts every SUV at that site; per-scan checks cannot see it.

**Limit.** A site whose patients truly differ in liver uptake would be flagged too; the query lets the site say so.
