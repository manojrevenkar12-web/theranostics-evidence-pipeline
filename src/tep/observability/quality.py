"""Data quality per site and series in SQL (DuckDB here, the same SQL runs on BigQuery)."""

from __future__ import annotations

from typing import Any

import duckdb
import pandas as pd

SITE_QUALITY = """
SELECT site,
       COUNT(*)                                                    AS series,
       AVG(CASE WHEN has_weight AND has_dose AND has_times THEN 1 ELSE 0 END) AS completeness,
       AVG(CASE WHEN blocking_issues = 0 THEN 1 ELSE 0 END)        AS validity,
       AVG(CASE WHEN status = 'quarantined' THEN 1 ELSE 0 END)     AS quarantined_share,
       AVG(CASE WHEN status = 'recovered' THEN 1 ELSE 0 END)       AS recovered_share,
       SUM(duplicate_instances)                                    AS duplicate_instances,
       AVG(CASE WHEN order_fixed THEN 1 ELSE 0 END)                AS order_fixed_share,
       MEDIAN(liver_reference)                                     AS liver_reference_median
FROM series
GROUP BY site
ORDER BY site
"""

ISSUES = """
SELECT site, code, COUNT(*) AS n
FROM issues
GROUP BY site, code
ORDER BY site, code
"""


def site_quality(series: pd.DataFrame, issues: pd.DataFrame) -> dict[str, Any]:
    con = duckdb.connect()
    con.register("series", series)
    con.register("issues", issues if len(issues) else pd.DataFrame({"site": [], "code": []}))
    q = con.execute(SITE_QUALITY).df()
    i = con.execute(ISSUES).df() if len(issues) else pd.DataFrame(columns=["site", "code", "n"])
    con.close()
    return {"sites": q.round(4).to_dict(orient="records"), "issues": i.to_dict(orient="records")}
