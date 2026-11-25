# 6. De-identify by allowlist

**Decision.** Headers leave the pipeline through a list of fields that may leave; everything else, private tags
and free text included, is dropped. Patients get keyed pseudonyms; dates shift per patient by a keyed offset in
headers and documents alike, so intervals are preserved.

**Why.** A blocklist misses the field nobody thought of: sites put names in `ImageComments` and private tags. The
lab counts identifiers in everything that leaves: zero for the pipeline, hundreds without de-identification.

**Limit.** Pixel data is not scanned for burned-in text; PET series rarely carry it, secondary captures do.
