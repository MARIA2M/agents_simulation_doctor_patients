# tests/test_evaluate.py
# Reading a batch back off disk and scoring it against patients/*.json (4.7).

import json

import pytest

import evaluate
from ahead_agent.config import BIPQ_DIMENSIONS, BMQ_SUBSCALES
from ahead_agent.evaluation import evaluate_batch


def _document(patient_id, bipq_score, bmq_score=3.0):
    """What write_report leaves on disk: asdict(Report), not the raw reply."""
    return {
        "patient_id": patient_id,
        "attempts": 1,
        "parsed": True,
        "report": {
            "patient_id": patient_id,
            "clinical_summary": "stable",
            "bipq": {
                name: {"dimension": name, "evidence": [{"quote": "q", "turn": 1}],
                       "reasoning": "said so", "score": bipq_score, "confidence": 0.8}
                for name in BIPQ_DIMENSIONS
            },
            "bmq": {
                name: {"dimension": name, "evidence": [], "reasoning": "said so",
                       "score": bmq_score, "confidence": 0.5}
                for name in BMQ_SUBSCALES
            },
            "causes": [],
            "causes_evidence": [],
        },
    }


def _write(directory, name, payload):
    run = directory / name
    run.mkdir()
    (run / "report.json").write_text(json.dumps(payload))
    return run


@pytest.fixture
def batch(tmp_path):
    """Two patients, one report each, with numbers that can be checked by hand.

    P1 is scored 6 against a truth of 4 on every B-IPQ dimension; P2 is exact.
    """
    patients = tmp_path / "patients"
    patients.mkdir()
    for patient_id, truth in (("P1", 4), ("P2", 8)):
        b_ipq = {name: truth for name in BIPQ_DIMENSIONS}
        b_ipq["causes"] = ["stress"]
        (patients / f"{patient_id}.json").write_text(json.dumps({
            "patient_id": patient_id,
            "disease_profile": {"diagnosis": "d"},
            "belief_profile": {"b_ipq": b_ipq,
                               "bmq": {name: 3.0 for name in BMQ_SUBSCALES}},
        }))

    runs = tmp_path / "batch"
    runs.mkdir()
    _write(runs, "P1-r1", _document("P1", 6))
    _write(runs, "P2-r1", _document("P2", 8))

    return patients, runs


# ── Reading it back ──────────────────────────


def test_a_stored_report_comes_back_as_a_report(batch):
    """The document write_report saved has the shape parse() reads."""
    _, runs = batch
    reports, unparsed = evaluate.load_reports(runs)

    assert unparsed == []
    assert len(reports) == 2
    assert reports[0][1].bipq["concern"].score == 6.0
    assert reports[0][1].bipq["concern"].evidence[0].quote == "q"


def test_the_patient_id_comes_from_the_document_not_the_directory(batch):
    """The directory is `P1-r1`; keying on it would make every repeat a new patient."""
    _, runs = batch

    assert [patient_id for patient_id, _ in evaluate.load_reports(runs)[0]] == ["P1", "P2"]


def test_a_report_that_never_parsed_is_counted_and_not_scored(batch):
    """4.4 again: an unusable report is a gap, never an error of zero."""
    _, runs = batch
    _write(runs, "P3-r1", {"patient_id": "P3", "attempts": 3, "parsed": False, "report": None})

    reports, unparsed = evaluate.load_reports(runs)

    assert unparsed == ["P3-r1"]
    assert len(reports) == 2


def test_the_truth_is_the_belief_profile_and_nothing_else(batch):
    """4.1 — the ground truth comes from patients/*.json, and only that field."""
    patients, _ = batch
    truth = evaluate.load_truth(patients)

    assert sorted(truth) == ["P1", "P2"]
    assert set(truth["P1"]) == {"b_ipq", "bmq"}
    assert "disease_profile" not in truth["P1"]


# ── The numbers, by hand ─────────────────────


def test_the_metrics_are_what_the_two_reports_say(batch):
    """P1 is two points high on 8 dimensions, P2 exact: 16 error over 24 scores."""
    patients, runs = batch
    truth = evaluate.load_truth(patients)
    reports, _ = evaluate.load_reports(runs)

    metrics = evaluate_batch([(parsed, truth[pid]) for pid, parsed in reports])

    assert metrics.mae == round(16 / 24, 3)
    assert metrics.coverage_rate == 1.0
    assert metrics.by_dimension["concern"].mae == 1.0
    assert metrics.by_dimension["concern"].bias == 1.0
    assert metrics.by_dimension["specific_necessity"].mae == 0.0


def test_a_dimension_the_doctor_left_out_is_excluded_and_counted(batch):
    """A null score lowers the coverage, and never the MAE."""
    patients, runs = batch
    document = _document("P2", 8)
    document["report"]["bipq"]["coherence"]["score"] = None
    (runs / "P2-r1" / "report.json").write_text(json.dumps(document))

    truth = evaluate.load_truth(patients)
    reports, _ = evaluate.load_reports(runs)
    metrics = evaluate_batch([(parsed, truth[pid]) for pid, parsed in reports])

    assert metrics.by_dimension["coherence"].scored == 1
    assert metrics.by_dimension["coherence"].na == 1
    assert metrics.by_dimension["coherence"].coverage_rate == 0.5
    assert metrics.mae == round(16 / 23, 3)


# ── What it leaves behind ────────────────────


def test_the_written_file_keeps_the_coverage_rate(batch):
    """`coverage_rate` is a property, so asdict drops it unless it is added back."""
    patients, runs = batch
    truth = evaluate.load_truth(patients)
    reports, unparsed = evaluate.load_reports(runs)
    metrics = evaluate_batch([(parsed, truth[pid]) for pid, parsed in reports])

    path = evaluate.write_evaluation(runs, "test-1", metrics, reports, unparsed)
    written = json.loads(path.read_text())

    assert written["by_dimension"]["concern"]["coverage_rate"] == 1.0
    assert written["by_report"][0]["coverage_rate"] == 1.0
    assert written["ground_truth_source"] == "patients/*.json"
    assert written["reports"] == 2 and written["patients"] == 2


def test_a_missing_number_prints_as_a_gap_never_as_zero():
    """A dash and a 0.00 mean opposite things in the table."""
    assert evaluate._cell(None) == "-"
    assert evaluate._cell(0.0) == "0.00"
    assert evaluate._cell(-0.4, sign=True) == "-0.40"
    assert evaluate._cell(1.45, sign=True) == "+1.45"
