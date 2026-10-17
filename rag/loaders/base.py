"""文档解析统一入口：按扩展名分发 Loader，输出 (页码, 文本)。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class LoadedDoc:
    title: str
    pages: list[tuple[int, str]] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        return "\n\n".join(text for _, text in self.pages)


def load_document(path: Path) -> LoadedDoc:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from rag.loaders.pdf import load_pdf

        return load_pdf(path)
    if suffix in {".docx", ".doc"}:
        from rag.loaders.docx import load_docx

        return load_docx(path)
    if suffix in {".xlsx", ".xls"}:
        from rag.loaders.xlsx import load_xlsx

        return load_xlsx(path)
    if suffix in {".md", ".markdown", ".txt"}:
        from rag.loaders.markdown import load_markdown

        return load_markdown(path)
    raise ValueError(f"暂不支持的文档类型: {suffix}")
