# ahead_agent/tools.py
# ─────────────────────────────────────────────
# The patient is a tool of the doctor, not a node beside it — the equivalent of
# Scout's `delegate patient, :patient` (§1.1).
# ─────────────────────────────────────────────

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Dict, List, Optional

from .config import coverage_mode

HAND_OFF_TO_PATIENT = {
    "type": "function",
    "function": {
        "name": "hand_off_to_patient",
        "description": "Say something to the patient and get their reply.",
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "What to say to the patient, in your own words",
                },
            },
            "required": ["message"],
        },
    },
}

# Optional on purpose (§4.1). The doctor is already calling the tool every turn,
# so its own bookkeeping costs no extra call, and a model that ignores the field
# still holds a real consultation.
#
# It lives here rather than in DOCTOR.md so there is one source of truth: with
# the feature off the argument does not exist, and neither does the promise that
# anything comes back.
COVERED_ARGUMENT = {
    "type": "array",
    "items": {"type": "string"},
    "description": (
        "Dimensions you now have enough on to judge — not merely touched on. "
        "Optional, and nothing depends on it."
    ),
}

DOCTOR_TOOLS: List[Dict[str, Any]] = [HAND_OFF_TO_PATIENT]

TOOL_NAME = HAND_OFF_TO_PATIENT["function"]["name"]


def doctor_tools(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The doctor's tools for this run. `covered` exists in declare and show."""
    mode = coverage_mode(config)
    if mode == "off":
        return DOCTOR_TOOLS

    argument = deepcopy(COVERED_ARGUMENT)
    # Only in `show` does anything come back, so only there is it promised.
    if mode == "show":
        argument["description"] += (
            " What you leave out comes back with the patient's reply, as a note "
            "of what is still open. It is yours to use or ignore."
        )

    tool = deepcopy(HAND_OFF_TO_PATIENT)
    tool["function"]["parameters"]["properties"]["covered"] = argument
    return [tool]


class MalformedToolCall(ValueError):
    """The doctor tried to speak and failed. Not the same as choosing to stop."""


# ── Reading the call ─────────────────────────

def hand_off_message(reply: Dict[str, Any]) -> Optional[str]:
    """What the doctor wants said, or None if it stopped calling the tool.

    None is how the doctor closes the consultation (1.5), so a broken call must
    raise instead: ending the consultation on a parsing failure would look like
    a decision it never made.
    """
    calls = reply.get("tool_calls") or []
    if not calls:
        return None

    function = calls[0].get("function") or {}
    if function.get("name") != TOOL_NAME:
        raise MalformedToolCall(f"called {function.get('name')!r}, not {TOOL_NAME}")

    message = _arguments(function).get("message")
    if not isinstance(message, str) or not message.strip():
        raise MalformedToolCall(f"no message in arguments: {function.get('arguments')!r}")

    return message.strip()


def _arguments(function: Dict[str, Any]) -> Dict[str, Any]:
    """The call's arguments. Ollama sends them parsed or as JSON text."""
    arguments = function.get("arguments")

    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError as error:
            raise MalformedToolCall(f"arguments are not JSON: {arguments!r}") from error

    return arguments if isinstance(arguments, dict) else {}


def declared_covered(reply: Dict[str, Any], known: List[str]) -> List[str]:
    """Dimensions the doctor says it has settled (§4.1).

    Forgiving by design: a missing field, the wrong shape, or a name we do not
    recognise all come back empty rather than raising. Nothing about coverage
    may cost a consultation its tool call.
    """
    calls = reply.get("tool_calls") or []
    if not calls:
        return []

    try:
        arguments = _arguments(calls[0].get("function") or {})
    except MalformedToolCall:
        return []

    covered = arguments.get("covered")
    if not isinstance(covered, list):
        return []
    return [name for name in covered if name in known]


# ── Answering it ─────────────────────────────

def tool_result(text: str, outstanding: Optional[List[str]] = None) -> Dict[str, Any]:
    """What the patient said, given back to the doctor as the call's result.

    The dimensions still open ride back with it (§4.1): the doctor reads them
    at the moment it is choosing what to ask next. It informs and never blocks
    — the doctor is still the one who decides to stop (1.5), and closing with
    holes left in is a finding, not a failure to prevent.
    """
    if outstanding:
        text = f"{text}\n\n[not yet explored: {', '.join(outstanding)}]"
    return {"role": "tool", "name": TOOL_NAME, "content": text}
