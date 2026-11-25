import datetime as dt
from pathlib import Path

import numpy as np
import pytest

from tep.ingest import deid
from tep.ingest.rules import check
from tep.ingest.series import read_drop
from tep.ingest.suv import Corrections, suv_factor
from tep.ingest.volume import affine_ras, stack
from tep.world.cohort import cohort
from tep.world.dicom_out import site_defects, write_scan
from tep.world.render import suv_volume

SEED = {"v": 101}


def _scan_with(seed, world, defect=None, site=None):
    for sd in range(seed, seed + 30):
        for p in cohort(sd, world):
            for s in p.scans:
                d = site_defects(sd, world, s)
                if (defect is None and not d or defect in d) and (site is None or s.site == site):
                    SEED["v"] = sd
                    return p, s, d
    pytest.skip("no such scan in this world")


def test_same_seed_same_cohort(small_root):
    a, b = cohort(5, "dev"), cohort(5, "dev")
    assert [p.key for p in a] == [p.key for p in b] and a[3].scans[0].lesions == b[3].scans[0].lesions


@pytest.mark.parametrize("site", ["charite", "uke"])  # START and ADMIN decay references
def test_dicom_round_trip_gives_the_true_suv(small_root, tmp_path, site):
    p, s, d = _scan_with(101, "dev", None, site)
    write_scan(SEED["v"], "dev", p, s, tmp_path)
    [series] = read_drop(tmp_path)
    assert not [i for i in check(series) if i.blocking]
    suv = stack(series) * suv_factor(series)
    truth = suv_volume(SEED["v"], s)
    m = truth > 1
    assert abs(np.median(suv[m] / truth[m]) - 1) < 0.002


def test_rules_refuse_grams_and_name_the_fix(small_root, tmp_path):
    p, s, d = _scan_with(101, "dev", "weightGrams")
    write_scan(SEED["v"], "dev", p, s, tmp_path)
    [series] = read_drop(tmp_path)
    issues = {i.code: i for i in check(series)}
    assert issues["weightUnits"].blocking and "grams" in issues["weightUnits"].message
    good = suv_factor(series, Corrections(weight_kg=s.weight_kg))
    assert abs(good * 1000 - suv_factor(series)) / suv_factor(series) < 1e-3  # header weight has one decimal


def test_reversed_instances_are_ordered_by_position(small_root, tmp_path):
    p, s, d = _scan_with(101, "dev", "instanceReversed")
    write_scan(SEED["v"], "dev", p, s, tmp_path)
    [series] = read_drop(tmp_path)
    assert any(i.code == "instanceOrder" and not i.blocking for i in check(series))
    by_pos, by_inst = stack(series, True), stack(series, False)
    assert np.allclose(by_pos[:, :, ::-1], by_inst)


def test_missing_slice_blocks(small_root, tmp_path):
    p, s, d = _scan_with(101, "dev", "missingSlice")
    write_scan(SEED["v"], "dev", p, s, tmp_path)
    [series] = read_drop(tmp_path)
    assert any(i.code == "missingSlice" and i.blocking for i in check(series))


def test_duplicate_send_is_kept_once(small_root, tmp_path):
    p, s, d = _scan_with(101, "dev", "duplicateSend")
    write_scan(SEED["v"], "dev", p, s, tmp_path)
    assert len(read_drop(tmp_path)) == 1 and len(read_drop(tmp_path, dedupe=False)) == 2
    [series] = read_drop(tmp_path)
    assert series.duplicate_instances == len(series.slices)


def test_affine_maps_dicom_lps_to_nifti_ras(small_root, tmp_path):
    p, s, d = _scan_with(101, "dev")
    write_scan(SEED["v"], "dev", p, s, tmp_path)
    [series] = read_drop(tmp_path)
    a = affine_ras(series)
    x = a @ np.array([3, 4, 5, 1.0])
    # voxel (3,4,5) is 15 mm along +x (left in LPS) and 20 mm along +y (posterior); RAS flips both
    assert np.allclose(x[:3], [-15.0, -20.0, 25.0])


def test_deid_allowlist_drops_names_and_private_tags(small_root, tmp_path):
    p, s, d = _scan_with(101, "dev", "phiComments")
    write_scan(SEED["v"], "dev", p, s, tmp_path)
    [series] = read_drop(tmp_path)
    h = deid.header(series.header, "P-x")
    text = str(h)
    assert p.family not in text and "ImageComments" not in h and p.birth_date.strftime("%Y%m%d") not in text
    assert h["StudyDate"] != series.header.StudyDate


def test_linkage_matches_spelling_variants():
    assert deid.linkage_key("Müller^Hans", "19500101") == deid.linkage_key("MUELLER^HANS", "19500101")
    assert deid.pseudonym(deid.linkage_key("García^Jose", "1")) == deid.pseudonym(deid.linkage_key("GARCIA^JOSE", "1"))


def test_text_deid_scrubs_and_shifts_consistently():
    doc = "Patient: Müller, Hans; DOB 1950-01-01; MRN CHA123\nPSA 4.2 ng/ml on 2025-03-10.\nPSA 2.0 am 11.03.2025.\n"
    out = deid.text(doc, "P-1", ["Müller", "Hans"], ["CHA123"], "19500101")
    assert "Müller" not in out and "CHA123" not in out and "1950" not in out
    off = deid.date_offset_days("P-1")
    assert (dt.date(2025, 3, 10) + dt.timedelta(days=off)).isoformat() in out
    assert (dt.date(2025, 3, 11) + dt.timedelta(days=off)).strftime("%d.%m.%Y") in out


def test_defects_depend_on_the_world_only(small_root):
    p, s, _ = _scan_with(101, "dev")
    assert site_defects(SEED["v"], "dev", s) == site_defects(SEED["v"], "dev", s)
    _ = Path
