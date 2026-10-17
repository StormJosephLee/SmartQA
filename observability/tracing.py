"""可观测性：Langfuse 可选接入，未配置时 no-op（deployment.md#5）。"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from core.config import get_settings
from core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

_client: Any | None = None
_client_checked = False


def _get_client() -> Any | None:
    global _client, _client_checked
    if _client_checked:
        return _client
    _client_checked = True
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        logger.info("langfuse not configured, tracing disabled")
        return None
    try:
        from langfuse import Langfuse

        _client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host or None,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("langfuse init failed, tracing disabled: %s", exc)
        _client = None
    return _client


class _NoopSpan:
    def end(self, **kwargs: Any) -> None:
        return None

    def update(self, **kwargs: Any) -> None:
        return None


@contextmanager
def trace_span(name: str, **meta: Any) -> Iterator[Any]:
    """统一埋点入口；未配置 Langfuse 时返回空实现，调用方无需分支。"""
    client = _get_client()
    span: Any = None
    if client is not None:
        try:
            span = client.span(name=name, **meta)
        except Exception as exc:  # noqa: BLE001
            logger.warning("langfuse span failed: %s", exc)
            span = None
    try:
        yield span or _NoopSpan()
    finally:
        if span is not None:
            try:
                span.end()
            except Exception:  # noqa: BLE001
                pass


def flush() -> None:
    if _client is not None:
        try:
            _client.flush()
        except Exception:  # noqa: BLE001
            pass
