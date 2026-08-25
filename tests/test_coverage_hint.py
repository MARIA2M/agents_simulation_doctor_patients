# tests/test_coverage_hint.py
# coverage_hint (§4.1): the doctor's own bookkeeping, declared through the tool
# it already calls and read back to it with the patient's reply.

from dataclasses import replace

import pytest

from ahead_agent import nodes, tools

from conftest import in_mode, profile, speaks


# ── The three arms (§4.1) ────────────────────


def test_off_never_asks_the_doctor_anything():
    """The clean baseline: coverage is reconstructed afterwards by 3.2."""
    properties = tools.doctor_tools(profile("off"))[0]["function"]["parameters"]["properties"]

    assert "covered" not in properties


def test_show_asks_and_promises_what_comes_back():
    tool = tools.doctor_tools(profile("show"))[0]
    covered = tool["function"]["parameters"]["properties"]["covered"]

    assert "comes back" in covered["description"]


# The module constant is untouched in every mode: `test_tools.py`, next to the
# rest of what `doctor_tools` does.


# ── Reading what the doctor declared ─────────


def test_the_dimensions_it_names_are_taken():
    reply = speaks("How is work?", covered=["consequences", "identity"])

    assert tools.declared_covered(reply, nodes.DIMENSIONS) == ["consequences", "identity"]


@pytest.mark.parametrize(
    "arguments",
    [{}, {"covered": "consequences"}, {"covered": None}, {"covered": ["not_a_dimension"]}],
    ids=["absent", "a string", "null", "unknown name"],
)
def test_anything_it_does_not_declare_properly_is_simply_no_news(arguments):
    """Optional and forgiving: nothing about coverage may cost a tool call."""
    assert tools.declared_covered(speaks("Hello", **arguments), nodes.DIMENSIONS) == []


def test_a_reply_with_no_call_declares_nothing():
    assert tools.declared_covered({"content": "I have what I need."}, nodes.DIMENSIONS) == []


# ── Handing it back ──────────────────────────


# That the patient's channel carries only the patient is checked by
# `test_tools.py::test_the_patient_reply_goes_back_as_the_tool_result`.


def test_the_note_is_a_separate_message_in_our_own_voice():
    note = tools.coverage_note(["causes", "general_harm"])

    assert note["role"] == "user"          # the OPENING channel, not the patient's
    assert note["content"] == "Not yet explored: causes, general_harm."


def test_there_is_no_note_when_nothing_is_open():
    assert tools.coverage_note([]) is None
    assert tools.coverage_note(None) is None


# ── Through the loop ─────────────────────────


def test_the_map_accumulates_across_turns(scripted):
    replies, _ = scripted
    replies["doctor"] += [speaks("How is work?", covered=["consequences"]),
                          speaks("And the tablets?", covered=["specific_necessity"])]
    replies["patient"] += [{"content": "Fine."}, {"content": "I take them."}]

    state = in_mode("show")
    for _ in range(2):
        state = replace(state, **nodes.doctor_node(state))
        state = replace(state, **nodes.patient_node(state))

    assert state.coverage_hint == {"consequences": "covered",
                                   "specific_necessity": "covered"}


def test_show_hands_back_what_is_still_open(scripted):
    replies, _ = scripted
    replies["doctor"].append(speaks("How is work?", covered=["consequences"]))
    replies["patient"].append({"content": "Fine."})

    state = in_mode("show")
    state = replace(state, **nodes.doctor_node(state))
    update = nodes.patient_node(state)

    patient_turn, note = update["doctor_messages"][-2:]

    assert patient_turn == {"role": "tool", "name": "hand_off_to_patient", "content": "Fine."}
    assert note["role"] == "user"
    assert "consequences" not in note["content"]
    assert "general_overuse" in note["content"]


def test_the_patient_never_sees_the_coverage_note(scripted):
    """It is the doctor's bookkeeping. In the patient's context it would be a
    list of what to talk about next."""
    replies, seen = scripted
    replies["doctor"].append(speaks("How is work?", covered=["consequences"]))
    replies["patient"].append({"content": "Fine."})

    state = in_mode("show")
    state = replace(state, **nodes.doctor_node(state))
    nodes.patient_node(state)

    assert not any("Not yet explored" in str(message) for message in seen["patient"][0])


# ── The invariant ────────────────────────────


@pytest.mark.parametrize(
    ("mode", "notes"),
    [("off", False), ("off", True), ("show", False), ("show", True)],
    ids=["baseline", "notes only", "coverage only", "both"],
)
def test_the_doctor_can_always_close_with_dimensions_open(scripted, mode, notes):
    """No mode makes it cover anything. A dimension left untouched is a result,
    and forcing another turn would put the questionnaire back in charge of when
    the consultation ends (1.5)."""
    replies, _ = scripted
    replies["doctor"].append({"content": "I have what I need."})

    update = nodes.doctor_node(in_mode(mode, notes))

    assert update["finished"] is True
    assert update["stop_reason"] == "doctor"


def test_off_hands_back_nothing_at_all():
    assert nodes._outstanding(profile("off"), {}) == []
    assert nodes._outstanding(profile("show"), {}) == nodes.DIMENSIONS
