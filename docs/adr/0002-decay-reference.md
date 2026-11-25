# 2. Respect the image's decay-correction reference

**Decision.** SUV decays the injected dose to scan start only when `DecayCorrection` is `START`. With `ADMIN` the
image is already corrected to injection time and the dose is used as injected.

**Why.** Many SUV implementations always decay the dose. For Ga-68 with about 60–90 minutes of uptake that
inflates SUV at `ADMIN` sites by a factor of roughly 1.8–2.5. The ablation shows it in SUV error, pairing and RECIP.
