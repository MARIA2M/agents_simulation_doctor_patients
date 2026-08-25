# tests/test_nodes.py
# The loop, with the LLM replaced by scripted replies. No server involved.

import json
from dataclasses import replace

from ahead_agent import nodes, routing

from conftest import PATIENT, speaks


# ── The doctor drives ────────────────────────


def test_the_doctor_speaks_through_the_tool(scripted, state):
    replies, _ = scripted
    replies["doctor"].append(speaks("How have you been?"))

    update = nodes.doctor_node(state)

    assert update["conversation"][-1] == {
        "role": "doctor",
        "content": "How have you been?",
        "turn": 1,
    }
    assert update["finished"] is False


def test_the_doctor_closes_by_not_calling_the_tool(scripted, state):
    """The whole of 1.5 is this: no tool call, no consultation."""
    replies, _ = scripted
    replies["doctor"].append({"content": "Thank you, that is all I need."})

    update = nodes.doctor_node(state)

    assert update["finished"] is True
    assert update["stop_reason"] == "doctor"
    assert routing.route_after_doctor(replace(state, **update)) == "report"


def test_the_turn_cap_stops_the_loop_and_says_so(scripted, state):
    """Reaching the cap is an incident, not a decision — it must be tellable apart."""
    replies, _ = scripted
    replies["doctor"].append(speaks("And how is the fatigue?"))
    state.turn_count = state.config["limits"]["max_turns"] - 1

    update = nodes.doctor_node(state)

    assert update["finished"] is True
    assert update["stop_reason"] == "turn_cap"
    assert update["events"][-1]["event"] == "turn_cap"


def test_a_broken_call_is_recorded_and_never_looks_like_a_decision(scripted, state):
    replies, _ = scripted
    replies["doctor"].append({"content": "", "tool_calls": [{"function": {"name": "wrong"}}]})

    update = nodes.doctor_node(state)

    assert update["stop_reason"] == "malformed_call"
    assert update["events"][-1]["event"] == "malformed_tool_call"


# ── The patient answers ──────────────────────


def test_the_patient_answer_comes_back_as_the_tool_result(scripted, state):
    replies, _ = scripted
    replies["doctor"].append(speaks("How have you been?"))
    replies["patient"].append({"content": "Tired, mostly."})

    state = replace(state, **nodes.doctor_node(state))
    update = nodes.patient_node(state)

    assert update["doctor_messages"][-1] == {
        "role": "tool",
        "name": "hand_off_to_patient",
        "content": "Tired, mostly.",
    }
    assert update["conversation"][-1]["role"] == "patient"


# ── Isolation (§3.1) ─────────────────────────


def test_the_patient_profile_never_reaches_the_doctor(scripted, state):
    """Not a comment, a test: the doctor must infer, not read the answers."""
    replies, seen = scripted
    replies["doctor"].extend([speaks("How have you been?"), speaks("And your mood?")])
    replies["patient"].append({"content": "Tired, mostly."})

    state = replace(state, **nodes.doctor_node(state))
    state = replace(state, **nodes.patient_node(state))
    nodes.doctor_node(state)

    doctor_context = json.dumps(seen["doctor"])
    for score in PATIENT["belief_profile"]["b_ipq"].values():
        if isinstance(score, (int, float)):
            assert f'"{score}"' not in doctor_context
    for banned in ("belief_profile", "b_ipq", "bmq", "Genetics / family history"):
        assert banned not in doctor_context


def test_the_patient_is_told_who_they_are(scripted, state):
    """The same profile the doctor must not see is what the patient plays."""
    replies, seen = scripted
    replies["doctor"].append(speaks("How have you been?"))
    replies["patient"].append({"content": "Tired, mostly."})

    state = replace(state, **nodes.doctor_node(state))
    nodes.patient_node(state)

    system = seen["patient"][0][0]["content"]
    assert "58-year-old male" in system
    assert "Genetics / family history" in system
