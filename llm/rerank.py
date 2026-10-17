"""Rerank 适配层。

- provider=none：保持融合后的顺序（不额外引入依赖）
- provider=http：调用 OpenAI 兼容的 /rerank 接口（SiliconFlow / vLLM 等）
"""

from __future__ import annotations

from collections.abc import Sequence

import httpx

from core.config import get_settings
from core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class Reranker:
    async def rerank(self, query: str, documents: Sequence[str], top_n: int) -> list[tuple[int, float]]:
        """返回 [(原始下标, 分数), ...]，已按分数降序并截断到 top_n。"""
        if not documents:
            return []
        if settings.rerank_provider != "http" or not settings.rerank_base_url:
            return [(i, 0.0) for i in range(min(top_n, len(documents)))]

        payload = {
            "model": settings.rerank_model,
            "query": query,
            "documents": list(documents),
            "top_n": top_n,
        }
        headers = {"Authorization": f"Bearer {settings.rerank_api_key}"}
        try:
            async with httpx.AsyncClient(timeout=settings.llm_timeout) as client:
                resp = await client.post(
                    f"{settings.rerank_base_url.rstrip('/')}/rerank", json=payload, headers=headers
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001 重排失败不阻断，退化为原顺序
            logger.warning("rerank failed, fallback to fusion order: %s", exc)
            return [(i, 0.0) for i in range(min(top_n, len(documents)))]

        results = data.get("results", data.get("data", []))
        pairs: list[tuple[int, float]] = []
        for item in results:
            idx = item.get("index", item.get("document", {}).get("index"))
            score = item.get("relevance_score", item.get("score", 0.0))
            if idx is not None:
                pairs.append((int(idx), float(score)))
        if not pairs:
            return [(i, 0.0) for i in range(min(top_n, len(documents)))]
        pairs.sort(key=lambda x: x[1], reverse=True)
        return pairs[:top_n]


_reranker: Reranker | None = None


def get_reranker() -> Reranker:
    global _reranker
    if _reranker is None:
        _reranker = Reranker()
    return _reranker
