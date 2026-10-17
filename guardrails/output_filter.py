"""输出侧安全：PII 脱敏 + 敏感内容复核（security.md#4）。"""

from __future__ import annotations

from dataclasses import dataclass

from core.logging import mask_pii

_LEAK_HINTS = ("system prompt", "我的指令是", "忽略以上指令")


@dataclass
class ScanResult:
    safe: bool
    reason: str = ""
    text: str = ""


def sanitize(text: str) -> str:
    return mask_pii(text or "")


def scan(text: str) -> ScanResult:
    """返回脱敏后的文本与是否命中风险。"""
    cleaned = sanitize(text)
    lowered = cleaned.lower()
    for hint in _LEAK_HINTS:
        if hint.lower() in lowered:
            return ScanResult(False, f"输出疑似泄漏系统提示: {hint}", cleaned)
    return ScanResult(True, "", cleaned)


def check(text: str) -> str:
    result = scan(text)
    if not result.safe:
        return "抱歉，该回答未通过安全复核。"
    return result.text
