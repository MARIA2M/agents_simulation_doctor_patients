# tests/test_notes.py
# working_notes (§4.1): the doctor writes down what it concludes, with the turn
# and never overwriting. Two notes on one dimension are a dated change of mind,
# which is the only thing this arm buys for advancing part of the judgement.

from dataclasses import replace

import pytest

from ahead_agent import nodes, tools

from conftest import in_mode, note, profile, speaks


# ── The argument exists only if the profile asks ──


def test_no_notes_argument_by_default():
    properties = tools.doctor_tools(profile("off"))[0]["function"]["parameters"]["properties"]

    assert "notes" not in properties


def test_the_two_switches_are_independent():
    """Two separate interventions: one value could not say which caused the effect."""
    def properties(mode, notes):
        tool = tools.doctor_tools(profile(mode, notes))[0]
        return tool["function"]["parameters"]["properties"]

    notes_only = properties("off", True)
    assert "notes" in notes_only and "covered" not in notes_only

    coverage_only = properties("show", False)
    assert "covered" in coverage_only and "notes" not in coverage_only

    both = properties("show", True)
    assert "covered" in both and "notes" in both


# That the module constant survives every mode is checked by
# `test_tools.py::test_building_the_tools_never_touches_the_one_the_module_ships`.


# ── Reading what it writes down ──────────────


def test_a_note_is_taken_with_its_dimension():
    reply = speaks("Does it limit you?", notes=[note("consequences", "They have stopped going for walks.")])

    assert tools.declared_notes(reply, nodes.DIMENSIONS) == [
        {"dimension": "consequences", "observation": "They have stopped going for walks."}
    ]


@pytest.mark.parametrize(
    "notes",
    [
        [],
        "consequences",
        [{"dimension": "does_not_exist", "observation": "something"}],
        [{"dimension": "concern"}],
        [{"dimension": "concern", "observation": "   "}],
        ["a loose string"],
    ],
    ids=["empty", "not a list", "unknown dimension", "no observation",
         "blank observation", "item is not an object"],
)
def test_anything_malformed_is_discarded_and_the_call_survives(notes):
    """Nothing it writes down may cost it the tool call."""
    reply = speaks("Does it limit you?", notes=notes)

    assert tools.declared_notes(reply, nodes.DIMENSIONS) == []
    assert tools.hand_off_message(reply) == "Does it limit you?"


# ── Through the loop ─────────────────────────


def test_a_note_carries_the_turn_it_was_taken_in(scripted):
    replies, _ = scripted
    replies["doctor"].append(
        speaks("Does it limit you?", notes=[note("consequences", "They have stopped going for walks.")])
    )

    update = nodes.doctor_node(in_mode("off", notes=True))

    assert update["working_notes"] == [
        {"turn": 1, "dimension": "consequences", "observation": "They have stopped going for walks."}
    ]


def test_a_second_note_on_the_same_dimension_is_added_not_replaced(scripted):
    """Revision is the point: overwriting would erase the only evidence for 1.11."""
    replies, _ = scripted
    replies["doctor"] += [
        speaks("Does it limit you?", notes=[note("consequences", "Says it barely affects them.")]),
        speaks("And the walk?", notes=[note("consequences",
                                           "Earlier they implied it barely affected "
                                           "them, but they have stopped going for walks.")]),
    ]
    replies["patient"].append({"content": "Fine."})

    state = in_mode("off", notes=True)
    state = replace(state, **nodes.doctor_node(state))
    state = replace(state, **nodes.patient_node(state))
    state = replace(state, **nodes.doctor_node(state))

    consequences = [n for n in state.working_notes if n["dimension"] == "consequences"]
    assert len(consequences) == 2
    assert consequences[0]["turn"] == 1 and consequences[1]["turn"] == 2
    assert "but" in consequences[1]["observation"]


def test_nothing_is_recorded_when_the_arm_is_off(scripted):
    """The argument does not exist, so a model sending it anyway stays out of the record."""
    replies, _ = scripted
    replies["doctor"].append(speaks("Does it limit you?", notes=[note("concern", "Worried.")]))

    update = nodes.doctor_node(in_mode("off", notes=False))

    assert update["working_notes"] == []


# ── What does not change ─────────────────────


def test_the_patient_never_sees_the_notes(scripted):
    replies, seen = scripted
    replies["doctor"].append(
        speaks("Does it limit you?", notes=[note("consequences", "They have stopped going for walks.")])
    )
    replies["patient"].append({"content": "Fine."})

    state = in_mode("off", notes=True)
    state = replace(state, **nodes.doctor_node(state))
    nodes.patient_node(state)

    assert "going for walks" not in str(seen["patient"][0])


def test_the_transcript_keeps_only_what_was_said(scripted):
    """Notes belong to the doctor, not the consultation: in the transcript they
    would be lines nobody said, and 3.2 checks quotes against it."""
    replies, _ = scripted
    replies["doctor"].append(
        speaks("Does it limit you?", notes=[note("consequences", "They have stopped going for walks.")])
    )

    update = nodes.doctor_node(in_mode("off", notes=True))

    assert update["conversation"] == [
        {"role": "doctor", "content": "Does it limit you?", "turn": 1}
    ]


# That the doctor still closes when it wants, with notes and without, is
# parametrized by
# `test_coverage_hint.py::test_the_doctor_can_always_close_with_dimensions_open`.
