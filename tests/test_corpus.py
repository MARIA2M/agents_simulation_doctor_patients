# tests/test_corpus.py
# The 10 patients are the ones the Ruby arm ran (0.3), with their ground truth.

import json

import pytest

from ahead_agent.config import BIPQ_DIMENSIONS, BMQ_SUBSCALES, CAUSES_DIMENSION, REPO_ROOT

PATIENTS_DIR = REPO_ROOT / "patients"
RUBY_PATIENTS_DIR = REPO_ROOT.parent / "modified_versions" / "ruby_version" / "patients"

PROFILES = sorted(PATIENTS_DIR.glob("*.json"))


def test_corpus_has_ten_patients():
    assert len(PROFILES) == 10


def _no_prescription(profile) -> bool:
    """Watch and wait: nothing is prescribed, so the specific subscales of the
    BMQ have no drug to be about and their ground truth is NA (C1)."""
    return "watch and wait" in profile["disease_profile"]["treatment_regimen"].lower()


@pytest.mark.parametrize("path", PROFILES, ids=lambda p: p.stem)
def test_profile_carries_ground_truth(path):
    profile = json.loads(path.read_text())

    assert profile["patient_id"] == path.stem
    assert profile["disease_profile"]["diagnosis"]
    assert profile["disease_profile"]["demographics"]

    b_ipq = profile["belief_profile"]["b_ipq"]
    bmq = profile["belief_profile"]["bmq"]

    for dimension in BIPQ_DIMENSIONS:
        assert isinstance(b_ipq[dimension], (int, float)), dimension

    for subscale in BMQ_SUBSCALES:
        if subscale.startswith("specific_") and _no_prescription(profile):
            assert bmq[subscale] is None, f"{subscale} scored without a prescription"
        else:
            assert isinstance(bmq[subscale], (int, float)), subscale

    # causes sits inside b_ipq alongside the eight numbers, but is a list of
    # strings: anything that iterates b_ipq and averages will trip over it.
    assert isinstance(b_ipq[CAUSES_DIMENSION], list) and b_ipq[CAUSES_DIMENSION]


@pytest.mark.skipif(not RUBY_PATIENTS_DIR.exists(), reason="Ruby arm not present")
@pytest.mark.parametrize("path", PROFILES, ids=lambda p: p.stem)
def test_profile_is_identical_to_the_ruby_arm(path):
    """Both arms must score the same patients or their results are not comparable."""
    reference = RUBY_PATIENTS_DIR / path.name

    assert reference.exists(), f"{path.name} is missing from the Ruby arm"
    assert path.read_bytes() == reference.read_bytes()
