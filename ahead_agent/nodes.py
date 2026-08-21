# ahead_agent/nodes.py
# ─────────────────────────────────────────────
# One function per graph node.
# Each function takes State → returns the channels it changed.
# ─────────────────────────────────────────────

from __future__ import annotations

from typing import Any, Dict

from . import llm, patient_profile, prompts, report, tools
from .config import BIPQ_DIMENSIONS, BMQ_SUBSCALES, CAUSES_DIMENSION, coverage_mode
from .state import State

# What the doctor is asked to end up with a view on, and so what coverage is
# measured against. Causes included: it is reported even though it is not scored.
DIMENSIONS = list(BIPQ_DIMENSIONS) + list(BMQ_SUBSCALES) + [CAUSES_DIMENSION]

# The mechanics of talking, kept next to the tool they name: the doctor's role
# is in DOCTOR.md, but how it reaches the patient is code, and the tool can be
# renamed without silently breaking a markdown file (this is Scout's
# `doctor.user` message).
OPENING = (
    f"Converse with the patient using the {tools.TOOL_NAME} tool to ask a question. "
    "Go back and forth this way like in a real session."
)


# ── Doctor ───────────────────────────────────

def doctor_node(state: State) -> Dict[str, Any]:
    """One doctor turn: it speaks through the tool, or it stops (1.5)."""
    config = state.config
    events = list(state.events)
    usage = list(state.usage)

    # The first turn builds the context; after that it is carried in the state.
    messages = state.doctor_messages or [
        {"role": "system", "content": prompts.compose(config, "doctor")},
        {"role": "user", "content": OPENING},
    ]

    reply = llm.chat(
        config, "doctor", messages, tools=tools.doctor_tools(config), events=events, usage=usage
    )
    messages = messages + [reply]

    # Three ways a turn can end: the doctor spoke, it chose to stop, or its call
    # was broken. Only the first one continues the loop.
    try:
        said = tools.hand_off_message(reply)   # None = it stopped calling the tool
    except tools.MalformedToolCall as error:
        events.append({"event": "malformed_tool_call", "detail": str(error)})
        said, stop_reason = None, "malformed_call"
    else:
        stop_reason = "doctor" if said is None else None

    # ── It stopped: nothing was said, so there is no turn to record ──

    if said is None:
        return {
            "doctor_messages": messages,
            "events": events,
            "usage": usage,
            "finished": True,
            "stop_reason": stop_reason,
        }

    # ── It spoke ──

    print(f"\n🩺  Doctor  : {said}")
    turn = state.turn_count + 1
    conversation = state.conversation + [{"role": "doctor", "content": said, "turn": turn}]

    # Whatever it declared settled this turn, added to what it declared before.
    coverage = dict(state.coverage_hint)
    for name in tools.declared_covered(reply, DIMENSIONS):
        coverage[name] = "cubierto"

    # A safety net, not a criterion: reaching it is recorded as an incident so a
    # capped consultation is never mistaken for one the doctor closed.
    at_cap = turn >= config["limits"]["max_turns"]
    if at_cap:
        events.append({"event": "turn_cap", "turns": turn})

    return {
        "doctor_messages": messages,
        "conversation": conversation,
        "turn_count": turn,
        "coverage_hint": coverage,
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

    # The first turn builds the context: the role, then who this patient is.
    messages = state.patient_messages or [
        {"role": "system", "content": _patient_system(config, state.patient)}
    ]

    question = state.conversation[-1]["content"]
    messages = messages + [{"role": "user", "content": question}]

    reply = llm.chat(config, "patient", messages, events=events, usage=usage)
    messages = messages + [reply]

    # ── It answered ──
    # The only outcome: the patient cannot end the consultation (1.5), and an
    # empty reply was already retried in llm.chat.

    answer = (reply.get("content") or "").strip()
    print(f"🧑  Patient : {answer}")

    return {
        "patient_messages": messages,
        # The doctor gets the answer as the result of its call, and what it has
        # not covered yet — nothing about the patient beyond what was said:
        # this is where the isolation of §3.1 is either kept or broken.
        "doctor_messages": state.doctor_messages
        + [tools.tool_result(answer, _outstanding(config, state.coverage_hint))],
        "conversation": state.conversation
        + [{"role": "patient", "content": answer, "turn": state.turn_count}],
        "events": events,
        "usage": usage,
    }


def _outstanding(config: Dict[str, Any], coverage: Dict[str, str]) -> list:
    """What is still open — handed back only in `show` (§4.1).

    In `declare` the map is kept and the doctor hears nothing: what it believed
    it covered is then comparable against what 3.2 finds it actually covered,
    without the answer having been given to it first.
    """
    if coverage_mode(config) != "show":
        return []
    return [name for name in DIMENSIONS if coverage.get(name) != "cubierto"]


def _patient_system(config: Dict[str, Any], patient: Dict[str, Any]) -> str:
    """PATIENT.md carries the role; patient_profile carries who this one is."""
    return prompts.compose(config, "patient") + prompts.SEPARATOR + patient_profile.describe(patient)


# ── Report ───────────────────────────────────

def report_node(state: State) -> Dict[str, Any]:
    """The one exit from the loop: it runs whatever ended the consultation (1.13)."""
    config = state.config
    events = list(state.events)
    usage = list(state.usage)

    # The doctor writes its own report, continuing the consultation it just had
    # (§4). A fresh model reading the transcript would score just as well and
    # mean something else entirely — that is the artifact arm of 5.4.
    #
    # The numbered transcript still travels: the doctor remembers the
    # conversation but never saw turn numbers, and Evidence.turn needs them.
    parts = [
        prompts.compose(config, "report"),
        report.transcript_text(state.conversation),
    ]
    # On a second pass, what the last one left out goes at the end, where it is
    # the most recent thing said (1.13).
    if state.report_attempts:
        parts.append(report.retry_note(report.gaps(state.report)))

    messages = state.doctor_messages + [
        {"role": "user", "content": prompts.SEPARATOR.join(parts)}
    ]

    # No tools: there is nothing left to ask, only to write.
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
