from langgraph.graph import StateGraph, START, END
from agents.statement_extraction.schema import AgentState
from agents.statement_extraction.nodes import (
    node_validate_file,
    node_extract_text,
    node_detect_format,
    node_extract_fields,
    node_finalize,
)

def route(state: dict) -> str:
    """If error exists in state, stop. Otherwise continue to next node."""
    if state.get("error"):
        return "end"
    return "continue"

def build_graph():
    graph = StateGraph(AgentState)

    # Deterministic nodes first, one model node, deterministic post-processing.
    graph.add_node("validate_file", node_validate_file)
    graph.add_node("extract_text", node_extract_text)
    graph.add_node("detect_format", node_detect_format)
    graph.add_node("extract_fields", node_extract_fields)   # the only model call
    graph.add_node("finalize", node_finalize)

    graph.add_edge(START, "validate_file")

    # Conditional edges: stop immediately if any node errors
    graph.add_conditional_edges("validate_file",  route, {"continue": "extract_text",   "end": END})
    graph.add_conditional_edges("extract_text",   route, {"continue": "detect_format",  "end": END})
    graph.add_conditional_edges("detect_format",  route, {"continue": "extract_fields", "end": END})
    graph.add_conditional_edges("extract_fields", route, {"continue": "finalize",       "end": END})

    graph.add_edge("finalize", END)

    return graph.compile()

compiled_graph = build_graph()
