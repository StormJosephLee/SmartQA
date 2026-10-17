"""Guardrail 节点：输出侧合规复核（agent_design.md 状态机 Guardrail → RAG）。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agents.state import AgentState
from core.config import cfg
from core.logging import get_logger
from guardrails.output_filter import scan

logger = get_logger(__name__)

MAX_GUARDRAIL_RETRY = 1


def make_guardrail() -> Callable[[AgentState], Any]:
    async def guardrail_node(state: AgentState) -> dict:
        retry = int(state.get("guardrail_retry", 0))
        messages = state.get("answer_messages", [])
        tool_results = state.get("tool_results", [])
        evidence = state.get("evidence", [])

        suspicious = False
        for item in tool_results:
            if not scan(str(item.get("output", ""))).safe:
                suspicious = True
        for chunk in evidence:
            if not scan(str(chunk.get("content", ""))[:1000]).safe:
                suspicious = True

        trace = list(state.get("trace", []))
        if suspicious and retry < MAX_GUARDRAIL_RETRY:
            logger.warning("guardrail rejected, back to retrieve (retry=%d)", retry)
            trace.append("guardrail -> rejected, retry retrieve")
            max_reflect = int(cfg("agent.max_reflect", 3))
            return {
                "guardrail": "rejected",
                "guardrail_retry": retry + 1,
                "tool_results": [],  # 丢弃可疑工具结果
                "evidence": [],
                "sub_query": state.get("question", ""),
                "reflect_count": max_reflect,  # 强制下次直接进入作答
                "trace": trace,
            }

        trace.append("guardrail -> ok")
        return {"guardrail": "ok", "guardrail_retry": retry, "trace": trace, "answer_messages": messages}

    return guardrail_node
