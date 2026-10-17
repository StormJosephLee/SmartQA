"""LLM 适配层：OpenAI 兼容协议（chat.completions），支持流式与降级重试。

对应 dataflow.md#3 失败路径：LLM 超时 → 重试 2 次 → 切更小模型 → 报错。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from typing import Any

from openai import AsyncOpenAI

from core.config import get_settings
from core.errors import llm_upstream
from core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class LLMClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self._client = AsyncOpenAI(
            api_key=api_key or settings.llm_api_key or "EMPTY",
            base_url=base_url or settings.llm_base_url,
            timeout=settings.llm_timeout,
        )

    def _candidate_models(self, model: str | None) -> list[str]:
        models = [model or settings.llm_model]
        if settings.llm_fallback_model and settings.llm_fallback_model not in models:
            models.append(settings.llm_fallback_model)
        return models

    async def complete(
        self,
        messages: Sequence[dict[str, Any]],
        model: str | None = None,
        temperature: float = 0.2,
    ) -> str:
        last_exc: Exception | None = None
        for candidate in self._candidate_models(model):
            for attempt in range(settings.llm_max_retries + 1):
                try:
                    resp = await self._client.chat.completions.create(
                        model=candidate,
                        messages=list(messages),
                        temperature=temperature,
                    )
                    return resp.choices[0].message.content or ""
                except Exception as exc:  # noqa: BLE001 上游异常统一兜底
                    last_exc = exc
                    logger.warning("llm call failed model=%s attempt=%d: %s", candidate, attempt, exc)
                    await asyncio.sleep(0.3 * (attempt + 1))
        raise llm_upstream(f"模型服务异常: {last_exc}")

    async def stream(
        self,
        messages: Sequence[dict[str, Any]],
        model: str | None = None,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        """流式生成；首个 token 前的失败会尝试降级模型，已产出内容后不再重试。"""
        last_exc: Exception | None = None
        for candidate in self._candidate_models(model):
            started = False
            try:
                stream = await self._client.chat.completions.create(
                    model=candidate,
                    messages=list(messages),
                    temperature=temperature,
                    stream=True,
                )
                async for chunk in stream:
                    delta = chunk.choices[0].delta.content if chunk.choices else None
                    if delta:
                        started = True
                        yield delta
                return
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if started:
                    raise llm_upstream(f"模型服务中断: {exc}") from exc
                logger.warning("llm stream failed model=%s: %s", candidate, exc)
                await asyncio.sleep(0.3)
        raise llm_upstream(f"模型服务异常: {last_exc}")


_client: LLMClient | None = None


def get_llm() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
