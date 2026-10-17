"""Router 节点：规划下一步动作（agent_design.md#3 每轮一条 JSON 动作）。"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from agents.state import AgentState
from agents.tools import available_tools, tool_catalog
from core.logging import get_logger
from core.prompts import prompt
from llm.chat import get_llm

logger = get_logger(__name__)

_JSON_BLOCK = re.compile(r"\{.*\}", re.S)


def _extract_json(text: str) -> dict[str, Any]:
    """宽容解析：容忍 ```json 代码块与前后废话。"""
    cleaned = text.strip().strip("`")
    cleaned = re.sub(r"^json", "", cleaned, flags=re.I).strip()
    match = _JSON_BLOCK.search(cleaned)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}


def _format_history(history: list[dict[str, str]]) -> str:
    if not history:
        return "（无）"
    return "\n".join(f"{m.get('role')}: {m.get('content', '')[:200]}" for m in history[-6:])


def _format_evidence(evidence: list[dict[str, Any]]) -> str:
    if not evidence:
        return "（无）"
    return "\n".join(f"[{i + 1}] {e.get('content', '')[:300]}" for i, e in enumerate(evidence[:5]))


def make_router() -> Callable[[AgentState], Any]:
    llm = get_llm()

    async def router_node(state: AgentState) -> dict:
        question = state.get("question", "")
        sub_query = state.get("sub_query") or question
        plan_prompt = prompt("agent", "planner_template").format(
            tools=tool_catalog() or "（无可用工具）",
            history=_format_history(state.get("history", [])),
            evidence=_format_evidence(state.get("evidence", [])),
            question=sub_query,
        )
        try:
            raw = await llm.complete([{"role": "user", "content": plan_prompt}], temperature=0.0)
            plan = _extract_json(raw)
        except Exception as exc:  # noqa: BLE001 规划失败默认走检索
            logger.warning("router failed, fallback to retrieve: %s", exc)
            plan = {}

        action = str(plan.get("action", "retrieve")).lower()
        tool_name = str(plan.get("tool", "")).strip()
        tool_args = plan.get("args") or {}
        if not isinstance(tool_args, dict):
            tool_args = {}

        if action == "tool" and tool_name in available_tools():
            route = "tool"
        elif action == "answer":
            route = "answer"
        else:
            route = "rag"

        trace = list(state.get("trace", []))
        trace.append(
            f"router -> {route}" + (f":{tool_name}" if route == "tool" else "")
        )
        return {
            "route": route,
            "tool_name": tool_name,
            "tool_args": tool_args,
            "sub_query": str(plan.get("sub_query") or sub_query),
            "trace": trace,
            "rounds": state.get("rounds", 0) + 1,
        }

    return router_node
