"""知识库检索工具：复用 rag 的混合检索。"""

from __future__ import annotations

import json
from typing import Any

from agents.tools.base import BaseTool, ToolContext, ToolResult
from rag.retriever import HybridRetriever


class KBSearchTool(BaseTool):
    name = "kb_search"
    description = "知识库检索：输入 query，返回最相关的知识片段（含来源与页码）"

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        query = str(args.get("query") or args.get("q") or "").strip()
        if not query or ctx.session is None:
            return ToolResult(tool=self.name, args=args, ok=False, error="缺少 query 或数据库会话")

        chunks = await HybridRetriever(ctx.session).retrieve(query, kb_ids=ctx.kb_ids)
        payload = {
            "results": [
                {
                    "id": c.id,
                    "content": c.content,
                    "source": c.source,
                    "page": c.page,
                    "score": round(float(c.score), 4),
                }
                for c in chunks
            ]
        }
        return ToolResult(
            tool=self.name,
            args={"query": query},
            output=json.dumps(payload, ensure_ascii=False),
            payload=payload,
        )
