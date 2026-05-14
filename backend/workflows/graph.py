"""LangGraph ``StateGraph`` definition.

Topology::

    START
      ↓
    validate_input
      ↓
    analyze_project
      ↓
    model_schema
      ↓
    fanout → analyze_performance ∥ analyze_security
                                 ↓
                          merge_results
                                 ↓
                          generate_erd
                                 ↓
                   await_approval (human-in-the-loop)
                  ↙ approved        ↘ rejected
            generate_sql       (loop) analyze_project
                ↓
        update_openproject
                ↓
              END
"""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from backend.workflows.nodes import (
    WorkflowDeps,
    fanout_to_parallel,
    make_analyze_performance,
    make_analyze_project,
    make_analyze_security,
    make_await_approval,
    make_generate_erd,
    make_generate_sql,
    make_merge_results,
    make_model_schema,
    make_update_openproject,
    make_validate_input,
    route_after_approval,
)
from backend.workflows.state import WorkflowState


def build_analysis_graph(deps: WorkflowDeps, checkpointer: BaseCheckpointSaver):
    """Build and compile the analysis workflow graph."""
    g: StateGraph = StateGraph(WorkflowState)

    g.add_node("validate_input", make_validate_input(deps))
    g.add_node("analyze_project", make_analyze_project(deps))
    g.add_node("model_schema", make_model_schema(deps))
    g.add_node("analyze_performance", make_analyze_performance(deps))
    g.add_node("analyze_security", make_analyze_security(deps))
    g.add_node("merge_results", make_merge_results(deps))
    g.add_node("generate_erd", make_generate_erd(deps))
    g.add_node("await_approval", make_await_approval(deps))
    g.add_node("generate_sql", make_generate_sql(deps))
    g.add_node("update_openproject", make_update_openproject(deps))

    g.add_edge(START, "validate_input")
    g.add_edge("validate_input", "analyze_project")
    g.add_edge("analyze_project", "model_schema")

    # Fan out to two parallel branches.
    g.add_conditional_edges(
        "model_schema",
        fanout_to_parallel,
        ["analyze_performance", "analyze_security"],
    )
    g.add_edge("analyze_performance", "merge_results")
    g.add_edge("analyze_security", "merge_results")

    g.add_edge("merge_results", "generate_erd")
    g.add_edge("generate_erd", "await_approval")

    # Approval gate: interrupt before evaluating the route. When the
    # caller resumes the graph after updating ``approval_state``, the
    # router below picks the correct branch.
    g.add_conditional_edges(
        "await_approval",
        route_after_approval,
        {
            "generate_sql": "generate_sql",
            "analyze_project": "analyze_project",
            "__end__": END,
        },
    )
    g.add_edge("generate_sql", "update_openproject")
    g.add_edge("update_openproject", END)

    return g.compile(
        checkpointer=checkpointer,
        interrupt_before=["await_approval"],
    )
