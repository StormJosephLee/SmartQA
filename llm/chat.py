"""LLM 适配层：OpenAI 兼容协议（chat.completions），支持流式与降级重试。

对应 dataflow.md#3 失败路径：LLM 超时 → 重试 2 次 → 切更小模型 → 报错。
日志规范见 observability.md §3.1。
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Sequence
from typing import Any

from openai import AsyncOpenAI

from core.config import get_settings
from core.errors import llm_upstream
from core.logging import get_logger, summarize_messages, truncate

logger = get_logger(__name__)
settings = get_settings()

# 日志中单条消息内容的最大保留长度（observability.md §3.1）
_MSG_LOG_LIMIT = 200
# 返回内容在日志中的最大长度
_CONTENT_LOG_LIMIT = 500


def _tool_names(messages: Sequence[dict[str, Any]]) -> str:
    """提取 messages 中声明的工具名列表（不打印 schema 全文）。"""
    names: list[str] = []
    for m in messages or []:
        tools = m.get("tools") if isinstance(m, dict) else None
        if isinstance(tools, list):
            for t in tools:
                if isinstance(t, dict):
                    fn = t.get("function") or t
                    name = fn.get("name") if isinstance(fn, dict) else None
                    if name:
                        names.append(str(name))
    return ",".join(names)


class LLMClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self._client = AsyncOpenAI(
            api_key=api_key or settings.llm_api_key or "EMPTY",
            base_url=base_url or settings.llm_base_url,
            timeout=settings.llm_timeout,
            max_retries=0,  # 自己管理重试，避免与 llm_max_retries 叠加
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
        msg_count, msg_chars = summarize_messages(messages)
        tools = _tool_names(messages)
        for candidate in self._candidate_models(model):
            for attempt in range(settings.llm_max_retries + 1):
                t0 = time.perf_counter()
                try:
                    logger.info(
                        "llm.complete -> model=%s base_url=%s attempt=%d messages=%d chars=%d "
                        "temperature=%.2f tools=%s%s",
                        candidate,
                        settings.llm_base_url,
                        attempt,
                        msg_count,
                        msg_chars,
                        temperature,
                        tools or "-",
                        " fallback_model=%s" % settings.llm_fallback_model
                        if candidate == settings.llm_fallback_model
                        else "",
                    )
                    logger.debug(
                        "llm.complete prompt preview model=%s: %s",
                        candidate,
                        truncate(
                            " | ".join(
                                str(m.get("content", "")) if isinstance(m, dict) else ""
                                for m in messages
                            ),
                            _MSG_LOG_LIMIT,
                        ),
                    )
                    resp = await self._client.chat.completions.create(
                        model=candidate,
                        messages=list(messages),
                        temperature=temperature,
                    )
                    content = resp.choices[0].message.content or ""
                    usage = getattr(resp, "usage", None)
                    logger.info(
                        "llm.complete OK model=%s attempt=%d chars=%d tokens=%s/%s/%s cost=%.0fms",
                        candidate,
                        attempt,
                        len(content),
                        getattr(usage, "prompt_tokens", None),
                        getattr(usage, "completion_tokens", None),
                        getattr(usage, "total_tokens", None),
                        (time.perf_counter() - t0) * 1000,
                    )
                    logger.debug(
                        "llm.complete content preview model=%s: %s",
                        candidate,
                        truncate(content, _CONTENT_LOG_LIMIT),
                    )
                    return content
                except Exception as exc:  # noqa: BLE001 上游异常统一兜底
                    last_exc = exc
                    logger.warning("llm call failed model=%s attempt=%d: %s", candidate, attempt, exc)
                    await asyncio.sleep(0.3 * (attempt + 1))
        logger.error(
            "llm.complete failed model=%s messages=%d chars=%d: %s",
            self._candidate_models(model)[0],
            msg_count,
            msg_chars,
            last_exc,
        )
        raise llm_upstream(f"模型服务异常: {last_exc}")

    async def stream(
        self,
        messages: Sequence[dict[str, Any]],
        model: str | None = None,
        temperature: float = 0.2,
    ) -> AsyncIterator[str]:
        """流式生成；首个 token 前的失败会尝试降级模型，已产出内容后不再重试。"""
        last_exc: Exception | None = None
        msg_count, msg_chars = summarize_messages(messages)
        for candidate in self._candidate_models(model):
            started = False
            t0 = time.perf_counter()
            ttft: float | None = None
            chunks = 0
            chars = 0
            try:
                logger.info(
                    "llm.stream -> model=%s base_url=%s messages=%d chars=%d temperature=%.2f",
                    candidate,
                    settings.llm_base_url,
                    msg_count,
                    msg_chars,
                    temperature,
                )
                stream = await self._client.chat.completions.create(
                    model=candidate,
                    messages=list(messages),
                    temperature=temperature,
                    stream=True,
                )
                async for chunk in stream:
                    delta = chunk.choices[0].delta.content if chunk.choices else None
                    if delta:
                        if ttft is None:
                            ttft = (time.perf_counter() - t0) * 1000
                            logger.debug("llm.stream first_chunk model=%s ttft=%.0fms", candidate, ttft)
                        started = True
                        chunks += 1
                        chars += len(delta)
                        yield delta
                logger.info(
                    "llm.stream OK model=%s chunks=%d chars=%d ttft=%sms total=%.0fms",
                    candidate,
                    chunks,
                    chars,
                    f"{ttft:.0f}" if ttft else "-",
                    (time.perf_counter() - t0) * 1000,
                )
                return
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if started:
                    logger.error(
                        "llm.stream interrupted model=%s chunks=%d chars=%d: %s",
                        candidate, chunks, chars, exc,
                    )
                    raise llm_upstream(f"模型服务中断: {exc}") from exc
                logger.warning("llm stream failed model=%s: %s", candidate, exc)
                await asyncio.sleep(0.3)
        logger.error(
            "llm.stream failed model=%s messages=%d chars=%d: %s",
            self._candidate_models(model)[0], msg_count, msg_chars, last_exc,
        )
        raise llm_upstream(f"模型服务异常: {last_exc}")


_client: LLMClient | None = None


def get_llm() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
