"""Rerank 适配层。

- provider=none：保持融合后的顺序（不额外引入依赖）
- provider=http：调用 OpenAI 兼容的 /rerank 接口（SiliconFlow / vLLM 等）
"""

from __future__ import annotations

import time
from collections.abc import Sequence

import httpx

from core.config import get_settings
from core.logging import get_logger, truncate

logger = get_logger(__name__)
settings = get_settings()

# 合法 provider 取值，启动时会校验并告警非法配置
_VALID_PROVIDERS = ("none", "http")
_PROVIDER_VALIDATED = False
# 日志中 query / 单条文档的最大保留长度（observability.md §3.3）
_QUERY_LOG_LIMIT = 30
_DOC_LOG_LIMIT = 80


def _validate_provider_once() -> None:
    """启动期一次性校验：非法 provider 值 → warning + 自动回退为 none。"""
    global _PROVIDER_VALIDATED
    if _PROVIDER_VALIDATED:
        return
    _PROVIDER_VALIDATED = True
    p = settings.rerank_provider
    if p not in _VALID_PROVIDERS:
        logger.warning(
            "rerank provider=%r 不在合法值 %s 中，自动按 none 处理（不会调用任何重排服务）。"
            "如需开启，请确认该服务商支持 OpenAI 兼容的 /rerank 端点。",
            p,
            list(_VALID_PROVIDERS),
        )


class Reranker:
    async def rerank(self, query: str, documents: Sequence[str], top_n: int) -> list[tuple[int, float]]:
        """返回 [(原始下标, 分数), ...]，已按分数降序并截断到 top_n。"""
        _validate_provider_once()
        if not documents:
            return []
        if settings.rerank_provider != "http" or not settings.rerank_base_url:
            # 关闭分支：状态已在模块导入时校验过，此处静默返回
            return [(i, 0.0) for i in range(min(top_n, len(documents)))]

        payload = {
            "model": settings.rerank_model,
            "query": query,
            "documents": list(documents),
            "top_n": top_n,
        }
        headers = {"Authorization": f"Bearer {settings.rerank_api_key}"}
        t0 = time.perf_counter()
        # 入参日志：query 只打印前 30 字符（脱敏），documents 只打印条数
        logger.debug(
            "rerank -> model=%s base_url=%s docs=%d top_n=%d query_len=%d query=%r",
            settings.rerank_model,
            settings.rerank_base_url,
            len(documents),
            top_n,
            len(query or ""),
            truncate(query, _QUERY_LOG_LIMIT),
        )
        logger.debug(
            "rerank docs preview: %s",
            [truncate(d, _DOC_LOG_LIMIT) for d in documents[:3]],
        )
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
            logger.warning("rerank returned no valid pairs, keep fusion order")
            return [(i, 0.0) for i in range(min(top_n, len(documents)))]
        pairs.sort(key=lambda x: x[1], reverse=True)
        result = pairs[:top_n]
        logger.info(
            "rerank OK model=%s docs=%d top_n=%d hits=%d cost=%.0fms",
            settings.rerank_model,
            len(documents),
            top_n,
            len(result),
            (time.perf_counter() - t0) * 1000,
        )
        return result


# 模块导入时即校验一次，避免首次请求才暴露配置问题
_validate_provider_once()


_reranker: Reranker | None = None


def get_reranker() -> Reranker:
    global _reranker
    if _reranker is None:
        _reranker = Reranker()
    return _reranker