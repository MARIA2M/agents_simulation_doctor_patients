# ahead_agent/state.py
# What the graph carries between nodes. No q_index, no follow_up_count: turns
# are not a walk through a list of questions any more (1.3).
#
# A dataclass because StateGraph reads these annotations to know its channels,
# and because the empty starting values then live next to the field they fill.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .report import Report


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

    # dimension → "cubierto" once the doctor says so, otherwise "sin sondear".
    # Its own bookkeeping, declared through the tool, read back to it each turn
    # (§4.1). A criterion of sufficiency, not a counter of turns.
    coverage_hint: dict = field(default_factory=dict)

    # ── Report (§4) ──
    # Written once the loop exits, whatever ended it (1.13). The raw text is
    # kept beside the parsed one so a report that failed to parse is still
    # readable, and report_attempts is what the retry limit counts.
    report_raw: Optional[str] = None
    report: Optional[Report] = None
    report_attempts: int = 0

    events: list = field(default_factory=list)  # retries, empty turns, broken calls
    usage: list = field(default_factory=list)   # tokens per call, to size context_length
