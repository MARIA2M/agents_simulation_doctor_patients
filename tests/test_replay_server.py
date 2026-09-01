# tests/test_replay_server.py
# The read layer of the consultation viewer. What is tested is the reading, not
# the HTML: which consultations a batch is said to hold, whose they are, and
# what one of them carries once it has been read back off disk.
#
# Nothing here needs a real batch. Every fixture is built in tmp_path, so these
# tests say the same thing on a machine with an empty runs/.

import json

import pytest
from fastapi.testclient import TestClient

import replay_server
from ahead_agent.config import BIPQ_DIMENSIONS, BMQ_SUBSCALES
from ahead_agent.evaluation import evaluate_patient
from ahead_agent.report import parse


# ── Building a batch on disk ─────────────────


def _report_document(patient_id, bipq_score=5.0, bmq_score=3.0, turn=1):
    """What write_report leaves: asdict(Report), not the raw reply."""
    return {
        "patient_id": patient_id,
        "attempts": 1,
        "parsed": True,
        "report": {
            "patient_id": patient_id,
            "clinical_summary": "stable",
            "bipq": {
                name: {"dimension": name,
                       "evidence": [{"quote": "it wears me down", "turn": turn}],
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


def _transcript(patient_id):
    """Doctor and patient share a turn number: a turn is an exchange (D13)."""
    return {
        "patient_id": patient_id,
        "turns": 1,
        "stop_reason": "doctor",
        "conversation": [
            {"turn": 1, "role": "doctor", "content": "How has it been?"},
            {"turn": 1, "role": "patient", "content": "it wears me down"},
        ],
        "coverage_hint": {},
        "working_notes": [],
        "events": [],
        "usage": [],
    }


def _write(run_dir, patient_id, report=True, **report_kwargs):
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "transcript.json").write_text(json.dumps(_transcript(patient_id)))
    if report:
        (run_dir / "report.json").write_text(
            json.dumps(_report_document(patient_id, **report_kwargs)))
    return run_dir


TRUTH = {
    "CLL-003": {
        "patient_id": "CLL-003",
        "disease_profile": {"diagnosis": "CLL", "treatment_regimen": "watch and wait",
                            "demographics": {"age": 61}},
        "belief_profile": {
            "b_ipq": {name: 4.0 for name in BIPQ_DIMENSIONS},
            "bmq": {name: 3.0 for name in BMQ_SUBSCALES},
        },
    },
    "HIV-005": {
        "patient_id": "HIV-005",
        "disease_profile": {"diagnosis": "HIV", "treatment_regimen": "ART",
                            "demographics": {"age": 34}},
        "belief_profile": {
            "b_ipq": {name: 6.0 for name in BIPQ_DIMENSIONS},
            "bmq": {name: 2.0 for name in BMQ_SUBSCALES},
        },
    },
}


@pytest.fixture
def runs(tmp_path):
    """Two arms over two patients: CLL-003 twice in one arm, HIV-005 once in each."""
    root = tmp_path / "runs"
    _write(root / "arm-a" / "CLL-003-r1", "CLL-003")
    _write(root / "arm-a" / "CLL-003-r2", "CLL-003")
    _write(root / "arm-a" / "HIV-005-r1", "HIV-005")
    _write(root / "arm-b" / "HIV-005-r1", "HIV-005")
    (root / "arm-a" / "metadata.json").write_text(
        json.dumps({"profile": "hpc", "features": {"coverage_hint": "off"}}))
    return root


# ── What a batch is said to hold ─────────────


def test_a_directory_that_is_not_a_batch_is_skipped(tmp_path):
    """runs/historic/ holds batches, not consultations. Walking into it as if it
    were one would offer a batch with nothing in it."""
    root = tmp_path / "runs"
    _write(root / "historic" / "e4-1" / "CLL-003-r1", "CLL-003")

    assert replay_server.list_runs(root) == []


def test_the_disk_decides_what_exists_not_the_index(runs):
    """A batch resumed after a walltime kill rewrites batch.json with that
    launch's consultations alone. Trusting the index loses whole sessions — a
    batch of 20 read as 8 — so the index only says who each one is."""
    (runs / "arm-a" / "batch.json").write_text(json.dumps({
        "consultations": [{"run": "CLL-003-r1", "patient_id": "CLL-003", "repeat": 1},
                          {"run": "CLL-003-r9", "patient_id": "CLL-003", "repeat": 9}],
    }))

    arm_a = next(b for b in replay_server.list_runs(runs) if b["batch"] == "arm-a")
    listed = {c["run"] for c in arm_a["consultations"]}

    assert "CLL-003-r9" not in listed      # named by the index, not on disk
    assert "CLL-003-r2" in listed          # on disk, not named by the index


def test_the_index_is_still_read_for_how_it_ended(runs):
    """stop_reason lives in batch.json and nowhere else, and it is the one thing
    the picker has to show: turn_cap is a result, not a fault."""
    (runs / "arm-a" / "batch.json").write_text(json.dumps({
        "consultations": [{"run": "CLL-003-r1", "patient_id": "CLL-003",
                           "repeat": 1, "stop_reason": "turn_cap", "events": 2}],
    }))

    arm_a = next(b for b in replay_server.list_runs(runs) if b["batch"] == "arm-a")
    first = next(c for c in arm_a["consultations"] if c["run"] == "CLL-003-r1")

    assert first["stop_reason"] == "turn_cap"
    assert first["events"] == 2


# ── One patient at a time ────────────────────


def test_only_the_patient_asked_for_comes_back(runs):
    everyone = {c["patient_id"]
                for b in replay_server.list_runs(runs, "CLL-003")
                for c in b["consultations"]}

    assert everyone == {"CLL-003"}


def test_a_batch_holding_nobody_asked_for_disappears_entirely(runs):
    """Filtering the consultations and leaving the batch would put an empty arm
    on screen, and an arm with no consultations reads as an arm that failed."""
    names = {b["batch"] for b in replay_server.list_runs(runs, "CLL-003")}

    assert names == {"arm-a"}   # arm-b is HIV-005 only


def test_a_patient_with_a_profile_but_no_consultation_is_not_offered(runs):
    """The corpus has ten; this viewer can only show what was run."""
    offered = {p["patient_id"] for p in replay_server.list_patients(runs, TRUTH)}

    assert offered == {"CLL-003", "HIV-005"}
    assert "CLL-001" not in offered


def test_a_consultation_whose_profile_is_gone_is_still_offered(runs):
    """Read from the directory names, not the corpus: a transcript is worth
    reading even when nothing is left to score it against."""
    offered = replay_server.list_patients(runs, {})

    assert {p["patient_id"] for p in offered} == {"CLL-003", "HIV-005"}
    assert all(p["diagnosis"] is None for p in offered)


def test_the_counts_are_consultations_and_arms_not_one_number(runs):
    """Three consultations over two arms is a different thing from three over
    one, and the picker is where that has to be visible."""
    hiv = next(p for p in replay_server.list_patients(runs, TRUTH)
               if p["patient_id"] == "HIV-005")

    assert hiv["consultations"] == 2
    assert hiv["batches"] == 2


# ── Reading one consultation ─────────────────


def test_a_consultation_with_no_report_still_reads(runs):
    """Two of forty consultations left no report at all. The viewer has to show
    the conversation anyway — that is the only thing left to look at."""
    _write(runs / "arm-a" / "CLL-003-r3", "CLL-003", report=False)

    c = replay_server.read_consultation(runs, "arm-a", "CLL-003-r3", TRUTH)

    assert c["report"] is None
    assert c["evaluation"] is None
    assert len(c["transcript"]["conversation"]) == 2


def test_the_report_is_re_parsed_so_an_off_scale_score_is_na(runs):
    """4.4, applied here too rather than taken on trust. The old arm clamped an
    illegal value into a legal-looking one and it counted as a hit."""
    document = _report_document("CLL-003")
    document["report"]["bipq"]["identity"]["score"] = 44.0     # off the 0-10 scale
    (runs / "arm-a" / "CLL-003-r1" / "report.json").write_text(json.dumps(document))

    c = replay_server.read_consultation(runs, "arm-a", "CLL-003-r1", TRUTH)

    assert c["report"]["bipq"]["identity"]["score"] is None


def test_the_evaluation_is_the_one_evaluate_py_would_give(runs):
    """The number on screen has to be the number in evaluation.json. Computing it
    a second way here is how the two drift apart without anyone noticing."""
    c = replay_server.read_consultation(runs, "arm-a", "CLL-003-r1", TRUTH)

    document = json.loads((runs / "arm-a" / "CLL-003-r1" / "report.json").read_text())
    expected = evaluate_patient(parse(json.dumps(document["report"]), "CLL-003"),
                                TRUTH["CLL-003"]["belief_profile"])

    assert c["evaluation"]["mae"] == expected.mae
    assert c["evaluation"]["mean_bias"] == expected.mean_bias
    assert c["evaluation"]["coverage_rate"] == expected.coverage_rate


def test_an_na_is_counted_and_not_an_error_of_zero(runs):
    """general_overuse comes back NA in every consultation of the demo matrix.
    Counting it as a hit would give an empty report a perfect score."""
    document = _report_document("CLL-003")
    document["report"]["bmq"]["general_overuse"]["score"] = None
    (runs / "arm-a" / "CLL-003-r1" / "report.json").write_text(json.dumps(document))

    c = replay_server.read_consultation(runs, "arm-a", "CLL-003-r1", TRUTH)

    assert c["evaluation"]["na"] == 1
    assert c["evaluation"]["scored"] == 11


def test_a_post_process_that_has_not_run_is_absent_not_an_error(runs):
    """cover.py and fidel.py may simply not have run yet, which is the normal
    state of a fresh batch and not something to fail on."""
    c = replay_server.read_consultation(runs, "arm-a", "CLL-003-r1", TRUTH)

    assert c["coverage"] is None
    assert c["fidelity"] is None


def test_the_coverage_and_fidelity_entries_are_matched_by_run(runs):
    """Both files hold one entry per consultation. Taking the first would show
    every repeat the verdict of r1."""
    (runs / "arm-a" / "fidelity.json").write_text(json.dumps({"by_run": [
        {"run": "CLL-003-r1", "passed": True, "contradictions": 0},
        {"run": "CLL-003-r2", "passed": False, "contradictions": 1},
    ]}))

    second = replay_server.read_consultation(runs, "arm-a", "CLL-003-r2", TRUTH)

    assert second["fidelity"]["passed"] is False
    assert second["fidelity"]["contradictions"] == 1


# ── Over HTTP ────────────────────────────────


@pytest.fixture
def client(runs, tmp_path, monkeypatch):
    """The app with the corpus stubbed: these tests are about routing, not about
    reading patients/*.json, which corpus.py already has tests for."""
    monkeypatch.setattr(replay_server.corpus, "load_corpus", lambda _: TRUTH)
    return lambda only=None: TestClient(
        replay_server.build_app(runs, tmp_path / "patients", only))


def test_the_page_is_served_at_the_root(client):
    response = client().get("/")

    assert response.status_code == 200
    assert "consultation viewer" in response.text


def test_a_dot_dot_in_the_url_never_reads_outside_runs(client):
    """Both parts of the path are used as directory names, so without this a
    `..` in either one walks out of runs/."""
    assert client().get("/api/runs/../../etc/passwd").status_code in (400, 404)
    assert client().get("/api/runs/%2e%2e/%2e%2e").status_code in (400, 404)


def test_a_consultation_that_is_not_there_is_a_404(client):
    assert client().get("/api/runs/arm-a/CLL-003-r99").status_code == 404


def test_the_query_string_picks_one_patient(client):
    body = client().get("/api/runs", params={"patient": "HIV-005"}).json()

    assert {c["patient_id"] for b in body for c in b["consultations"]} == {"HIV-005"}


def test_a_server_pinned_to_one_patient_cannot_be_talked_out_of_it(client):
    """--patient is a decision about what this instance shows, not a default the
    browser may override by asking for someone else."""
    body = client("CLL-003").get("/api/runs", params={"patient": "HIV-005"}).json()

    assert {c["patient_id"] for b in body for c in b["consultations"]} == {"CLL-003"}


def test_the_pinned_patient_is_the_only_one_offered(client):
    body = client("CLL-003").get("/api/patients").json()

    assert [p["patient_id"] for p in body] == ["CLL-003"]
