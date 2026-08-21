# tests/test_coverage.py
# coverage_hint (§4.1): the doctor's own bookkeeping, declared through the tool
# it already calls and read back to it with the patient's reply.

from dataclasses import replace

import pytest

from ahead_agent import nodes, tools
from ahead_agent.config import load_config
from ahead_agent.state import State

from test_nodes import PATIENT, scripted, state  # noqa: F401


def speaks(message, **arguments):
    return {
        "content": "",
        "tool_calls": [
            {"function": {"name": "hand_off_to_patient",
                          "arguments": {"message": message, **arguments}}}
        ],
    }


def profile(mode):
    config = load_config("local")
    config["features"] = {"coverage_hint": mode}
    return config


def in_mode(mode):
    return State(profile(mode), PATIENT)


# ── The three arms (§4.1) ────────────────────


def test_off_never_asks_the_doctor_anything():
    """The clean baseline: coverage is reconstructed afterwards by 3.2."""
    properties = tools.doctor_tools(profile("off"))[0]["function"]["parameters"]["properties"]

    assert "covered" not in properties


@pytest.mark.parametrize("mode", ["declare", "show"])
def test_declare_and_show_both_ask(mode):
    properties = tools.doctor_tools(profile(mode))[0]["function"]["parameters"]["properties"]

    assert "covered" in properties


def test_only_show_promises_anything_back():
    """A promise the mode does not keep would be a lie in the prompt."""
    def described(mode):
        tool = tools.doctor_tools(profile(mode))[0]
        return tool["function"]["parameters"]["properties"]["covered"]["description"]

    assert "comes back" not in described("declare")
    assert "comes back" in described("show")


def test_asking_the_doctor_does_not_disturb_the_tool_it_already_had():
    """doctor_tools copies; the module constant must survive every mode."""
    tools.doctor_tools(profile("show"))

    assert "covered" not in tools.HAND_OFF_TO_PATIENT["function"]["parameters"]["properties"]


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


def test_what_is_still_open_rides_back_with_the_answer():
    result = tools.tool_result("Tired, mostly.", ["causes", "general_harm"])

    assert result["content"] == "Tired, mostly.\n\n[not yet explored: causes, general_harm]"


def test_nothing_is_appended_once_there_is_nothing_left():
    assert tools.tool_result("Tired, mostly.", [])["content"] == "Tired, mostly."
    assert tools.tool_result("Tired, mostly.")["content"] == "Tired, mostly."


# ── Through the loop ─────────────────────────


@pytest.mark.parametrize("mode", ["declare", "show"])
def test_the_map_accumulates_across_turns(scripted, mode):
    replies, _ = scripted
    replies["doctor"] += [speaks("How is work?", covered=["consequences"]),
                          speaks("And the tablets?", covered=["specific_necessity"])]
    replies["patient"] += [{"content": "Fine."}, {"content": "I take them."}]

    state = in_mode(mode)
    for _ in range(2):
        state = replace(state, **nodes.doctor_node(state))
        state = replace(state, **nodes.patient_node(state))

    assert state.coverage_hint == {"consequences": "cubierto",
                                   "specific_necessity": "cubierto"}


def test_declare_records_the_map_and_tells_the_doctor_nothing(scripted):
    """The point of the arm: what it believed it covered, uncontaminated by
    being told the answer first."""
    replies, _ = scripted
    replies["doctor"].append(speaks("How is work?", covered=["consequences"]))
    replies["patient"].append({"content": "Fine."})

    state = replace(in_mode("declare"), **{})
    state = replace(state, **nodes.doctor_node(state))
    update = nodes.patient_node(state)

    assert state.coverage_hint == {"consequences": "cubierto"}
    assert update["doctor_messages"][-1]["content"] == "Fine."


def test_show_hands_back_what_is_still_open(scripted):
    replies, _ = scripted
    replies["doctor"].append(speaks("How is work?", covered=["consequences"]))
    replies["patient"].append({"content": "Fine."})

    state = in_mode("show")
    state = replace(state, **nodes.doctor_node(state))
    update = nodes.patient_node(state)

    handed_back = update["doctor_messages"][-1]["content"]
    assert "not yet explored" in handed_back
    assert "consequences" not in handed_back
    assert "general_overuse" in handed_back


def test_the_patient_never_sees_the_coverage_note(scripted):
    """It is the doctor's bookkeeping. In the patient's context it would be a
    list of what to talk about next."""
    replies, seen = scripted
    replies["doctor"].append(speaks("How is work?", covered=["consequences"]))
    replies["patient"].append({"content": "Fine."})

    state = in_mode("show")
    state = replace(state, **nodes.doctor_node(state))
    nodes.patient_node(state)

    assert not any("not yet explored" in str(message) for message in seen["patient"][0])


# ── The invariant ────────────────────────────


@pytest.mark.parametrize("mode", ["off", "declare", "show"])
def test_the_doctor_can_always_close_with_dimensions_open(scripted, mode):
    """No mode makes it cover anything. A dimension left untouched is a result,
    and forcing another turn would put the questionnaire back in charge of when
    the consultation ends (1.5)."""
    replies, _ = scripted
    replies["doctor"].append({"content": "I have what I need."})

    update = nodes.doctor_node(in_mode(mode))

    assert update["finished"] is True
    assert update["stop_reason"] == "doctor"


def test_off_hands_back_nothing_at_all():
    assert nodes._outstanding(profile("off"), {}) == []
    assert nodes._outstanding(profile("declare"), {}) == []
    assert nodes._outstanding(profile("show"), {}) == nodes.DIMENSIONS
