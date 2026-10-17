"""RAG 节点：执行知识库检索并累积证据。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agents.state import AgentState
from agents.tools.base import ToolContext
from core.logging import get_logger
from rag.retriever import HybridRetriever

logger = get_logger(__name__)

MAX_EVIDENCE = 8


def make_rag_node(ctx: ToolContext) -> Callable[[AgentState], Any]:
    async def rag_node(state: AgentState) -> dict:
        if ctx.session is None:
            return {"evidence": state.get("evidence", [])}
        query = state.get("sub_query") or state.get("question", "")
        chunks = await HybridRetriever(ctx.session).retrieve(query, kb_ids=ctx.kb_ids)
        evidence = list(state.get("evidence", []))
        seen = {e.get("id") for e in evidence}
        for chunk in chunks:
            if chunk.id in seen:
                continue
            evidence.append(
                {
                    "id": chunk.id,
                    "content": chunk.content,
                    "source": chunk.source,
                    "page": chunk.page,
                    "score": round(float(chunk.score), 4),
                }
            )
            seen.add(chunk.id)
        trace = list(state.get("trace", []))
        trace.append(f"retrieve('{query[:24]}') -> {len(chunks)} hits")
        logger.info("rag node: query=%s hits=%d", query[:30], len(chunks))
        return {"evidence": evidence[:MAX_EVIDENCE], "trace": trace}

    return rag_node
