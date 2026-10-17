"""LangGraph 状态机组装（agent_design.md#1）。

Router → RAG / Tool / DirectLLM → Reflect → Answer → Guardrail
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from agents.nodes import (
    make_answer,
    make_guardrail,
    make_rag_node,
    make_reflect,
    make_router,
    make_tool_node,
)
from agents.state import AgentState
from agents.tools.base import ToolContext
from core.config import cfg
from core.logging import get_logger

logger = get_logger(__name__)


def _route_selector(state: AgentState) -> str:
    return state.get("route", "rag")


def _reflect_selector(state: AgentState) -> str:
    if state.get("sufficient", True):
        return "answer"
    max_rounds = int(cfg("agent.max_rounds", 8))
    if state.get("rounds", 0) >= max_rounds:
        return "answer"
    return "rag"


def _guard_selector(state: AgentState) -> str:
    if state.get("guardrail") == "rejected":
        return "rag"
    return END


def build_graph(ctx: ToolContext):
    """按请求构建（ctx 携带 session / 权限上下文）。"""
    workflow = StateGraph(AgentState)
    workflow.add_node("router", make_router())
    workflow.add_node("rag", make_rag_node(ctx))
    workflow.add_node("tool", make_tool_node(ctx))
    workflow.add_node("reflect", make_reflect())
    workflow.add_node("answer", make_answer())
    workflow.add_node("guardrail", make_guardrail())

    workflow.set_entry_point("router")
    workflow.add_conditional_edges(
        "router",
        _route_selector,
        {"rag": "rag", "tool": "tool", "answer": "answer"},
    )
    workflow.add_edge("rag", "reflect")
    workflow.add_edge("tool", "reflect")
    workflow.add_conditional_edges("reflect", _reflect_selector, {"rag": "rag", "answer": "answer"})
    workflow.add_edge("answer", "guardrail")
    workflow.add_conditional_edges("guardrail", _guard_selector, {"rag": "rag", END: END})
    return workflow.compile()


class QAAgent:
    """对外的 Agent 入口：返回 evidence / citations / answer_messages / trace。"""

    def __init__(self, ctx: ToolContext):
        self.ctx = ctx
        self.graph = build_graph(ctx)

    async def run(self, question: str, history: list[dict[str, str]] | None = None) -> AgentState:
        initial: AgentState = {
            "question": question,
            "history": history or [],
            "evidence": [],
            "tool_results": [],
            "reflect_count": 0,
            "rounds": 0,
            "trace": [],
            "guardrail": "ok",
            "guardrail_retry": 0,
        }
        state = await self.graph.ainvoke(initial)
        logger.info("agent finished, trace=%s", state.get("trace"))
        return state
