"""结构化日志 + PII 脱敏 + trace_id 传播（security.md#4 / observability.md）。"""

from __future__ import annotations

import contextvars
import logging
import re
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from core.config import get_settings

_PII_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"1[3-9]\d{9}"), "***PHONE***"),
    (re.compile(r"\d{17}[\dXx]"), "***IDNO***"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "***EMAIL***"),
]

_LOG_FORMAT = "%(asctime)s %(levelname)-7s [%(name)s] trace=%(trace_id)s %(message)s"

# 当前上下文的 trace_id；HTTP 请求由 middleware 设置，后台任务用 bind_trace 设置
_TRACE_ID: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="-")


class _TraceFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "trace_id", None):
            record.trace_id = _TRACE_ID.get()
        return True


def bind_trace(trace_id: str) -> contextvars.Token:
    """为当前上下文（含后台任务）绑定 trace_id，返回 reset 用的 token。"""
    return _TRACE_ID.set(trace_id)


def reset_trace(token: contextvars.Token) -> None:
    _TRACE_ID.reset(token)


@contextmanager
def trace_context(trace_id: str | None = None) -> Iterator[str]:
    """绑定 trace_id 的上下文管理器；不传则自动生成。

    用法（后台任务）：
        with trace_context(f"bg-{uuid.uuid4().hex}"):
            ...
    """
    tid = trace_id or uuid.uuid4().hex
    token = bind_trace(tid)
    try:
        yield tid
    finally:
        reset_trace(token)


def mask_pii(text: str) -> str:
    """对手机号 / 身份证 / 邮箱做脱敏，日志与输出侧共用。"""
    if not text:
        return text
    for pattern, replacement in _PII_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def truncate(text: str, limit: int = 200) -> str:
    """PII 脱敏 + 长度截断，供模型调用日志打印入参/返回使用（observability.md §3）。

    超长时保留首尾，中间用 `<...truncated N chars...>` 标记，既可读又不爆日志。
    """
    if not text:
        return ""
    safe = mask_pii(str(text))
    if len(safe) <= limit:
        return safe
    head = max(1, limit // 2)
    omitted = len(safe) - limit
    return f"{safe[:head]}<...truncated {omitted} chars...>{safe[-head:]}"


def summarize_messages(messages) -> tuple[int, int]:
    """返回 (条数, 总字符数)，供 LLM 调用入参日志使用（不打印逐条 content）。"""
    count = 0
    chars = 0
    for m in messages or []:
        count += 1
        content = m.get("content") if isinstance(m, dict) else getattr(m, "content", "")
        if isinstance(content, list):  # 多模态 content
            content = " ".join(
                str(part.get("text", "")) for part in content if isinstance(part, dict)
            )
        chars += len(content or "")
    return count, chars


def setup_logging(level: str | None = None) -> None:
    settings = get_settings()
    level = level or settings.log_level
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    handler.addFilter(_TraceFilter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
