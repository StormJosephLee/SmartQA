"""分块策略，参数来自 config/settings.yaml#chunking（rag_design.md#3）。"""

from __future__ import annotations

import re

from core.config import cfg

_PARA_SPLIT = re.compile(r"\n\s*\n")
_CODE_SPLIT = re.compile(r"\n(?=\s*(?:def |class |async def |function ))")


def _window(text: str, size: int, overlap: int) -> list[str]:
    """按字符窗口切分，overlap 用于保留上下文。"""
    if len(text) <= size:
        return [text] if text.strip() else []
    step = max(size - overlap, 1)
    chunks: list[str] = []
    start = 0
    while start < len(text):
        chunks.append(text[start : start + size])
        start += step
    return [c for c in chunks if c.strip()]


def split_text(text: str, profile: str = "default") -> list[str]:
    conf = cfg(f"chunking.{profile}") or cfg("chunking.default") or {}
    strategy = conf.get("strategy", "recursive")
    size = int(conf.get("size", 512))
    overlap = int(conf.get("overlap", 64))

    if strategy == "table":
        return [text] if text.strip() else []
    if strategy == "semantic":
        # 段落为最小单位，合并到接近 size
        chunks: list[str] = []
        buffer = ""
        for para in _PARA_SPLIT.split(text):
            para = para.strip()
            if not para:
                continue
            if len(buffer) + len(para) + 1 <= size:
                buffer = f"{buffer}\n{para}".strip()
            else:
                if buffer:
                    chunks.append(buffer)
                buffer = para
        if buffer:
            chunks.append(buffer)
        return chunks
    if strategy == "code":
        blocks = [b.strip() for b in _CODE_SPLIT.split(text) if b.strip()]
        result: list[str] = []
        for block in blocks:
            result.extend(_window(block, size, overlap))
        return result

    # recursive：段落 → 超长再滑窗
    result = []
    for para in _PARA_SPLIT.split(text):
        para = para.strip()
        if not para:
            continue
        if len(para) <= size:
            result.append(para)
        else:
            result.extend(_window(para, size, overlap))
    return result
