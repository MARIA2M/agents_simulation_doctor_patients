# ahead_agent/nodes.py
# ─────────────────────────────────────────────
# One function per graph node. Each takes State → returns the channels it changed.
#
#                 ┌──────────────────────────────┐
#                 ▼                              │
#  START ──► doctor ──(speaks)──► patient ───────┘
#                 │
#                 └──(stops)──► report ──► END
# ─────────────────────────────────────────────

from __future__ import annotations

from typing import Any, Dict

from . import llm, patient_profile, prompts, report, tools
from .config import (
    BIPQ_DIMENSIONS,
    BMQ_SUBSCALES,
    CAUSES_DIMENSION,
    coverage_mode,
    takes_notes,
)
from .state import State

# what coverage is measured against; causes is reported but not scored
DIMENSIONS = list(BIPQ_DIMENSIONS) + list(BMQ_SUBSCALES) + [CAUSES_DIMENSION]

# how the doctor is told to reach the patient (Scout's `doctor.user`)
OPENING = (
    f"Converse with the patient using the {tools.TOOL_NAME} tool to ask a question. "
    "Go back and forth this way like in a real session."
)


# ── Doctor ───────────────────────────────────


# 1.5
def doctor_node(state: State) -> Dict[str, Any]:
    """One doctor turn: it speaks through the tool, or it stops."""
    config = state.config
    events = list(state.events)
    usage = list(state.usage)

    # ── What it is sent ──
    # the first turn builds the context; after that the state carries it
    messages = state.doctor_messages or [
        {"role": "system", "content": prompts.compose_prompt(config, "doctor")},
        {"role": "user", "content": OPENING},
    ]

    reply = llm.chat(
        config, "doctor", messages, tools=tools.doctor_tools(config), events=events, usage=usage
    )
    messages = messages + [reply]

    # ── What it did: spoke, stopped, or broke ──
    try:
        said = tools.hand_off_message(reply)   # None = it stopped calling the tool
    except tools.MalformedToolCall as error:
        events.append({"event": "malformed_tool_call", "detail": str(error)})
        said, stop_reason = None, "malformed_call"
    else:
        stop_reason = "doctor" if said is None else None

    # ── It stopped: nothing said, so there is no turn to record ──
    if said is None:
        return {
            "doctor_messages": messages,
            "events": events,
            "usage": usage,
            "finished": True,
            "stop_reason": stop_reason,
        }

    # ── It spoke: record the turn ──
    print(f"\n🩺  Doctor  : {said}")
    turn = state.turn_count + 1
    conversation = state.conversation + [{"role": "doctor", "content": said, "turn": turn}]

    # §4.1
    coverage = dict(state.coverage_hint)
    if coverage_mode(config) == "show":
        for name in tools.declared_covered(reply, DIMENSIONS):
            coverage[name] = "covered"

    declared = tools.declared_notes(reply, DIMENSIONS) if takes_notes(config) else []
    notes = state.working_notes + [{"turn": turn, **note} for note in declared]
    for note in notes[len(state.working_notes):]:
        print(f"    📝 {note['dimension']}: {note['observation']}")

    # 1.5 — a safety net, recorded as an incident so it is never read as a close
    at_cap = turn >= config["limits"]["max_turns"]
    if at_cap:
        events.append({"event": "turn_cap", "turns": turn})

    return {
        "doctor_messages": messages,
        "conversation": conversation,
        "turn_count": turn,
        "coverage_hint": coverage,
        "working_notes": notes,
        "events": events,
        "usage": usage,
        "finished": at_cap,
        "stop_reason": "turn_cap" if at_cap else None,
    }


# ── Patient ──────────────────────────────────


def patient_node(state: State) -> Dict[str, Any]:
    """The tool call itself: the patient answers what the doctor just said."""
    config = state.config
    events = list(state.events)
    usage = list(state.usage)

    # ── What it is sent ──
    # the first turn builds the context: the role, then who this patient is
    messages = state.patient_messages or [
        {"role": "system", "content": _patient_system_prompt(config, state.patient)}
    ]

    question = state.conversation[-1]["content"]
    messages = messages + [{"role": "user", "content": question}]

    reply = llm.chat(config, "patient", messages, events=events, usage=usage)
    messages = messages + [reply]

    # ── It answered ──
    # the only outcome: the patient cannot end the consultation (1.5), and an
    # empty reply was already retried in llm.chat
    answer = (reply.get("content") or "").strip()
    print(f"🧑  Patient : {answer}")

    # §3.1 — the answer alone comes back as the tool result; ours goes after it
    handed_back = [tools.tool_result(answer)]
    note = tools.coverage_note(_outstanding(config, state.coverage_hint))
    if note:
        handed_back.append(note)

    return {
        "patient_messages": messages,
        "doctor_messages": state.doctor_messages + handed_back,
        "conversation": state.conversation
        + [{"role": "patient", "content": answer, "turn": state.turn_count}],
        "events": events,
        "usage": usage,
    }


# §4.1
def _outstanding(config: Dict[str, Any], coverage: Dict[str, str]) -> list:
    """What is still open — handed back only in `show`."""
    if coverage_mode(config) != "show":
        return []
    return [name for name in DIMENSIONS if coverage.get(name) != "covered"]


def _patient_system_prompt(config: Dict[str, Any], patient: Dict[str, Any]) -> str:
    """PATIENT.md carries the role; patient_profile carries who this one is."""
    return (
        prompts.compose_prompt(config, "patient")
        + prompts.SEPARATOR
        + patient_profile.describe_patient(patient)
    )


# ── Report ───────────────────────────────────


# 1.13, D9
def report_node(state: State) -> Dict[str, Any]:
    """The one exit from the loop: it runs whatever ended the consultation."""
    config = state.config
    events = list(state.events)
    usage = list(state.usage)

    # ── What it is shown ──
    # the doctor continues its own consultation; the transcript travels anyway
    # because it never saw turn numbers and Evidence.turn needs them
    parts = [
        prompts.compose_prompt(config, "report"),
        report.transcript_text(state.conversation),
    ]
    # on a second pass the gaps go last, where they are the most recent thing said
    if state.report_attempts:
        parts.append(report.retry_note(report.gaps(state.report)))

    messages = state.doctor_messages + [
        {"role": "user", "content": prompts.SEPARATOR.join(parts)}
    ]

    # ── What came back ──
    # no tools: there is nothing left to ask, only to write
    reply = llm.chat(config, "report", messages, events=events, usage=usage)
    raw = (reply.get("content") or "").strip()

    attempt = state.report_attempts + 1
    parsed = report.parse(raw, state.patient.get("patient_id", "unknown"))

    if parsed is None:
        events.append({"event": "report_unparsed", "attempt": attempt})
    elif report.gaps(parsed):
        events.append({"event": "report_gaps", "attempt": attempt, "missing": report.gaps(parsed)})

    return {
        "doctor_messages": messages + [reply],
        "report_raw": raw,
        "report": parsed,
        "report_attempts": attempt,
        "events": events,
        "usage": usage,
    }
