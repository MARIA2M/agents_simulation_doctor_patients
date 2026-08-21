# tests/test_report.py
# The report: the schema, who writes it, and the single exit the loop takes to
# reach it (1.13).

import json
import os
from dataclasses import fields

import pytest

from ahead_agent import nodes, report, routing
from ahead_agent.config import BIPQ_DIMENSIONS, BMQ_SUBSCALES, load_config
from ahead_agent.state import State

from test_nodes import PATIENT, scripted, speaks, state  # noqa: F401


# ── The schema is the specification (2.1) ────


def test_evidence_comes_before_the_score():
    """A number written after its evidence is a number the evidence leads to."""
    names = [f.name for f in fields(report.DimensionScore)]

    assert names.index("evidence") < names.index("reasoning") < names.index("score")


def test_a_score_can_be_absent():
    """NA is a value, never a default (4.4). Ruby's scorer wrote 5 instead."""
    na = report.DimensionScore(
        dimension="coherence", evidence=[], reasoning="never asked", score=None, confidence=0.0
    )

    assert na.score is None


def test_the_transcript_is_numbered_so_evidence_can_point_at_a_turn():
    text = report.transcript_text(
        [
            {"role": "doctor", "content": "How have you been?", "turn": 1},
            {"role": "patient", "content": "Tired.", "turn": 1},
        ]
    )

    assert "[turn 1] Doctor: How have you been?" in text
    assert "[turn 1] Patient: Tired." in text


# ── Reading what came back ───────────────────

GOOD = {
    "clinical_summary": "Stable on watch and wait.",
    "bipq": {
        "consequences": {
            "evidence": [{"quote": "I manage fine", "turn": 3}],
            "reasoning": "Keeps every role.",
            "score": 2,
            "confidence": 0.8,
        }
    },
    "bmq": {"specific_necessity": {"evidence": [], "reasoning": "not asked",
                                   "score": None, "confidence": 0.0}},
    "causes": ["genetics"],
    "causes_evidence": [{"quote": "my father had it", "turn": 9}],
}


def test_a_fenced_object_parses():
    """GLM fences it despite REPORT.md asking it not to. Measured, not assumed."""
    raw = "```json\n" + json.dumps(GOOD) + "\n```"

    assert report.parse(raw, "CLL-003") is not None


def test_a_bare_object_parses():
    assert report.parse(json.dumps(GOOD), "CLL-003") is not None


@pytest.mark.parametrize(
    "raw", ["", None, "I could not complete the report.", "[1, 2, 3]", "{not json"],
    ids=["empty", "none", "prose", "array", "broken"],
)
def test_anything_that_is_not_an_object_is_no_report(raw):
    """None, so the retry fires. An empty Report would look like a finished one."""
    assert report.parse(raw, "CLL-003") is None


def test_every_dimension_is_present_even_when_the_doctor_skipped_it():
    """A missing dimension is a hole in the coverage map, not an absent key."""
    parsed = report.parse(json.dumps(GOOD), "CLL-003")

    assert len(parsed.bipq) == 8 and len(parsed.bmq) == 4
    assert parsed.bipq["coherence"].score is None
    assert parsed.bipq["coherence"].evidence == []


@pytest.mark.parametrize("score", [11, -1, "eight", True, None])
def test_a_score_off_the_scale_is_na_and_never_clamped(score):
    """The old arm did min/max, turning an illegal value into a legal-looking
    one that then counted as a hit (P1)."""
    data = json.dumps({"bipq": {"consequences": {"score": score, "reasoning": "", "evidence": []}}})

    assert report.parse(data, "X").bipq["consequences"].score is None


def test_the_two_scales_are_judged_separately():
    """5.5 is a legal B-IPQ score and an illegal BMQ one. The same number can
    be an answer on one scale and a mistake on the other."""
    data = json.dumps(
        {
            "bipq": {"consequences": {"score": 5.5, "reasoning": "r", "evidence": []}},
            "bmq": {"general_harm": {"score": 5.5, "reasoning": "r", "evidence": []}},
        }
    )
    parsed = report.parse(data, "X")

    assert parsed.bipq["consequences"].score == 5.5
    assert parsed.bmq["general_harm"].score is None


def test_a_score_inside_the_scale_survives():
    data = json.dumps({"bmq": {"general_harm": {"score": 4.5, "reasoning": "", "evidence": []}}})

    assert report.parse(data, "X").bmq["general_harm"].score == 4.5


def test_confidence_outside_zero_to_one_is_pulled_back():
    data = json.dumps({"bipq": {"concern": {"score": 4, "confidence": 7, "evidence": []}}})

    assert report.parse(data, "X").bipq["concern"].confidence == 1.0


def test_evidence_without_a_usable_turn_is_kept_and_marked():
    """The quote is still checkable at stage 6; only the pointer is missing."""
    data = json.dumps(
        {"bipq": {"identity": {"evidence": [{"quote": "the tiredness"}], "score": 4}}}
    )

    evidence = report.parse(data, "X").bipq["identity"].evidence
    assert evidence[0].quote == "the tiredness" and evidence[0].turn == -1


# ── What counts as unfinished (1.13) ─────────


def _scored(**dimensions):
    return json.dumps({"bipq": dimensions, "bmq": {}})


def test_a_declared_na_is_an_answer_and_not_a_gap():
    """It said it did not explore it. Asking again is how it invents one."""
    parsed = report.parse(
        _scored(coherence={"score": None, "reasoning": "never came up", "evidence": []}),
        "X",
    )

    assert "coherence" not in report.gaps(parsed)


def test_a_dimension_it_never_mentioned_is_a_gap():
    """The parser filled it in, so there is no reasoning: that is silence."""
    parsed = report.parse(_scored(), "X")

    assert "coherence" in report.gaps(parsed)


def test_a_report_that_would_not_parse_is_all_gaps():
    assert len(report.gaps(None)) == 12


def test_an_empty_causes_list_is_never_a_gap():
    """Demanding causes is what produces an invented one (N3). It stays out."""
    parsed = report.parse(json.dumps({"causes": [], "causes_evidence": []}), "X")

    assert "causes" not in report.gaps(parsed)


def test_a_cause_with_nothing_behind_it_is_dropped():
    parsed = report.parse(
        json.dumps({"causes": ["stress at work"], "causes_evidence": []}), "X"
    )

    assert parsed.causes == []


def test_a_cause_with_evidence_survives():
    parsed = report.parse(
        json.dumps(
            {"causes": ["genetics"], "causes_evidence": [{"quote": "my father", "turn": 4}]}
        ),
        "X",
    )

    assert parsed.causes == ["genetics"]


def test_the_retry_names_what_is_missing_and_allows_a_null():
    note = report.retry_note(["coherence", "general_harm"])

    assert "coherence, general_harm" in note
    assert "null" in note


# ── Giving up rather than looping ────────────


def _with_report(raw, attempts):
    return State(
        load_config("local"), PATIENT, report=report.parse(raw, "X"), report_attempts=attempts
    )


def _complete_report():
    """Every dimension accounted for, so nothing sends it back (1.13)."""
    return json.dumps(
        {
            "bipq": {n: {"score": 4, "reasoning": "said so", "evidence": []}
                     for n in BIPQ_DIMENSIONS},
            "bmq": {n: {"score": 3, "reasoning": "said so", "evidence": []}
                    for n in BMQ_SUBSCALES},
        }
    )


def test_a_complete_report_ends_it():
    assert routing.route_after_report(_with_report(_complete_report(), 1)) == "end"


def test_gaps_send_it_back_while_attempts_remain():
    assert routing.route_after_report(_with_report(_scored(), 1)) == "report"
    assert routing.route_after_report(_with_report(_scored(), 2)) == "report"


def test_it_gives_up_after_the_configured_retries():
    """What is still missing stays NA. An endless retry is only an endless bill."""
    exhausted = _with_report(_scored(), 3)   # report_retries: 2, so 3 attempts

    assert routing.route_after_report(exhausted) == "end"
    assert exhausted.report.bipq["coherence"].score is None


# ── The loop has one exit and it is the report ──


@pytest.mark.parametrize("stop_reason", ["doctor", "turn_cap", "malformed_call"])
def test_every_way_of_finishing_routes_to_the_report(stop_reason):
    """It runs whatever ended the consultation, not only a clean close (1.13)."""
    finished = State(load_config("local"), PATIENT, finished=True, stop_reason=stop_reason)

    assert routing.route_after_doctor(finished) == "report"


def test_an_unfinished_turn_still_goes_to_the_patient():
    assert routing.route_after_doctor(State(load_config("local"), PATIENT)) == "patient"


# ── Who writes it ────────────────────────────


@pytest.fixture
def consulted():
    """A state as it looks when the doctor has just closed the consultation."""
    return State(
        load_config("local"),
        PATIENT,
        conversation=[{"role": "doctor", "content": "How have you been?", "turn": 1}],
        doctor_messages=[
            {"role": "system", "content": "I am the doctor"},
            {"role": "assistant", "content": "what I already worked out"},
        ],
    )


def test_the_doctor_writes_its_own_report(scripted, consulted):
    """Continuing the consultation it had, not reading a transcript cold (§4).

    A fresh model on the transcript is the artifact arm of 5.4: it would score
    just as well and measure something else entirely.
    """
    replies, seen = scripted
    replies["report"].append({"content": "{}"})

    nodes.report_node(consulted)

    history = seen["report"][0]
    assert history[0]["content"] == "I am the doctor"
    assert history[1]["content"] == "what I already worked out"


def test_the_transcript_travels_so_evidence_can_cite_a_turn(scripted, consulted):
    """The doctor remembers the conversation but never saw turn numbers."""
    replies, seen = scripted
    replies["report"].append({"content": "{}"})

    nodes.report_node(consulted)

    assert "[turn 1] Doctor: How have you been?" in seen["report"][0][-1]["content"]


def test_the_report_is_asked_for_without_tools(monkeypatch, consulted):
    """There is nothing left to ask, only to write."""
    seen = {}

    def fake_chat(config, role, messages, tools=None, events=None, usage=None):
        seen["tools"] = tools
        return {"content": "{}"}

    monkeypatch.setattr(nodes.llm, "chat", fake_chat)
    nodes.report_node(consulted)

    assert seen["tools"] is None


def test_the_raw_text_is_kept_and_the_attempt_counted(scripted, consulted):
    """Kept so a report that will not parse is still readable by hand."""
    replies, seen = scripted
    replies["report"].append({"content": '  {"clinical_summary": "stable"}  '})

    result = nodes.report_node(consulted)

    assert result["report_raw"] == '{"clinical_summary": "stable"}'
    assert result["report_attempts"] == 1


# ── End to end ───────────────────────────────
# Skipped by default: building the graph imports langgraph, which takes about
# three minutes off GPFS. Run with AHEAD_GRAPH_TESTS=1.


@pytest.mark.skipif(
    os.getenv("AHEAD_GRAPH_TESTS") != "1", reason="imports langgraph (~3 min off GPFS)"
)
def test_a_consultation_ends_in_the_report(scripted, state):
    from ahead_agent.graph import build_graph

    replies, seen = scripted
    replies["doctor"] += [speaks("How have you been?"), {"content": "I have what I need."}]
    replies["patient"].append({"content": "Tired, mostly."})
    replies["report"].append({"content": _complete_report()})

    final = State(**build_graph(state.config).invoke(state))

    assert final.stop_reason == "doctor"
    assert final.report_attempts == 1
    assert final.report.bipq["coherence"].score == 4.0


@pytest.mark.skipif(
    os.getenv("AHEAD_GRAPH_TESTS") != "1", reason="imports langgraph (~3 min off GPFS)"
)
def test_a_thin_report_is_asked_for_again_and_then_given_up_on(scripted, state):
    """A summary and nothing else accounts for no dimension, so all 12 are gaps.

    The retry has never fired in a live run (N8), so this is the only place the
    whole path is exercised: it goes back, it is told what is missing, and what
    is still missing when the attempts run out stays NA rather than looping (4.4).
    """
    from ahead_agent.graph import build_graph

    replies, seen = scripted
    replies["doctor"] += [speaks("How have you been?"), {"content": "I have what I need."}]
    replies["patient"].append({"content": "Tired, mostly."})
    replies["report"] += [{"content": '{"clinical_summary": "stable"}'}] * 3

    final = State(**build_graph(state.config).invoke(state))

    assert final.report_attempts == 3     # report_retries: 2, so three asks
    assert all(scored.score is None for scored in final.report.bipq.values())
    assert [event["event"] for event in final.events].count("report_gaps") == 3

    # What the last one left out goes at the end, where it is the most recent
    # thing said — the second ask is where that first shows up.
    assert "did not account for" in seen["report"][1][-1]["content"]


# ── What is left on disk ─────────────────────


def test_text_that_would_not_parse_is_the_only_record_so_it_is_kept(tmp_path):
    written = State(load_config("local"), PATIENT, report_raw="not json at all")

    path = report.write_report(written, tmp_path)
    saved = json.loads(path.read_text())

    assert saved["patient_id"] == "TEST-001"
    assert saved["parsed"] is False and saved["report"] is None
    assert (tmp_path / "report_raw.txt").read_text().strip() == "not json at all"


def test_a_parsed_report_is_written_as_a_document_and_nothing_else(tmp_path):
    """Once it has parsed, the raw text says the same thing twice."""
    parsed = report.parse(json.dumps(GOOD), "TEST-001")
    written = State(load_config("local"), PATIENT, report=parsed, report_raw=json.dumps(GOOD))

    saved = json.loads(report.write_report(written, tmp_path).read_text())

    assert saved["parsed"] is True
    assert saved["report"]["bipq"]["consequences"]["score"] == 2.0
    assert saved["report"]["bipq"]["consequences"]["evidence"][0]["turn"] == 3
    assert not (tmp_path / "report_raw.txt").exists()
