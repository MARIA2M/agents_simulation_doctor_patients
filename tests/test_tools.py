# tests/test_tools.py
# Reading the doctor's tool call: what it said, or that it chose to stop.

import pytest

from ahead_agent import tools

from conftest import profile


def call(**function):
    return {"content": "", "tool_calls": [{"function": function}]}


def test_arguments_as_an_object():
    reply = call(name="hand_off_to_patient", arguments={"message": "How have you been?"})
    assert tools.hand_off_message(reply) == "How have you been?"


def test_arguments_as_a_json_string():
    """Ollama sends either shape depending on the model."""
    reply = call(name="hand_off_to_patient", arguments='{"message": "And the treatment?"}')
    assert tools.hand_off_message(reply) == "And the treatment?"


def test_no_tool_call_means_the_doctor_closed_the_consultation():
    """This is the only way a consultation ends by decision (1.5)."""
    assert tools.hand_off_message({"content": "I have what I need."}) is None
    assert tools.hand_off_message({"content": "", "tool_calls": []}) is None


# ── Broken calls are not decisions ───────────


@pytest.mark.parametrize(
    "function",
    [
        {"name": "ask_the_patient", "arguments": {"message": "hello"}},
        {"name": "hand_off_to_patient", "arguments": "{not json"},
        {"name": "hand_off_to_patient", "arguments": {}},
        {"name": "hand_off_to_patient", "arguments": {"message": "   "}},
    ],
    ids=["wrong tool", "bad json", "no message", "blank message"],
)
def test_a_broken_call_raises_rather_than_ending_the_consultation(function):
    """Ending here would look like a decision the doctor never made."""
    with pytest.raises(tools.MalformedToolCall):
        tools.hand_off_message(call(**function))


def test_the_patient_reply_goes_back_as_the_tool_result():
    """The patient's channel carries only the patient.

    In a tool result the doctor cannot tell our words from theirs, and
    `Evidence.quote` has to be a literal line of the patient's — which is why
    the `coverage_hint: show` reminder travels apart, as `role: user` (§4.1).
    """
    assert tools.tool_result("Not great, honestly.") == {
        "role": "tool",
        "name": "hand_off_to_patient",
        "content": "Not great, honestly.",
    }


# ── Building the tools for a run ─────────────


@pytest.mark.parametrize(
    ("mode", "notes"),
    [("off", False), ("off", True), ("show", False), ("show", True)],
    ids=["baseline", "notes only", "coverage only", "both"],
)
def test_building_the_tools_never_touches_the_one_the_module_ships(mode, notes):
    """`doctor_tools` copies before adding arguments. Mutating the constant would
    leave the first arm contaminating the next inside one process — and a batch
    runs the arms in one process."""
    tools.doctor_tools(profile(mode, notes))

    properties = tools.HAND_OFF_TO_PATIENT["function"]["parameters"]["properties"]
    assert "covered" not in properties
    assert "notes" not in properties
