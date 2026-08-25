# ahead_agent/graph.py
# ─────────────────────────────────────────────
# doctor ⇄ patient until the doctor stops calling the tool, then the report.
# The only module that touches StateGraph.
# ─────────────────────────────────────────────

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .nodes import doctor_node, patient_node, report_node
from .routing import route_after_doctor, route_after_report
from .state import State


def build_graph(config: dict):
    """START → doctor ⇄ patient → report → END."""
    graph = StateGraph(State)
    graph.add_node("doctor", doctor_node)
    graph.add_node("patient", patient_node)
    graph.add_node("report", report_node)

    graph.add_edge(START, "doctor")
    # 1.13
    graph.add_conditional_edges(
        "doctor", route_after_doctor, {"patient": "patient", "report": "report"}
    )
    graph.add_edge("patient", "doctor")
    graph.add_conditional_edges(
        "report", route_after_report, {"report": "report", "end": END}
    )

    limits = config["limits"]
    # Two visits per turn, one per report attempt, and margin.
    node_visits = 2 * limits["max_turns"] + limits["report_attempts"] + 5

    return graph.compile().with_config({"recursion_limit": node_visits})
