"""Answer 节点：组装最终 prompt，由 chat_service 负责流式生成。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agents.state import AgentState
from core.prompts import prompt


def _build_messages(state: AgentState) -> list[dict[str, str]]:
    evidence = state.get("evidence", [])
    evidence_text = (
        "\n".join(f"[{i + 1}] {e.get('content', '')}（来源：{e.get('source', '')} p{e.get('page', 0)}）"
                  for i, e in enumerate(evidence))
        or prompt("agent", "no_evidence_notice", "知识库未覆盖此问题")
    )
    tool_text = (
        "\n".join(
            f"- {r.get('tool')}: {r.get('output') or r.get('error')}" for r in state.get("tool_results", [])
        )
        or "（未调用工具）"
    )
    history = state.get("history", []) or []
    history_text = "\n".join(f"{m.get('role')}: {m.get('content', '')[:300]}" for m in history[-6:]) or "（无）"

    system = prompt(
        "rag",
        "system_template",
        "你是 SmartQA，请严格基于证据回答，并在句末标注 [1][2] 引用。",
    )
    user = prompt("agent", "answer_template").format(
        evidence=evidence_text,
        tool_results=tool_text,
        history=history_text,
        question=state.get("question", ""),
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def make_answer() -> Callable[[AgentState], Any]:
    async def answer_node(state: AgentState) -> dict:
        return {"answer_messages": _build_messages(state)}

    return answer_node


def build_direct_messages(state: AgentState) -> list[dict[str, str]]:
    """无 Agent 时的直接问答 prompt（P0 路径）。"""
    evidence = state.get("evidence", [])
    history = state.get("history", []) or []
    return [
        {"role": "system", "content": prompt("rag", "system_template", "你是 SmartQA。")},
        {
            "role": "user",
            "content": prompt("rag", "qa_template").format(
                context="\n".join(f"[{i + 1}] {e.get('content', '')}" for i, e in enumerate(evidence))
                or "（无知识片段）",
                history="\n".join(f"{m.get('role')}: {m.get('content', '')}" for m in history[-6:]) or "（无）",
                question=state.get("question", ""),
            ),
        },
    ]
