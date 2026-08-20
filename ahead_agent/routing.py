# ahead_agent/routing.py
# The only decision in the loop.

from __future__ import annotations

from .state import State


def route_after_doctor(state: State) -> str:
    """Whether the doctor called the tool — the turn count is not consulted.

    Keeping the cap out of here is what stops it from quietly becoming the
    criterion for ending a consultation (1.5).
    """
    return "end" if state.finished else "patient"
