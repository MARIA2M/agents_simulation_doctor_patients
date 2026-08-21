# tests/test_nodes.py
# The loop, with the LLM replaced by scripted replies. No server involved.

import json
from dataclasses import replace

import pytest

from ahead_agent import llm, nodes, routing
from ahead_agent.config import load_config
from ahead_agent.state import State

PATIENT = {
    "patient_id": "TEST-001",
    "disease_profile": {
        "diagnosis": "Chronic Lymphocytic Leukemia (CLL)",
        "treatment_regimen": "Watch and wait",
        "key_symptoms": ["Mild fatigue"],
        "trajectory": "Slow-progressing",
        "demographics": {"age": 58, "gender": "male"},
    },
    "belief_profile": {
        "b_ipq": {
            "consequences": 7,
            "timeline": 9,
            "personal_control": 3,
            "treatment_control": 6,
            "identity": 5,
            "concern": 8,
            "coherence": 4,
            "emotional_response": 8,
            "causes": ["Genetics / family history"],
        },
        "bmq": {"specific_necessity": 3.4},
    },
}


def speaks(message):
    return {
        "content": "",
        "tool_calls": [
            {"function": {"name": "hand_off_to_patient", "arguments": {"message": message}}}
        ],
    }


@pytest.fixture
def scripted(monkeypatch):
    """Queue replies per role, and record every message sent to each model."""
    replies = {"doctor": [], "patient": [], "report": []}
    seen = {"doctor": [], "patient": [], "report": []}

    def fake_chat(config, role, messages, tools=None, events=None, usage=None):
        seen[role].append(messages)
        if usage is not None:
            usage.append({"role": role, "prompt_tokens": 100, "eval_tokens": 20})
        return replies[role].pop(0)

    monkeypatch.setattr(nodes.llm, "chat", fake_chat)
    return replies, seen


@pytest.fixture
def state():
    return State(load_config("local"), PATIENT)


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

    handed_back = update["doctor_messages"][-1]
    assert handed_back["role"] == "tool"
    assert handed_back["name"] == "hand_off_to_patient"
    # The answer, then the coverage note of §4.1 — see test_coverage.py.
    assert handed_back["content"].startswith("Tired, mostly.")
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
