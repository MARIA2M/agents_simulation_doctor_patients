# ahead_agent/__init__.py
# ─────────────────────────────────────────────
# The package entry point (§2).
#
# `build_graph` resolves on demand, not on import: `graph.py` pulls in langgraph,
# which takes about three minutes off GPFS, and without this every import of the
# package would pay it — including post-processing tests that never touch the graph.
# ─────────────────────────────────────────────

from __future__ import annotations

from typing import Any

from .state import State

__all__ = ["State", "build_graph"]


def __getattr__(name: str) -> Any:
    if name == "build_graph":
        from .graph import build_graph

        return build_graph
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
