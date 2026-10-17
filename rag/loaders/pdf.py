from pathlib import Path

from pypdf import PdfReader

from rag.loaders.base import LoadedDoc


def load_pdf(path: Path) -> LoadedDoc:
    reader = PdfReader(str(path))
    pages: list[tuple[int, str]] = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append((index, text.strip()))
    return LoadedDoc(title=path.name, pages=pages)
