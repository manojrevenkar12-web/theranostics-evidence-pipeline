from types import SimpleNamespace

from tep.knowledge.reader import ClaudeReader, Proposal, parse
from tep.knowledge.validate import check, decide
from tep.lineage.store import Lineage

TEXT = "Patient: P-1\nPSMA-avid vertebra (SUVmax 14.8) on 2025-04-03.\nCycle 1: Lu-PSMA-I&T, 7.4 GBq, administered on 2025-04-13.\n"


def P(**k):
    base = dict(doc_id="d1", kind="finding", code="REG:BONE", label="bone", date="2025-04-03", value=14.8,
                span="PSMA-avid vertebra (SUVmax 14.8) on 2025-04-03.")
    base.update(k)
    return Proposal(**base)


def test_a_correct_fact_passes():
    assert check(P(), TEXT)[0]


def test_invented_sentence_wrong_number_and_wrong_code_are_refused():
    assert check(P(span="PSMA-avid hepatic lesion (SUVmax 11.0) on 2025-04-03."), TEXT)[1] == "sentence not in document"
    assert check(P(value=148.0), TEXT)[1] == "number not in sentence"
    assert check(P(code="REG:LIVER"), TEXT)[1] == "sentence does not name the coded term"
    assert check(P(date="2025-04-04"), TEXT)[1] == "date not in sentence"


def test_new_term_is_induced_only_with_enough_documents_and_sites():
    span = "Cycle 1: Lu-PSMA-I&T, 7.4 GBq, administered on 2025-04-13."
    prop = lambda i: P(doc_id=f"d{i}", kind="therapy", code=None, label="Lu-PSMA-I&T", date="2025-04-13", value=7.4, span=span)  # noqa: E731
    few = [(prop(i), TEXT, "a") for i in range(5)]
    d, onto = decide(few)
    assert not onto.induced and all(not x.accepted for x in d)
    many = [(prop(i), TEXT, "ab"[i % 2]) for i in range(4)]
    d, onto = decide(many)
    assert onto.induced == {"lu-psma-i&t": "NEW:lu_psma_i_t"} and all(x.accepted for x in d)


def test_claude_reader_output_goes_through_the_same_parser():
    raw = '{"facts": [{"kind": "psa", "code": "LAB:PSA", "label": "PSA", "date": "2025-04-03", "value": 4.2, "span": "x"}]}'
    client = SimpleNamespace(messages=SimpleNamespace(create=lambda **k: SimpleNamespace(content=[SimpleNamespace(text=raw)])))
    [p] = ClaudeReader(client).read("d1", "text")
    assert p.value == 4.2 and p.code == "LAB:PSA"
    assert parse("d1", "not json") == []


def test_lineage_traces_a_number_back_to_its_sources():
    lin = Lineage("v", "c")
    src = [lin.source("f1", "dicom", "a"), lin.source("f2", "dicom", "b")]
    a = lin.step("ingest", src, {"series": {"x": 1}})
    b = lin.step("model", [a["series"]], {"auc": 0.8})
    assert lin.sources_of(b["auc"]) == ["f1", "f2"]
    lin2 = Lineage("v", "c")
    src2 = [lin2.source("f2", "dicom", "b"), lin2.source("f1", "dicom", "a")]
    a2 = lin2.step("ingest", src2, {"series": {"x": 1}})
    lin2.step("model", [a2["series"]], {"auc": 0.8})
    assert lin.digest() == lin2.digest()


def test_a_recurring_typo_is_held_as_a_misspelling():
    from tep.knowledge.validate import misspelling_of

    assert misspelling_of("vertbra") == "vertebra"
    assert misspelling_of("Lu-PSMA-I&T") is None and misspelling_of("miPSMA score") is None


def test_a_german_site_gets_a_german_letter():
    from tep.agent.site_queries import draft
    from tep.ingest.rules import Issue

    q = draft("charite", "de", "ACC1", [Issue("weightUnits", True, "PatientWeight", "82000", "Patient weight 82000 kg is outside")])
    assert "Körpergewicht ist mit 82000 kg angegeben" in q.text and "Patient weight" not in q.text
