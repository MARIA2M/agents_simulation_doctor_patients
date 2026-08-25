# ahead_agent/tools.py
# ─────────────────────────────────────────────
# The patient is a tool of the doctor, not a node beside it — the equivalent of
# Scout's `delegate patient, :patient` (§1.1).
# ─────────────────────────────────────────────

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Dict, List, Optional

from .config import coverage_mode, takes_notes


# ── What the doctor reads ────────────────────
# Prompt text, so it is hashed into run_meta by prompts.hashes (0.4). The rest
# of this file is JSON Schema, which is the shape Ollama requires.

# the tool itself
ASK = "Say something to the patient and get their reply."

MESSAGE = "What to say to the patient, in your own words"

# the `covered` argument
COVERED = (
    "Dimensions you now have enough on to judge — not merely touched on. "
    "Optional. What you leave out comes back with the patient's reply, as a "
    "note of what is still open. It is yours to use or ignore."
)

# the `notes` argument
NOTES = (
    "What this reply told you, dimension by dimension. Optional, and only "
    "for what actually moved: nothing to add is a normal turn. Revisit an "
    "earlier note whenever the conversation has since changed its meaning."
)

NOTE_DIMENSION = "Which one this bears on"

NOTE_OBSERVATION = (
    "What you now understand about it, and what they said that shows it. If it "
    "changes what you thought before, say so and say why — 'earlier they gave "
    "the impression that…, but…'."
)


# ── The tool ─────────────────────────────────

# the only tool the doctor has
HAND_OFF_TO_PATIENT = {
    "type": "function",
    "function": {
        "name": "hand_off_to_patient",
        "description": ASK,
        "parameters": {
            "type": "object",
            "properties": {"message": {"type": "string", "description": MESSAGE}},
            "required": ["message"],
        },
    },
}

DOCTOR_TOOLS: List[Dict[str, Any]] = [HAND_OFF_TO_PATIENT]   # the baseline set
TOOL_NAME = HAND_OFF_TO_PATIENT["function"]["name"]          # what a call must name


# ── Optional arguments (§4.1) ────────────────

# added by `coverage_hint: show`
COVERED_ARGUMENT = {"type": "array", "items": {"type": "string"}, "description": COVERED}

# added by `working_notes`
NOTES_ARGUMENT = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "dimension": {"type": "string", "description": NOTE_DIMENSION},
            "observation": {"type": "string", "description": NOTE_OBSERVATION},
        },
        "required": ["dimension", "observation"],
    },
    "description": NOTES,
}


# ── Building the tools ───────────────────────


def doctor_tools(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The doctor's tools for this run, with whatever arguments the arms add."""
    wants_covered = coverage_mode(config) == "show"
    wants_notes = takes_notes(config)
    if not (wants_covered or wants_notes):
        return DOCTOR_TOOLS

    tool = deepcopy(HAND_OFF_TO_PATIENT)
    properties = tool["function"]["parameters"]["properties"]
    if wants_covered:
        properties["covered"] = deepcopy(COVERED_ARGUMENT)
    if wants_notes:
        properties["notes"] = deepcopy(NOTES_ARGUMENT)
    return [tool]


class MalformedToolCall(ValueError):
    """The doctor tried to speak and failed. Not the same as choosing to stop."""


# ── Reading the call ─────────────────────────


# 1.5
def hand_off_message(reply: Dict[str, Any]) -> Optional[str]:
    """What the doctor wants said, or None if it stopped calling the tool."""
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


# §4.1
def declared_covered(reply: Dict[str, Any], known: List[str]) -> List[str]:
    """Dimensions the doctor says it has settled."""
    covered = _optional_arguments(reply).get("covered")
    if not isinstance(covered, list):
        return []
    return [name for name in covered if name in known]


# §4.1
def declared_notes(reply: Dict[str, Any], known: List[str]) -> List[Dict[str, str]]:
    """What the doctor says this turn told it."""
    notes = []
    for entry in _optional_arguments(reply).get("notes") or []:
        if not isinstance(entry, dict):
            continue
        dimension = entry.get("dimension")
        observation = entry.get("observation")
        if dimension in known and isinstance(observation, str) and observation.strip():
            notes.append({"dimension": dimension, "observation": observation.strip()})
    return notes


def _arguments(function: Dict[str, Any]) -> Dict[str, Any]:
    """The call's arguments. Ollama sends them parsed or as JSON text."""
    arguments = function.get("arguments")

    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError as error:
            raise MalformedToolCall(f"arguments are not JSON: {arguments!r}") from error

    return arguments if isinstance(arguments, dict) else {}


def _optional_arguments(reply: Dict[str, Any]) -> Dict[str, Any]:
    """The arguments, or {} — nothing optional may cost a consultation its call."""
    calls = reply.get("tool_calls") or []
    if not calls:
        return {}
    try:
        return _arguments(calls[0].get("function") or {})
    except MalformedToolCall:
        return {}


# ── Answering it ─────────────────────────────


# §3.1
def tool_result(text: str) -> Dict[str, Any]:
    """What the patient said, and only that."""
    return {"role": "tool", "name": TOOL_NAME, "content": text}


# §4.1
def coverage_note(outstanding: Optional[List[str]]) -> Optional[Dict[str, Any]]:
    """The dimensions still open, in our own voice and never the patient's."""
    if not outstanding:
        return None
    return {
        "role": "user",
        "content": "Not yet explored: " + ", ".join(outstanding) + ".",
    }
