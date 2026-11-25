# 5. Content-addressed lineage and a sealed evidence pack

**Decision.** Artifacts are named by the hash of their content; steps record inputs, outputs, parameters, the code
version (a hash of the source) and the config hash. The evidence pack is written without timestamps and sealed with
an HMAC over the manifest of file hashes.

**Why.** An auditor asks where a number came from and whether anything changed since. Hashes answer both; the
same code, config and data give the same pack byte for byte, which CI checks.
