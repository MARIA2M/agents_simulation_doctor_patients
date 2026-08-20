# ahead_agent/nodes.py
# The two nodes of the loop: the doctor, and the patient it calls as a tool.

from __future__ import annotations

from typing import Any, Dict, List

from . import llm, patient_profile, prompts, tools
from .state import State

OPENING = "Begin the consultation."


def doctor_node(state: State) -> Dict[str, Any]:
    """One doctor turn: it speaks through the tool, or it stops (1.5)."""
    config = state.config
    events = list(state.events)
    usage = list(state.usage)
    messages = state.doctor_messages or [
        {"role": "system", "content": prompts.compose(config, "doctor")},
        {"role": "user", "content": OPENING},
    ]

    reply = llm.chat(
        config, "doctor", messages, tools=tools.DOCTOR_TOOLS, events=events, usage=usage
    )
    messages = messages + [reply]

    turn = state.turn_count
    conversation = state.conversation
    stop_reason = "doctor"

    try:
        said = tools.hand_off_message(reply)
    except tools.MalformedToolCall as error:
        events.append({"event": "malformed_tool_call", "detail": str(error)})
        said = None
        stop_reason = "malformed_call"

    if said is not None:
        print(f"\n🩺  Doctor  : {said}")
        turn += 1
        conversation = conversation + [{"role": "doctor", "content": said, "turn": turn}]
        # A safety net, not a criterion: reaching it is recorded as an incident
        # so a capped consultation is never mistaken for one the doctor closed.
        at_cap = turn >= config["limits"]["max_turns"]
        stop_reason = "turn_cap" if at_cap else None
        if at_cap:
            events.append({"event": "turn_cap", "turns": turn})

    return {
        "doctor_messages": messages,
        "conversation": conversation,
        "turn_count": turn,
        "events": events,
        "usage": usage,
        "finished": stop_reason is not None,
        "stop_reason": stop_reason,
    }


def patient_node(state: State) -> Dict[str, Any]:
    """The tool call itself: the patient answers what the doctor just said."""
    config = state.config
    events = list(state.events)
    usage = list(state.usage)
    question = state.conversation[-1]["content"]

    messages = state.patient_messages or [
        {"role": "system", "content": _patient_system(config, state.patient)}
    ]
    messages = messages + [{"role": "user", "content": question}]

    reply = llm.chat(config, "patient", messages, events=events, usage=usage)
    answer = (reply.get("content") or "").strip()
    print(f"🧑  Patient : {answer}")

    return {
        "patient_messages": messages + [reply],
        # The doctor gets the answer as the result of its call, and nothing
        # else: this is where the isolation of §3.1 is either kept or broken.
        "doctor_messages": state.doctor_messages + [tools.tool_result(answer)],
        "conversation": state.conversation
        + [{"role": "patient", "content": answer, "turn": state.turn_count}],
        "events": events,
        "usage": usage,
    }


def _patient_system(config: Dict[str, Any], patient: Dict[str, Any]) -> str:
    return prompts.compose(config, "patient") + prompts.SEPARATOR + patient_profile.describe(patient)
