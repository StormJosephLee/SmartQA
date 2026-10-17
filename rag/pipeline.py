"""入库流水线：解析 → 分块 → Embedding → 写库（对应 spec.md 6.2 文档入库流程）。"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from core.logging import get_logger
from db.models import Chunk, Document
from llm.embedding import get_embedder
from rag.bm25 import get_bm25_store
from rag.loaders.base import load_document
from rag.splitter import split_text

logger = get_logger(__name__)

EMBED_BATCH = 32


def build_chunks(doc: Document, file_path: Path, profile: str = "default") -> list[Chunk]:
    loaded = load_document(file_path)
    chunks: list[Chunk] = []
    index = 0
    for page, text in loaded.pages:
        for piece in split_text(text, profile=profile):
            if not piece.strip():
                continue
            chunks.append(
                Chunk(
                    doc_id=doc.id,
                    kb_id=doc.kb_id,
                    chunk_index=index,
                    content=piece,
                    meta={
                        "source_uri": doc.source_uri or str(file_path),
                        "title": doc.title,
                        "page": page,
                        "kb_id": doc.kb_id,
                        "doc_id": doc.id,
                        "chunk_index": index,
                    },
                )
            )
            index += 1
    return chunks


async def ingest_document(
    session: Session,
    doc: Document,
    file_path: Path,
    profile: str = "default",
) -> int:
    """返回写入的 chunk 数量；失败时把文档标记为 failed。"""
    try:
        doc.status = "processing"
        session.commit()

        chunks = build_chunks(doc, file_path, profile)
        if not chunks:
            doc.status = "failed"
            doc.error = "解析后无有效内容"
            doc.chunk_count = 0
            session.commit()
            return 0

        embedder = get_embedder()
        for start in range(0, len(chunks), EMBED_BATCH):
            batch = chunks[start : start + EMBED_BATCH]
            vectors = await embedder.embed_documents([c.content for c in batch])
            for chunk, vector in zip(batch, vectors, strict=False):
                chunk.embedding = vector

        # 覆盖式写入：先清旧 chunk，保证重复上传不产生脏数据
        session.query(Chunk).filter(Chunk.doc_id == doc.id).delete()
        session.add_all(chunks)
        doc.status = "ready"
        doc.chunk_count = len(chunks)
        doc.error = ""
        session.commit()

        get_bm25_store().invalidate()
        logger.info("document %s ingested, chunks=%d", doc.id, len(chunks))
        return len(chunks)
    except Exception as exc:  # noqa: BLE001 入库失败必须落库可见（US-102）
        session.rollback()
        doc = session.get(Document, doc.id)
        if doc:
            doc.status = "failed"
            doc.error = str(exc)[:500]
            session.commit()
        logger.exception("ingest failed for document %s", doc.id)
        raise
