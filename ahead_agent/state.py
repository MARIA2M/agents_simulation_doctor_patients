# ahead_agent/state.py
# What the graph carries between nodes. No q_index, no follow_up_count: turns
# are not a walk through a list of questions any more (1.3).
#
# A dataclass because StateGraph reads these annotations to know its channels,
# and because the empty starting values then live next to the field they fill.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class State:
    config: dict
    patient: dict               # only patient_node reads it (§3.1)

    conversation: list = field(default_factory=list)   # [{"role", "content", "turn"}]
    doctor_messages: list = field(default_factory=list)  # its own history, with tool_calls
    patient_messages: list = field(default_factory=list)

    turn_count: int = 0
    finished: bool = False      # the doctor stopped calling the tool (1.5)
    stop_reason: Optional[str] = None  # "doctor", "turn_cap" or "malformed_call"

    events: list = field(default_factory=list)  # retries, empty turns, broken calls
    usage: list = field(default_factory=list)   # tokens per call, to size context_length
