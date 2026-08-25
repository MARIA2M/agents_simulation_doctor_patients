# ahead_agent/state.py
# ─────────────────────────────────────────────
# What the graph carries between nodes.
# ─────────────────────────────────────────────

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .report import Report


@dataclass
class State:
    config: dict
    patient: dict                       # §3.1

    # ── Conversation (1.3) ───────────────────
    conversation: list = field(default_factory=list)     # [{"role", "content", "turn"}]
    doctor_messages: list = field(default_factory=list)
    patient_messages: list = field(default_factory=list)

    turn_count: int = 0
    finished: bool = False              # 1.5
    stop_reason: Optional[str] = None   # "doctor" | "turn_cap" | "malformed_call"

    # ── What the doctor keeps for itself (§4.1) ──
    coverage_hint: dict = field(default_factory=dict)  # dimension → "covered"; missing = not asked
    working_notes: list = field(default_factory=list)  # [{"turn", "dimension", "observation"}]

    # ── Report (§4, 1.13) ────────────────────
    report_raw: Optional[str] = None
    report: Optional[Report] = None
    report_attempts: int = 0

    # ── Traceability (0.4) ───────────────────
    events: list = field(default_factory=list)
    usage: list = field(default_factory=list)
