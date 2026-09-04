from langgraph.graph import StateGraph, START, END
from agents.statement_extraction.schema import AgentState
from agents.statement_extraction.nodes import (
    node_validate_file,
    node_extract_text,
    node_detect_format,
    node_extract_fields,
    node_reconcile,
    node_escalate,
    node_finalize,
    should_escalate,
)

def route(state: dict) -> str:
    """If error exists in state, stop. Otherwise continue to next node."""
    if state.get("error"):
        return "end"
    return "continue"

def route_after_reconcile(state: dict) -> str:
    if state.get("error"):
        return "end"
    if should_escalate(state):
        return "escalate"
    return "finalize"

def build_graph():
    graph = StateGraph(AgentState)

    # Deterministic nodes, then the model, then deterministic checks on it.
    graph.add_node("validate_file", node_validate_file)
    graph.add_node("extract_text", node_extract_text)
    graph.add_node("detect_format", node_detect_format)
    graph.add_node("extract_fields", node_extract_fields)   # model call, cheap model
    graph.add_node("reconcile", node_reconcile)             # arithmetic, no model
    graph.add_node("escalate", node_escalate)               # model call, stronger model, at most once
    graph.add_node("finalize", node_finalize)

    graph.add_edge(START, "validate_file")

    graph.add_conditional_edges("validate_file",  route, {"continue": "extract_text",   "end": END})
    graph.add_conditional_edges("extract_text",   route, {"continue": "detect_format",  "end": END})
    graph.add_conditional_edges("detect_format",  route, {"continue": "extract_fields", "end": END})
    graph.add_conditional_edges("extract_fields", route, {"continue": "reconcile",      "end": END})
    graph.add_conditional_edges("reconcile", route_after_reconcile,
                                {"escalate": "escalate", "finalize": "finalize", "end": END})
    graph.add_edge("escalate", "reconcile")
    graph.add_edge("finalize", END)

    return graph.compile()

compiled_graph = build_graph()
