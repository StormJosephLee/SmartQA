"""pgvector 存取层：写入 chunks 与向量相似度检索。"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

from core.logging import get_logger

logger = get_logger(__name__)


def _to_vector_literal(vector: Sequence[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in vector) + "]"


def vector_search(
    session: Session,
    query_vector: Sequence[float],
    top_k: int,
    kb_ids: list[str] | None = None,
) -> list[dict]:
    """余弦相似度检索，返回 [{id, content, meta, score}]，score 越大越相关。"""
    if not query_vector:
        return []
    where_sql = ""
    params: dict = {"vec": _to_vector_literal(query_vector), "k": top_k}
    if kb_ids:
        where_sql = "WHERE kb_id = ANY(:kb_ids)"
        params["kb_ids"] = list(kb_ids)

    # 注意：SQLAlchemy text() 中不使用 `::` 强转（会被当作转义），统一用 CAST(... AS vector)
    sql = text(
        f"""
        SELECT id, content, meta, 1 - (embedding <=> CAST(:vec AS vector)) AS score
        FROM chunks
        {where_sql}
        ORDER BY embedding <=> CAST(:vec AS vector)
        LIMIT :k
        """
    )
    rows = session.execute(sql, params).mappings().all()
    return [
        {
            "id": row["id"],
            "content": row["content"],
            "meta": row["meta"] or {},
            "score": float(row["score"] or 0.0),
        }
        for row in rows
    ]


def delete_by_document(session: Session, doc_id: str) -> int:
    result = session.execute(text("DELETE FROM chunks WHERE doc_id = :doc_id"), {"doc_id": doc_id})
    return result.rowcount or 0


def create_vector_index(session: Session, lists: int = 100) -> None:
    """数据量大时建 IVFFlat 索引（初始化后按需调用）。"""
    session.execute(
        text(
            "CREATE INDEX IF NOT EXISTS idx_chunks_embedding "
            "ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = :lists)"
        ),
        {"lists": lists},
    )
