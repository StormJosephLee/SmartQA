"""输入侧安全：长度限制 + 注入关键词规则（security.md#3）。"""

from __future__ import annotations

from dataclasses import dataclass

from core.config import cfg
from core.errors import INPUT_FORBIDDEN, BizError


@dataclass
class ScanResult:
    safe: bool
    reason: str = ""


def scan(text: str) -> ScanResult:
    max_chars = int(cfg("security.max_input_chars", 4000))
    if not text or not text.strip():
        return ScanResult(False, "输入为空")
    if len(text) > max_chars:
        return ScanResult(False, f"输入超长（>{max_chars} 字符）")

    lowered = text.lower()
    for pattern in cfg("security.forbidden_patterns", []) or []:
        if str(pattern).lower() in lowered:
            return ScanResult(False, f"命中注入关键词: {pattern}")
    return ScanResult(True)


def check(text: str) -> None:
    result = scan(text)
    if not result.safe:
        raise BizError(INPUT_FORBIDDEN, result.reason, status_code=400)
