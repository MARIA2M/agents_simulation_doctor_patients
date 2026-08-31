# tests/test_coverage.py
# coverage.py V1 (§8, Etapa 6): evidence integrity, ungrounded scores, spread.
# Synthetic fixtures throughout — nothing here needs a batch on disk to exist.

import ast
import json
from pathlib import Path

import pytest

from ahead_agent import coverage
from ahead_agent.coverage import (
    CITED_UNSCORED,
    GROUNDED,
    SILENT,
    UNGROUNDED,
)


# ── Fixtures ─────────────────────────────────

# A turn is an EXCHANGE: nodes.py gives the doctor's line and the patient's
# reply the same number. The fixture is numbered that way on purpose — read it
# as two turns of two lines, not four turns.
CONVERSATION = [
    {"turn": 1, "role": "doctor", "content": "What brings you in today?"},
    {"turn": 1, "role": "patient", "content": "I can barely get through a shift any more."},
    {"turn": 2, "role": "doctor", "content": "And the tablets?"},
    {"turn": 2, "role": "patient", "content": "I'd not miss a dose, whatever else happens."},
]

SHIFT = "I can barely get through a shift any more."
DOSE = "I'd not miss a dose, whatever else happens."


def quote(text, turn):
    return {"quote": text, "turn": turn}


def report_body(**dimensions):
    """A stored report with only the dimensions named; the rest parse to NA."""
    from ahead_agent.config import BIPQ_DIMENSIONS

    body = {"bipq": {}, "bmq": {}, "causes": [], "causes_evidence": []}
    for name, (evidence, score) in dimensions.items():
        block = "bipq" if name in BIPQ_DIMENSIONS else "bmq"
        body[block][name] = {
            "evidence": evidence,
            "reasoning": "because they said so",
            "score": score,
            "confidence": 0.8,
        }
    return body


def write_run(batch: Path, patient_id: str, repeat: int, body, conversation=CONVERSATION):
    run_dir = batch / f"{patient_id}-r{repeat}"
    run_dir.mkdir(parents=True)
    (run_dir / "transcript.json").write_text(json.dumps({
        "patient_id": patient_id,
        "conversation": conversation,
        "coverage_hint": {},
        "working_notes": [],
    }))
    (run_dir / "report.json").write_text(json.dumps({
        "patient_id": patient_id, "parsed": True, "report": body,
    }))
    return run_dir


def check(text, turn, conversation=CONVERSATION):
    from ahead_agent.report import Evidence

    return coverage.check_quote(Evidence(quote=text, turn=turn), conversation)


# ── Verifying a quote (objective 3) ──────────


def test_a_quote_that_holds_up_passes_all_three():
    result = check(SHIFT, 1)

    assert (result.verbatim, result.in_named_turn, result.from_patient) == (True, True, True)
    assert result.verified


def test_the_doctor_line_of_the_same_turn_does_not_shadow_the_patient():
    """The bug e4-1 found: a turn holds both speakers, so matching on the number
    alone lands on the doctor and every quote in the batch came out unverified.
    Turn and speaker have to be matched together."""
    assert check(SHIFT, 1).verified          # turn 1 is also the doctor's greeting
    assert check(DOSE, 2).verified           # and turn 2 the doctor's question


def test_an_invented_quote_is_not_verbatim():
    assert not check("I feel completely fine about it.", 1).verbatim


def test_a_real_quote_filed_under_the_wrong_turn_is_caught():
    """The words are there. The turn the report points at is not where they are —
    which is the difference between citing and reconstructing."""
    result = check(SHIFT, 2)

    assert result.verbatim
    assert not result.in_named_turn
    assert not result.verified
    assert result.found_in == [1]        # and it says where they really are


def test_the_checks_stay_apart():
    """A quote never said and one merely misplaced are opposite findings; a
    single `verified` flag reports them the same, which is what hid the bug."""
    never_said = check("I feel completely fine about it.", 1)
    misplaced = check(SHIFT, 2)

    assert (never_said.verbatim, never_said.found_in) == (False, [])
    assert (misplaced.verbatim, misplaced.found_in) == (True, [1])


def test_the_doctor_quoting_itself_is_not_evidence():
    result = check("And the tablets?", 2)

    assert result.verbatim and result.in_named_turn
    assert not result.from_patient
    assert not result.verified


@pytest.mark.parametrize(
    ("text", "turn"),
    [
        ("I CAN BARELY get through a shift any more.", 1),
        ("I can barely   get through\na shift any more.", 1),
        ("I’d not miss a dose, whatever else happens.", 2),
    ],
    ids=["case", "whitespace", "curly apostrophe"],
)
def test_typography_is_not_fabrication(text, turn):
    """Normalised before comparing: a capital letter is not an invented quote.
    The rule travels in coverage.json so the rate stays reproducible."""
    assert check(text, turn).verified


# ── The four cells ───────────────────────────


def test_a_score_with_verified_evidence_is_grounded(tmp_path):
    body = report_body(consequences=([quote(SHIFT, 1)], 8))
    run = write_run(tmp_path / "b", "TEST-001", 1, body)

    result = coverage.read_consultation(run, "TEST-001", 1)

    assert result.dimensions["consequences"].state == GROUNDED


def test_a_score_with_no_evidence_at_all_is_ungrounded(tmp_path):
    """The alarm: a number that came from somewhere other than the conversation."""
    run = write_run(tmp_path / "b", "TEST-001", 1, report_body(consequences=([], 8)))

    result = coverage.read_consultation(run, "TEST-001", 1)

    assert result.dimensions["consequences"].state == UNGROUNDED
    assert result.ungrounded == ["consequences"]


def test_evidence_that_does_not_verify_is_evidence_of_nothing(tmp_path):
    """A quote that is not in the transcript supports nothing, so this lands in
    the same cell as no quote at all."""
    body = report_body(concern=([quote("I am terrified of dying", 1)], 7))
    run = write_run(tmp_path / "b", "TEST-001", 1, body)

    assert coverage.read_consultation(run, "TEST-001", 1).dimensions["concern"].state == UNGROUNDED


def test_quoting_and_then_declining_to_score_is_its_own_cell(tmp_path):
    body = report_body(timeline=([quote(DOSE, 2)], None))
    run = write_run(tmp_path / "b", "TEST-001", 1, body)

    assert coverage.read_consultation(run, "TEST-001", 1).dimensions["timeline"].state == CITED_UNSCORED


def test_a_dimension_never_touched_is_silent(tmp_path):
    run = write_run(tmp_path / "b", "TEST-001", 1, report_body())

    assert coverage.read_consultation(run, "TEST-001", 1).dimensions["general_overuse"].state == SILENT


def test_causes_can_never_be_scored(tmp_path):
    """It is open text (4.3), so it only ever lands in the unscored row — and it
    is still checked for evidence integrity like everything else."""
    body = report_body()
    body["causes"] = ["stress at work"]
    body["causes_evidence"] = [quote(SHIFT, 1)]
    run = write_run(tmp_path / "b", "TEST-001", 1, body)

    causes = coverage.read_consultation(run, "TEST-001", 1).dimensions["causes"]

    assert causes.score is None
    assert causes.state == CITED_UNSCORED


# ── Turns read out twice (V3 candidates) ─────


def test_a_turn_cited_by_two_dimensions_is_flagged(tmp_path):
    """That turn carried more than one thing, so at most one of them answers
    what was asked. Candidates for what the patient added unprompted."""
    line = quote(SHIFT, 1)
    run = write_run(tmp_path / "b", "TEST-001", 1,
                    report_body(consequences=([line], 8), identity=([line], 6)))

    assert coverage.read_consultation(run, "TEST-001", 1).turn_reuse == {
        1: ["consequences", "identity"]
    }


def test_a_turn_cited_once_is_not(tmp_path):
    run = write_run(tmp_path / "b", "TEST-001", 1,
                    report_body(consequences=([quote(SHIFT, 1)], 8)))

    assert coverage.read_consultation(run, "TEST-001", 1).turn_reuse == {}


# ── Spread across repeats (2.4) ──────────────


def batch_with(tmp_path, *scores):
    """One patient, one repeat per score given."""
    batch = tmp_path / "b"
    for repeat, score in enumerate(scores, start=1):
        write_run(batch, "TEST-001", repeat, report_body(consequences=([], score)))
    return coverage.read_batch(batch)


def _spread_of(batch, dimension):
    return next(s for s in batch.spreads if s.dimension == dimension)


def test_spread_is_none_below_the_projects_floor(tmp_path):
    """Arithmetic allows a sd from three points; TASKS 2.4 says that below five
    repeats the spread means nothing. The stricter of the two wins, because a
    number the design calls unreadable will be read anyway once it is printed."""
    spread = _spread_of(batch_with(tmp_path, 4, 2, 5, 3), "consequences")

    assert spread.n == 4
    assert spread.sd is None


def test_spread_by_hand(tmp_path):
    """4, 2, 5, 3, 6 — mean 4, sample sd 1.581."""
    spread = _spread_of(batch_with(tmp_path, 4, 2, 5, 3, 6), "consequences")

    assert spread.n == 5
    assert spread.sd == 1.581


def test_an_na_is_counted_apart_and_never_averaged_in(tmp_path):
    """An NA is not a value (4.4): it is excluded from the sd and reported.
    It also costs a repeat — four present values are below the floor."""
    spread = _spread_of(batch_with(tmp_path, 4, None, 5, 3, 6), "consequences")

    assert (spread.n, spread.na) == (4, 1)
    assert spread.sd is None


def test_repeats_of_one_patient_are_not_four_patients(tmp_path):
    """The grouping evaluation.py does not do: 2.4 is within a patient."""
    batch = batch_with(tmp_path, 4, 2, 5)
    consequences = [s for s in batch.spreads if s.dimension == "consequences"]

    assert len(consequences) == 1
    assert consequences[0].patient_id == "TEST-001"


# ── Mean and the overall consistency (2.4) ───


def batch_of(tmp_path, **per_patient):
    """Several patients, each with one repeat per score given."""
    batch = tmp_path / "b"
    for patient_id, scores in per_patient.items():
        for repeat, score in enumerate(scores, start=1):
            write_run(batch, patient_id, repeat, report_body(consequences=([], score)))
    return coverage.read_batch(batch)


def test_the_mean_is_reported_from_one_score_up(tmp_path):
    """Unlike the sd, a mean needs no sample size to mean what it says. Holding
    it back below the floor would leave the map with no centre to read."""
    spread = _spread_of(batch_with(tmp_path, 4, 2, 5, 3), "consequences")

    assert spread.mean == 3.5
    assert spread.sd is None


def test_the_mean_by_hand(tmp_path):
    """4, 2, 5, 3, 6 — mean 4.0, sample sd 1.581."""
    spread = _spread_of(batch_with(tmp_path, 4, 2, 5, 3, 6), "consequences")

    assert spread.mean == 4.0
    assert spread.sd == 1.581


def test_the_overall_consistency_averages_the_per_patient_sds(tmp_path):
    """A: 3,3,3,3,3 → sd 0. B: 1,1,1,1,3 → sd 0.894. The measure is their
    average, 0.447 — one number per patient, then the mean of those."""
    batch = batch_of(tmp_path, A=[3, 3, 3, 3, 3], B=[1, 1, 1, 1, 3])

    assert _spread_of_patient(batch, "A").sd == 0.0
    assert _spread_of_patient(batch, "B").sd == 0.894
    assert batch.mean_within_patient_sd == 0.447


def test_a_gap_between_patients_does_not_inflate_the_within_patient_sd(tmp_path):
    """The distinction 2.4 and 2.5 turn on. Two patients parked at opposite ends
    of the scale, each perfectly steady: consistency is 0, and the distance
    between them belongs to 2.5, which is a different question."""
    batch = batch_of(tmp_path, A=[2, 2, 2, 2, 2], B=[9, 9, 9, 9, 9])

    assert batch.mean_within_patient_sd == 0.0


def test_the_overall_consistency_is_none_when_nothing_reached_the_floor(tmp_path):
    """Four repeats is below MIN_REPEATS, so there is no sd to average and the
    answer is "not enough data", never 0.0."""
    batch = batch_of(tmp_path, A=[3, 3, 3, 3], B=[1, 1, 1, 3])

    assert batch.mean_within_patient_sd is None


def test_the_consistency_is_also_reported_per_dimension(tmp_path):
    """Which dimension the doctor is least steady on is the actionable half."""
    batch = batch_of(tmp_path, A=[1, 1, 1, 1, 3])
    by_dimension = batch.within_patient_sd_by_dimension

    assert by_dimension["consequences"] == 0.894
    assert by_dimension["timeline"] is None        # never scored in this fixture
    assert "causes" not in by_dimension            # never scored at all (4.3)


def _spread_of_patient(batch, patient_id, dimension="consequences"):
    return next(s for s in batch.spreads
                if s.dimension == dimension and s.patient_id == patient_id)


# ── The batch ────────────────────────────────


def test_an_empty_batch_says_what_it_looked_for(tmp_path):
    """The failure that cost a round trip: `nothing to read` with no way to tell
    a wrong path from a wrong layout."""
    batch = tmp_path / "b"
    (batch / "TEST-001-r1").mkdir(parents=True)

    with pytest.raises(SystemExit) as error:
        coverage.read_batch(batch)

    message = str(error.value)
    assert "directory names" in message      # how the index was built
    assert "TEST-001-r1" in message          # and what it actually found


def test_a_missing_report_is_reported_not_raised(tmp_path):
    """Half a consultation is a fact about the batch, not a traceback."""
    batch = tmp_path / "b"
    write_run(batch, "TEST-001", 1, report_body(consequences=([], 8)))
    (batch / "TEST-001-r2").mkdir()
    (batch / "TEST-001-r2" / "transcript.json").write_text(json.dumps({"conversation": []}))

    assert len(coverage.read_batch(batch).consultations) == 1


def test_a_consultation_with_no_report_is_named_not_dropped(tmp_path):
    batch = tmp_path / "b"
    write_run(batch, "TEST-001", 1, report_body(consequences=([], 8)))
    broken = batch / "TEST-001-r2"
    broken.mkdir()
    (broken / "transcript.json").write_text(json.dumps({"conversation": CONVERSATION}))
    (broken / "report.json").write_text(json.dumps({"parsed": False, "report": None}))

    result = coverage.read_batch(batch)

    assert result.unparsed == ["TEST-001-r2"]
    assert len(result.consultations) == 1


def test_the_ungrounded_rate_is_over_the_scores_emitted(tmp_path):
    """NAs are not in the denominator: a dimension nobody scored cannot be an
    unfounded score."""
    line = quote(SHIFT, 1)
    batch = tmp_path / "b"
    write_run(batch, "TEST-001", 1,
              report_body(consequences=([line], 8), identity=([], 6), concern=([line], 4)))

    assert coverage.read_batch(batch).ungrounded_rate == round(1 / 3, 3)


def test_the_batch_reads_without_batch_json(tmp_path):
    """Directory names carry the patient and the repeat, so a batch cut short by
    the queue is still readable."""
    batch = tmp_path / "b"
    write_run(batch, "TEST-001", 1, report_body(consequences=([], 8)))
    write_run(batch, "TEST-002", 3, report_body(consequences=([], 4)))

    result = coverage.read_batch(batch)

    assert sorted((c.patient_id, c.repeat) for c in result.consultations) == [
        ("TEST-001", 1), ("TEST-002", 3)
    ]


def test_a_failed_consultation_is_skipped_even_with_a_transcript(tmp_path):
    """The index is believed about *who* each consultation is and about which
    ones failed. A failed one may have left half a transcript behind."""
    batch = tmp_path / "b"
    write_run(batch, "TEST-001", 1, report_body(consequences=([], 8)))
    write_run(batch, "TEST-001", 2, report_body(consequences=([], 4)))
    (batch / "batch.json").write_text(json.dumps({
        "batch_id": "b",
        "consultations": [
            {"run": "TEST-001-r1", "patient_id": "TEST-001", "repeat": 1, "status": "ok"},
            {"run": "TEST-001-r2", "patient_id": "TEST-001", "repeat": 2, "status": "failed"},
        ],
    }))

    assert len(coverage.read_batch(batch).consultations) == 1


def test_a_resumed_batch_is_read_whole(tmp_path):
    """The bug s52-bps-1 found: run_batch used to rewrite batch.json with only
    the consultations of the latest launch, so a batch of 20 read as 8. What
    exists is decided by the disk; the index only says who each one is."""
    batch = tmp_path / "b"
    for repeat in (1, 2, 3):
        write_run(batch, "TEST-001", repeat, report_body(consequences=([], 8)))

    # An index that only remembers the last launch.
    (batch / "batch.json").write_text(json.dumps({
        "batch_id": "b",
        "consultations": [
            {"run": "TEST-001-r3", "patient_id": "TEST-001", "repeat": 3, "status": "ok"},
        ],
    }))

    result = coverage.read_batch(batch)

    assert len(result.consultations) == 3
    assert sorted(c.repeat for c in result.consultations) == [1, 2, 3]


# ── The invariants (§9) ──────────────────────


def _imports_of(module) -> set:
    source = Path(module.__file__).read_text()
    return {
        node.module
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom) and node.module
    }


def test_coverage_is_post_process_only():
    """Invariant 5: no import of nodes or graph, or it stops running over other
    arms' batches."""
    assert not {"nodes", "graph"} & _imports_of(coverage)


def test_coverage_never_reads_the_ground_truth():
    """Truth-blind by design: `corpus` is the single loader for patients/*.json
    (0.6), so not importing it is the invariant. The map cannot be contaminated
    by knowing the answer, and it stays usable on arms with no profile at all."""
    assert "corpus" not in _imports_of(coverage)
    assert "belief_profile" not in Path(coverage.__file__).read_text()
