# ahead_agent/graph.py
# doctor ⇄ patient, until the doctor stops calling the tool. The only module
# that touches StateGraph.

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .nodes import doctor_node, patient_node
from .routing import route_after_doctor
from .state import State


def build_graph(config: dict):
    """ """
    # Nodes
    graph = StateGraph(State)
    graph.add_node("doctor", doctor_node)
    graph.add_node("patient", patient_node)

    # Loops
    graph.add_edge(START, "doctor")
    graph.add_conditional_edges("doctor", route_after_doctor, {"patient": "patient", "end": END})
    graph.add_edge("patient", "doctor")

    
    # N node interactions (default)
    node_visits = 2 * config["limits"]["max_turns"] + 10

    return graph.compile().with_config({"recursion_limit": node_visits})
