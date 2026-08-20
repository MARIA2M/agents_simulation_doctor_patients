# ahead_agent/tools.py
# The patient is a tool of the doctor, not a node beside it — the equivalent of
# Scout's `delegate patient, :patient` (§1.1).

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

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
                }
            },
            "required": ["message"],
        },
    },
}

DOCTOR_TOOLS: List[Dict[str, Any]] = [HAND_OFF_TO_PATIENT]

TOOL_NAME = HAND_OFF_TO_PATIENT["function"]["name"]


class MalformedToolCall(ValueError):
    """The doctor tried to speak and failed. Not the same as choosing to stop."""


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

    arguments = function.get("arguments")
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError as error:
            raise MalformedToolCall(f"arguments are not JSON: {arguments!r}") from error

    message = (arguments or {}).get("message") if isinstance(arguments, dict) else None
    if not isinstance(message, str) or not message.strip():
        raise MalformedToolCall(f"no message in arguments: {arguments!r}")

    return message.strip()


def tool_result(text: str) -> Dict[str, Any]:
    """What the patient said, given back to the doctor as the call's result."""
    return {"role": "tool", "name": TOOL_NAME, "content": text}
