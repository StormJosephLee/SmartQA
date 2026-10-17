"""Agent 状态定义（LangGraph StateGraph 的 state schema）。"""

from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    question: str
    history: list[dict[str, str]]
    # 路由结果
    route: str  # rag | tool | answer
    tool_name: str
    tool_args: dict[str, Any]
    sub_query: str
    # 证据与工具结果
    evidence: list[dict[str, Any]]  # {id, content, source, page, score}
    tool_results: list[dict[str, Any]]  # {tool, args, output, ok}
    # 反思
    reflect_count: int
    rounds: int
    sufficient: bool
    # 产物
    citations: list[dict[str, Any]]
    answer_messages: list[dict[str, str]]
    guardrail: str  # ok | rejected
    guardrail_retry: int
    trace: list[str]
