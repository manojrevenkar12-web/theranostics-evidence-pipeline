import json

import pytest

from tep.lab import study
from tep.lab.process import SWITCHES, Lineage, code_version, prepare, run


@pytest.fixture()
def prep(small_root, tmp_path_factory):
    return prepare(101, "dev", tmp_path_factory.mktemp("w"))


def test_pipeline_leaks_nothing_and_naive_does(prep):
    p = run(prep, set()).measures
    n = run(prep, set(SWITCHES)).measures
    assert p["phiLeaks"] == 0 and n["phiLeaks"] > 0
    assert p["hallucinatedFactsKept"] == 0
    assert p["suvErrorMedian"] < 0.02


def test_same_world_same_answer(prep):
    l1, l2 = Lineage(code_version(), "c"), Lineage(code_version(), "c")
    a, b = run(prep, set(), l1), run(prep, set(), l2)
    assert json.dumps(a.measures, sort_keys=True, default=str) == json.dumps(b.measures, sort_keys=True, default=str)
    assert l1.digest() == l2.digest()
    assert l1.runs  # lineage was recorded


def test_heldout_runs_once(small_root):
    (small_root / "reports").mkdir(exist_ok=True)
    (small_root / "reports" / "heldout.lock").write_text("{}")
    with pytest.raises(study.Locked):
        study.run_heldout_once()
