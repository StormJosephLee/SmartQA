"""结构化日志 + PII 脱敏（security.md#4）。"""

from __future__ import annotations

import logging
import re
import sys

from core.config import get_settings

_PII_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"1[3-9]\d{9}"), "***PHONE***"),
    (re.compile(r"\d{17}[\dXx]"), "***IDNO***"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "***EMAIL***"),
]

_LOG_FORMAT = "%(asctime)s %(levelname)-7s [%(name)s] trace=%(trace_id)s %(message)s"


class _TraceFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "trace_id"):
            record.trace_id = "-"
        return True


def mask_pii(text: str) -> str:
    """对手机号 / 身份证 / 邮箱做脱敏，日志与输出侧共用。"""
    if not text:
        return text
    for pattern, replacement in _PII_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


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
