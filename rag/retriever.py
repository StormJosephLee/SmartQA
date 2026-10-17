"""混合检索：向量 + BM25 → RRF 融合 → Rerank → Top-N（rag_design.md#4）。"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from core.config import cfg
from core.logging import get_logger
from llm.embedding import get_embedder
from llm.rerank import get_reranker
from rag.bm25 import get_bm25_store
from rag.vectorstore import vector_search

logger = get_logger(__name__)


@dataclass
class RetrievedChunk:
    id: str
    content: str
    score: float = 0.0
    meta: dict = field(default_factory=dict)

    @property
    def source(self) -> str:
        return self.meta.get("source_uri") or self.meta.get("title") or ""

    @property
    def page(self) -> int:
        return int(self.meta.get("page") or 0)


def rrf_fuse(rankings: list[list[tuple[str, float]]], k: int = 60) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion。"""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, (doc_id, _) in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


class HybridRetriever:
    def __init__(self, session: Session):
        self.session = session

    async def retrieve(
        self,
        query: str,
        kb_ids: list[str] | None = None,
        top_n: int | None = None,
    ) -> list[RetrievedChunk]:
        vector_top_k = int(cfg("retrieval.vector_top_k", 20))
        bm25_top_k = int(cfg("retrieval.bm25_top_k", 20))
        rrf_k = int(cfg("retrieval.rrf_k", 60))
        top_n = top_n or int(cfg("retrieval.rerank_top_n", 5))

        # 1) 稠密召回
        embedder = get_embedder()
        try:
            query_vector = await embedder.embed_query(query)
        except Exception as exc:  # noqa: BLE001 Embedding 不可用则退化为纯 BM25
            logger.warning("embedding unavailable, fallback to bm25 only: %s", exc)
            query_vector = []
        dense = vector_search(self.session, query_vector, vector_top_k, kb_ids) if query_vector else []

        # 2) 稀疏召回
        store = get_bm25_store()
        if not store.ready:  # 首次使用或失效后重建
            store.refresh_from_db(self.session, kb_ids)
        sparse_ids = dict(store.search(query, bm25_top_k))

        id_to_content = {item["id"]: item for item in dense}
        if sparse_ids:
            missing = [cid for cid in sparse_ids if cid not in id_to_content]
            if missing:
                from sqlalchemy import text

                rows = (
                    self.session.execute(
                        text(
                            "SELECT id, content, meta FROM chunks WHERE id = ANY(:ids)"
                        ),
                        {"ids": missing},
                    )
                    .mappings()
                    .all()
                )
                for row in rows:
                    id_to_content[row["id"]] = {
                        "id": row["id"],
                        "content": row["content"],
                        "meta": row["meta"] or {},
                        "score": 0.0,
                    }

        # 3) RRF 融合
        dense_rank = [(item["id"], item["score"]) for item in dense]
        sparse_rank = list(sparse_ids.items())
        fused = rrf_fuse([dense_rank, sparse_rank], k=rrf_k)

        # 4) Rerank → Top-N
        candidates = [cid for cid, _ in fused][: max(top_n * 4, top_n)]
        contents = [id_to_content[cid]["content"] for cid in candidates if cid in id_to_content]
        reranked = await get_reranker().rerank(query, contents, top_n)

        results: list[RetrievedChunk] = []
        for pos, (idx, score) in enumerate(reranked):
            if idx >= len(candidates):
                continue
            chunk_id = candidates[idx]
            item = id_to_content.get(chunk_id)
            if not item:
                continue
            fused_score = dict(fused).get(chunk_id, 0.0)
            final_score = score if score else fused_score
            results.append(
                RetrievedChunk(
                    id=chunk_id,
                    content=item["content"],
                    score=float(final_score),
                    meta=item["meta"],
                )
            )
        logger.info("retrieved %d chunks for query=%s", len(results), query[:30])
        return results
