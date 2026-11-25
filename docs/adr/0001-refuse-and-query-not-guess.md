# 1. Refuse and query, never guess a unit

**Decision.** A weight or injected dose outside its plausible range blocks the series. The pipeline drafts a query
to the site and uses the value the site confirms.

**Why.** A weight of 82,000 is almost certainly grams, but "almost certainly" is not evidence. A rescaled value
that turns out wrong is invisible in every later number; a refused series is visible and recoverable. In the dev
sites, queries recover most refused series (see the results), and switching queries off loses about a quarter of scans.

**Cost.** Data arrives later; sites that do not answer lose series.
