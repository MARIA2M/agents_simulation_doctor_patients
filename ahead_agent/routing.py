# ahead_agent/routing.py
# The only decision in the loop.

from __future__ import annotations

from . import report
from .state import State


def route_after_doctor(state: State) -> str:
    """Whether the doctor called the tool — the turn count is not consulted.

    Keeping the cap out of here is what stops it from quietly becoming the
    criterion for ending a consultation (1.5).
    """
    return "report" if state.finished else "patient"


def route_after_report(state: State) -> str:
    """Whether to ask the doctor again for what it left out (1.13).

    It gives up rather than looping: what is still missing after the last
    attempt stays NA, which is a result, where an endless retry would only be
    an endless bill.
    """
    if not report.gaps(state.report):
        return "end"

    attempts_allowed = state.config["limits"]["report_retries"] + 1
    return "end" if state.report_attempts >= attempts_allowed else "report"
