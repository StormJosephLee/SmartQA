from pathlib import Path

from rag.loaders.base import LoadedDoc


def load_markdown(path: Path) -> LoadedDoc:
    text = path.read_text(encoding="utf-8", errors="ignore")
    return LoadedDoc(title=path.name, pages=[(0, text)])
