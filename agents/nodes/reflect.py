"""Reflect 节点：判断证据是否充分，最多反思 3 次（agent_design.md#3）。"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from agents.state import AgentState
from core.config import cfg
from core.logging import get_logger
from core.prompts import prompt
from llm.chat import get_llm

logger = get_logger(__name__)
_JSON_BLOCK = re.compile(r"\{.*\}", re.S)


def make_reflect() -> Callable[[AgentState], Any]:
    llm = get_llm()

    async def reflect_node(state: AgentState) -> dict:
        max_reflect = int(cfg("agent.max_reflect", 3))
        count = int(state.get("reflect_count", 0))
        question = state.get("question", "")
        evidence = state.get("evidence", [])
        tool_results = state.get("tool_results", [])

        if not evidence and not tool_results:
            # 无证据时最多再检索一次，避免空转
            return {"sufficient": count >= max_reflect, "reflect_count": count + 1, "sub_query": question}

        if count >= max_reflect:
            logger.info("reflect reached max=%d, force answer", max_reflect)
            return {"sufficient": True, "reflect_count": count + 1}

        evidence_text = "\n".join(
            f"[{i + 1}] {e.get('content', '')[:300]}" for i, e in enumerate(evidence)
        ) or "（无）"
        if tool_results:
            evidence_text += "\n工具结果：" + "\n".join(
                f"- {r.get('tool')}: {str(r.get('output', ''))[:300]}" for r in tool_results
            )

        prompt_text = prompt("agent", "reflector_template").format(
            question=question, evidence=evidence_text
        )
        try:
            raw = await llm.complete([{"role": "user", "content": prompt_text}], temperature=0.0)
            match = _JSON_BLOCK.search(raw.strip().strip("`"))
            verdict = json.loads(match.group(0)) if match else {}
        except Exception as exc:  # noqa: BLE001 反思失败即视为充分，避免死循环
            logger.warning("reflect failed: %s", exc)
            verdict = {"sufficient": True}

        sufficient = bool(verdict.get("sufficient", True))
        sub_query = str(verdict.get("sub_query") or "") or question
        trace = list(state.get("trace", []))
        trace.append(f"reflect#{count + 1} -> sufficient={sufficient}")
        return {
            "sufficient": sufficient,
            "reflect_count": count + 1,
            "sub_query": sub_query,
            "trace": trace,
        }

    return reflect_node
