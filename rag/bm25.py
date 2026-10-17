"""BM25 稀疏检索：语料缓存 + 内存索引（rag_design.md#4）。"""

from __future__ import annotations

import re
from threading import Lock

from rank_bm25 import BM25Okapi
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.config import cfg
from core.logging import get_logger

logger = get_logger(__name__)

_TOKEN = re.compile(r"[\u4e00-\u9fff]|[A-Za-z0-9_]+")


def tokenize(text: str) -> list[str]:
    """中文按字、英文按词，够用于词面匹配。"""
    return _TOKEN.findall(text.lower())


class BM25Store:
    def __init__(self) -> None:
        self._index: BM25Okapi | None = None
        self._ids: list[str] = []
        self._lock = Lock()

    def build(self, corpus: list[tuple[str, str]]) -> None:
        """corpus: [(chunk_id, content)]"""
        if not corpus:
            self._index = None
            self._ids = []
            return
        self._ids = [cid for cid, _ in corpus]
        self._index = BM25Okapi([tokenize(content) for _, content in corpus])

    def refresh_from_db(self, session: Session, kb_ids: list[str] | None = None) -> int:
        limit = int(cfg("retrieval.max_bm25_corpus", 5000))
        where_sql = "WHERE kb_id = ANY(:kb_ids)" if kb_ids else ""
        params = {"limit": limit}
        if kb_ids:
            params["kb_ids"] = list(kb_ids)
        rows = session.execute(
            text(
                f"SELECT id, content FROM chunks {where_sql} "
                "ORDER BY chunk_index LIMIT :limit"
            ),
            params,
        ).all()
        with self._lock:
            self.build([(row[0], row[1]) for row in rows])
        return len(rows)

    def invalidate(self) -> None:
        with self._lock:
            self._index = None
            self._ids = []

    @property
    def ready(self) -> bool:
        return self._index is not None

    def search(self, query: str, top_k: int) -> list[tuple[str, float]]:
        with self._lock:
            if self._index is None:
                return []
            scores = self._index.get_scores(tokenize(query))
        pairs = list(zip(self._ids, scores, strict=False))
        pairs.sort(key=lambda x: x[1], reverse=True)
        return [(cid, float(score)) for cid, score in pairs[:top_k] if score > 0]


_store: BM25Store | None = None


def get_bm25_store() -> BM25Store:
    global _store
    if _store is None:
        _store = BM25Store()
    return _store
