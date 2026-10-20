"""Embedding 适配层：OpenAI 兼容协议（/embeddings）。

特性：
- 请求端降维（dimensions）
- 瞬时错误指数退避重试（5xx/429/连接超时/服务端过载）
- 服务端不支持 dimensions 时自动降级为原生维度
- 维度不符时按 EMBEDDING_STRICT_DIM 决定 warn / 抛错
- 上游错误统一解析脱敏，按错误类型映射正确 HTTP 状态码
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Sequence

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
)

from core.config import get_settings
from core.errors import llm_upstream
from core.logging import get_logger, mask_pii

logger = get_logger(__name__)
settings = get_settings()


# 视为"瞬时/可重试"的服务端状态码
_TRANSIENT_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}
# 服务端过载/限流的文本片段（用于文本分类与拉长退避）
_OVERLOAD_HINTS = (
    "service load",
    "too many requests",
    "rate limit",
    "overloaded",
    "temporarily unavailable",
    "please try again",
    "server is busy",
)


def _is_transient(exc: BaseException) -> tuple[bool, bool]:
    """返回 (是否可重试, 是否过载类——影响退避时长)。"""
    if isinstance(exc, (APIConnectionError, APITimeoutError)):
        return True, True
    if isinstance(exc, APIStatusError):
        code = getattr(exc, "status_code", None)
        msg = (str(exc) or "").lower()
        overload = any(h in msg for h in _OVERLOAD_HINTS)
        if code in _TRANSIENT_STATUS:
            return True, overload or code == 429
        return False, False
    msg = (str(exc) or "").lower()
    overload = any(h in msg for h in _OVERLOAD_HINTS)
    return overload, overload


def _parse_upstream(exc: BaseException) -> dict:
    """从 openai 异常中抽取干净的 {message, status, code, biz_status, transient}。

    - 不暴露 SDK 内部字面量（"Error code: NNN - {...}"）。
    - 对连接/超时给出明确 code。
    - 4xx 客户端错误映射 BizError 400；其余瞬时类映射 502/504。
    """
    info = {
        "message": str(exc),
        "status": None,
        "code": None,
        "biz_status": 502,
        "transient": False,
    }
    if isinstance(exc, APIStatusError):
        info["status"] = getattr(exc, "status_code", None)
        info["code"] = getattr(exc, "code", None)
        # body 通常是 {"error": {"message": "...", "type": "...", "code": "..."}}
        body = getattr(exc, "body", None)
        if isinstance(body, dict):
            err = body.get("error") if isinstance(body.get("error"), (dict, str)) else body
            if isinstance(err, dict):
                info["message"] = err.get("message") or err.get("error") or info["message"]
                if not info["code"]:
                    info["code"] = err.get("code") or err.get("type")
            elif isinstance(err, str):
                info["message"] = err
        st = info["status"]
        if st in (400, 401, 403, 404, 422):
            info["biz_status"] = 400
        elif st in _TRANSIENT_STATUS:
            info["biz_status"] = 502
            info["transient"] = True
        # 文本兜底
        if any(h in (info["message"] or "").lower() for h in _OVERLOAD_HINTS):
            info["transient"] = True
    elif isinstance(exc, APITimeoutError):
        info["code"] = "timeout"
        info["biz_status"] = 504
        info["transient"] = True
        info["message"] = "上游服务超时"
    elif isinstance(exc, APIConnectionError):
        info["code"] = "connection_error"
        info["biz_status"] = 502
        info["transient"] = True
        info["message"] = "无法连接上游服务"
    else:
        msg = (str(exc) or "").lower()
        if any(h in msg for h in _OVERLOAD_HINTS):
            info["transient"] = True
    return info


class Embedder:
    """OpenAI /embeddings 适配。"""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        dimensions: int | None = None,
        model: str | None = None,
    ):
        # 解析base_url
        resolved_base_url = base_url or settings.embedding_base_url or settings.llm_base_url

        # 实例化AsyncOpenAI：自己管理重试与日志，故关闭 SDK 内置重试避免叠加
        self._client = AsyncOpenAI(
            api_key=api_key or settings.embedding_api_key or settings.llm_api_key or "EMPTY",
            base_url=resolved_base_url,
            timeout=settings.llm_timeout,
            max_retries=0,
        )
        # 模型
        self.model = model or settings.embedding_model
        self.base_url: str = resolved_base_url

        # 维度：入参 > EMBEDDING_DIMENSIONS > EMBEDDING_DIM；<=0 视为不传
        requested = dimensions if dimensions is not None else settings.embedding_dimensions
        requested = settings.embedding_dim if requested is None else requested
        requested = int(requested or 0)
        self.dimensions: int | None = requested if requested > 0 else None
        # 期望维度（与 pgvector 列维度保持一致；降级为原生维度后跳过校验）
        self.expected_dim: int = self.dimensions or settings.embedding_dim
        # 服务端是否支持 dimensions（首次报错后置 False 并降级重试）
        self._dimensions_supported: bool = True
        self._strict_dim: bool = settings.embedding_strict_dim

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        t0 = time.perf_counter()
        try:
            vectors = await self._create_with_retry(list(texts))
        except Exception as exc:  # noqa: BLE001
            info = _parse_upstream(exc)
            hint = "上游服务繁忙/限流，请稍后重试" if info["transient"] else "上游请求被拒绝"
            # 关键：消息做 PII 脱敏 + 长度截断，避免把 SDK 内部字面量/dict 暴露给客户端
            safe_msg = mask_pii(info["message"] or str(exc))[:300]
            logger.error(
                "embedding 失败 model=%s upstream_status=%s upstream_code=%s: %s",
                self.model, info["status"], info["code"], safe_msg,
            )
            raise llm_upstream(
                f"Embedding {hint}（{safe_msg}）",
                status_code=info["biz_status"],
                detail={
                    "upstream_status": info["status"],
                    "upstream_code": info["code"],
                    "transient": info["transient"],
                    "model": self.model,
                },
            ) from exc

        # 降级为原生维度后不再做严格校验（expected_dim 已与原生维度不一致）
        if self._dimensions_supported:
            self._check_dim(vectors)

        logger.info(
            "embedding OK model=%s count=%d dim=%d dimensions=%s strict=%s cost=%.0fms",
            self.model,
            len(vectors),
            len(vectors[0]) if vectors else 0,
            self.dimensions,
            self._strict_dim,
            (time.perf_counter() - t0) * 1000,
        )
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self.embed_documents([text])
        return vectors[0] if vectors else []

    async def _create_with_retry(self, texts: list[str]) -> list[list[float]]:
        """带退避重试的 /embeddings 调用。

        - 第一次尝试携带 dimensions；若服务端提示不支持则后续均不再携带。
        - 瞬时错误（5xx/429/连接超时/过载提示）按 LLM_RETRY_BACKOFF 指数退避。
        - 最多 LLM_MAX_RETRIES+1 次（默认 4 次）。
        """
        attempts = max(0, settings.llm_max_retries) + 1
        backoff = max(0.1, float(settings.llm_retry_backoff or 0.0))
        last_exc: BaseException | None = None
        dim_disabled = not self._dimensions_supported
        attempt = 0

        while attempt < attempts:
            use_dimensions = self.dimensions is not None and not dim_disabled
            try:
                resp = await self._create_once(texts, use_dimensions=use_dimensions)
                if use_dimensions:
                    self._dimensions_supported = True
                # 成功后更新期望维度为"实际返回维度"，避免后续 _check_dim 误报
                try:
                    got = len(resp.data[0].embedding)
                    if got and (self.dimensions is None or got == self.dimensions or not use_dimensions):
                        self.expected_dim = got
                except Exception:  # noqa: BLE001
                    pass
                return [item.embedding for item in resp.data]
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                # 1) 维度不支持：仅当本次带了 dimensions 时降级
                if self._is_dimensions_unsupported(exc) and use_dimensions:
                    dim_disabled = True
                    self._dimensions_supported = False
                    self.expected_dim = 0  # 标记"不校验"
                    logger.warning(
                        "embedding 服务端不支持 dimensions=%s，降级为原生维度后继续重试: %s",
                        self.dimensions,
                        _parse_upstream(exc)["message"],
                    )
                    attempt += 1
                    continue
                # 2) 瞬时错误：退避重试
                transient, overload = _is_transient(exc)
                if transient and attempt < attempts - 1:
                    wait = backoff * (2 ** attempt)
                    if overload:
                        wait *= 3
                    wait = min(wait, 30.0) + random.uniform(0, 0.5)
                    info = _parse_upstream(exc)
                    logger.warning(
                        "embedding 瞬时失败 model=%s upstream_status=%s upstream_code=%s attempt=%d/%d，%.1fs 后重试: %s",
                        self.model, info["status"], info["code"], attempt + 1, attempts, wait, info["message"],
                    )
                    await asyncio.sleep(wait)
                    attempt += 1
                    continue
                # 3) 非瞬时：直接抛出
                raise

        if last_exc:
            raise last_exc
        raise RuntimeError("embedding 重试耗尽且无异常信息")

    async def _create_once(self, texts: list[str], *, use_dimensions: bool):
        payload: dict = {"model": self.model, "input": texts}
        if use_dimensions:
            payload["dimensions"] = self.dimensions
        logger.info(
            "embedding -> model=%s base_url=%s texts=%d chars=%d dimensions=%s",
            self.model,
            self.base_url,
            len(texts),
            sum(len(t) for t in texts),
            self.dimensions if use_dimensions else None,
        )
        return await self._client.embeddings.create(**payload)

    @staticmethod
    def _is_dimensions_unsupported(exc: BaseException) -> bool:
        msg = (str(exc) or "").lower()
        if "dimensions" not in msg:
            return False
        return any(k in msg for k in ("unsupported", "not support", "unknown", "invalid", "not allowed"))

    def _check_dim(self, vectors: list[list[float]]) -> None:
        if not vectors or self.expected_dim <= 0:
            return
        got = len(vectors[0])
        if got == self.expected_dim:
            return
        msg = (
            f"embedding 维度不符: got {got}, expected {self.expected_dim}"
            f"（请求 dimensions={self.dimensions}）"
        )
        if self._strict_dim:
            # 严格模式：抛 BizError 阻止脏数据写入
            raise llm_upstream(
                msg + "——请同步 .env EMBEDDING_DIM 与库表 vector 维度，或调整上游",
                status_code=400,
                detail={"got": got, "expected": self.expected_dim, "requested": self.dimensions},
            )
        logger.warning(msg + "（已设为非严格模式 EMBEDDING_STRICT_DIM=false，仅记录不抛错）")


_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        _embedder = Embedder()
    return _embedder
