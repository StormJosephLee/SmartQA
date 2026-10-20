"""知识库服务：上传、入库任务、列表、删除（US-101 ~ US-103）。"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.config import ROOT_DIR
from core.errors import not_found
from core.logging import get_logger, trace_context
from db.models import Chunk, Document
from db.session import SessionLocal
from rag.pipeline import ingest_document

logger = get_logger(__name__)

STORAGE_DIR = ROOT_DIR / "storage" / "uploads"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB，api.md#3
SUPPORTED_SUFFIX = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".md", ".markdown", ".txt"}


def save_upload(file: UploadFile) -> Path:
    suffix = Path(file.filename or "upload").suffix.lower()
    if suffix not in SUPPORTED_SUFFIX:
        raise ValueError(f"暂不支持的文档类型: {suffix}，支持 {sorted(SUPPORTED_SUFFIX)}")
    target = STORAGE_DIR / f"{uuid.uuid4().hex}{suffix}"
    with target.open("wb") as fp:
        shutil.copyfileobj(file.file, fp)
    size = target.stat().st_size
    if size > MAX_FILE_SIZE:
        target.unlink(missing_ok=True)
        raise ValueError("单文件不得超过 50MB")
    return target


def create_document(session: Session, kb_id: str, title: str, source_uri: str) -> Document:
    doc = Document(kb_id=kb_id, title=title, source_uri=source_uri, status="pending")
    session.add(doc)
    session.commit()
    session.refresh(doc)
    return doc


def list_documents(session: Session, page: int = 1, size: int = 20) -> tuple[list[Document], int]:
    total = session.scalar(select(func.count(Document.id))) or 0
    items = (
        session.execute(
            select(Document).order_by(Document.created_at.desc()).offset((page - 1) * size).limit(size)
        )
        .scalars()
        .all()
    )
    return list(items), int(total)


def get_document(session: Session, doc_id: str) -> Document:
    doc = session.get(Document, doc_id)
    if doc is None:
        raise not_found("文档不存在")
    return doc


def delete_document(session: Session, doc_id: str) -> str:
    doc = session.get(Document, doc_id)
    if doc is None:
        raise not_found("文档不存在")
    session.query(Chunk).filter(Chunk.doc_id == doc_id).delete()
    session.delete(doc)
    session.commit()
    from rag.bm25 import get_bm25_store

    get_bm25_store().invalidate()
    if doc.source_uri:
        Path(doc.source_uri).unlink(missing_ok=True)
    return doc_id


async def run_ingestion(doc_id: str, file_path: Path, profile: str = "default") -> None:
    """后台任务：独立 session 与独立 trace_id（observability.md §7）。"""
    with SessionLocal() as session, trace_context(f"bg-ingest-{doc_id}"):
        doc = session.get(Document, doc_id)
        if doc is None:
            logger.error("document %s not found for ingestion", doc_id)
            return
        try:
            await ingest_document(session, doc, file_path, profile)
        except Exception as exc:  # noqa: BLE001 状态已落库，避免后台任务抛出未捕获异常
            logger.error("ingestion failed for %s: %s", doc_id, exc)
