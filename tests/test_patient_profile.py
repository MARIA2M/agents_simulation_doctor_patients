# tests/test_patient_profile.py
# Scores become behaviour, and a score that is missing becomes nothing (1.9).

import pytest

from ahead_agent import patient_profile
from ahead_agent.patient_profile import BIPQ_BANDS, BMQ_BANDS

from conftest import PATIENT


# ── Where one band ends and the next begins ──


@pytest.mark.parametrize(
    ("score", "band"),
    [(0, 0), (2, 0), (2.1, 1), (4, 1), (4.5, 2), (6, 2), (7, 3), (8, 3), (9, 4), (10, 4)],
)
def test_a_score_on_the_boundary_belongs_to_the_lower_band(score, band):
    """`score <= upper`, so 2 is still the first band and 2.1 is the second."""
    bands = BIPQ_BANDS["consequences"]

    assert patient_profile._band_for(bands, score) == bands[band][1]


@pytest.mark.parametrize(
    ("score", "band"),
    [(1.0, 0), (2.0, 0), (2.5, 1), (3.0, 1), (3.4, 2), (4.0, 2), (4.6, 3), (5.0, 3)],
)
def test_the_bmq_ladder_has_its_own_boundaries(score, band):
    """Four bands at 2/3/4/5, not the five of the B-IPQ."""
    bands = BMQ_BANDS["specific_necessity"]

    assert patient_profile._band_for(bands, score) == bands[band][1]


def test_a_score_above_the_last_bound_still_lands():
    """Ground truth is not range-checked here, so the top band is the catch-all."""
    bands = BIPQ_BANDS["consequences"]

    assert patient_profile._band_for(bands, 99) == bands[-1][1]


# ── A missing score is left out, never guessed (P9) ──


def test_a_dimension_without_a_score_is_skipped():
    lines = patient_profile._behaviour_lines(BIPQ_BANDS, {"concern": 8})

    assert lines.count("  - ") == 1
    assert BIPQ_BANDS["concern"][3][1] in lines


def test_a_score_that_is_not_a_number_is_skipped():
    """`causes` lives in b_ipq as a list, and must never be banded."""
    assert patient_profile._behaviour_lines(BIPQ_BANDS, {"concern": None, "identity": "high"}) == ""


def test_no_scores_at_all_is_an_empty_block():
    assert patient_profile._behaviour_lines(BMQ_BANDS, {}) == ""


# ── Watch and wait has no medication to believe in (C1) ──


def test_the_medication_block_disappears_without_bmq_scores():
    patient = {**PATIENT, "belief_profile": {**PATIENT["belief_profile"], "bmq": {}}}

    assert "HOW YOU SEE YOUR MEDICATION" not in patient_profile.describe_patient(patient)


def test_the_medication_block_appears_when_there_are_scores():
    assert "HOW YOU SEE YOUR MEDICATION" in patient_profile.describe_patient(PATIENT)


# ── What the patient is told about themselves ──


def test_the_clinical_facts_are_stated_outright():
    described = patient_profile.describe_patient(PATIENT)

    assert "58-year-old male" in described
    assert "Chronic Lymphocytic Leukemia (CLL)" in described


def test_the_score_itself_never_reaches_the_patient():
    """1.9 in one line: they express the score, they never read it."""
    described = patient_profile.describe_patient(PATIENT)

    for dimension, score in PATIENT["belief_profile"]["b_ipq"].items():
        if isinstance(score, (int, float)):
            assert f"{dimension}: {score}" not in described


def test_the_causes_they_believe_in_are_listed():
    assert "Genetics / family history" in patient_profile.describe_patient(PATIENT)


def test_no_causes_falls_back_to_not_being_sure():
    """An empty section reads to the model as a gap to fill in."""
    patient = {**PATIENT, "belief_profile": {"b_ipq": {"causes": []}, "bmq": {}}}

    assert "you are not sure" in patient_profile.describe_patient(patient)
