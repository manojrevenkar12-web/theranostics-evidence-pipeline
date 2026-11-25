# 4. The reader proposes, code decides

**Decision.** Extraction from reports goes through a `Reader` that returns facts with the exact sentence. A fact is
kept only when the sentence is in the de-identified document, its date and number appear in that sentence, and the
sentence names the coded term. New terms are induced after 3 documents from 2 sites, unless one edit away from a
known word.

**Why.** A model that paraphrases, invents a sentence or turns 7.4 into 74 cannot be audited. Requiring a verbatim
sentence makes every fact traceable and lets code refuse the rest. The ablation keeps every proposal: invented
facts and wrong numbers enter the graph.
