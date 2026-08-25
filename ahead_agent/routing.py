# ahead_agent/routing.py
# ─────────────────────────────────────────────
# The only decision in the loop.
# ─────────────────────────────────────────────

from __future__ import annotations

from . import report
from .state import State

# 1.5
def route_after_doctor(state: State) -> str:
    """Back to the patient, or out to the report."""
    return "report" if state.finished else "patient"

# 1.13
def route_after_report(state: State) -> str:
    """Ask again for what it left out or stop."""
    if not report.gaps(state.report):
        return "end"

    return "end" if state.report_attempts >= state.config["limits"]["report_attempts"] else "report"
