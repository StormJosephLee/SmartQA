from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from api.deps import get_current_user, get_db
from core.errors import forbidden
from db.models import Document
from rag.permissions import assert_kb_access, visible_kb_ids
from schemas.kb import KBDocument, KBDocumentList
from services.auth_service import AuthUser
from services.kb_service import (
    create_document,
    delete_document,
    get_document,
    list_documents,
    run_ingestion,
    save_upload,
)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

DEFAULT_KB_ID = "kb_default"


@router.post("/upload", response_model=KBDocument, summary="上传文档并入知识库")
async def upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    kb_id: str = Form(DEFAULT_KB_ID),
    session: Session = Depends(get_db),
    current: AuthUser = Depends(get_current_user),
) -> KBDocument:
    if current.role not in {"admin", "kb_admin"}:
        raise forbidden("仅知识库管理员可上传文档")
    assert_kb_access(session, current.role, current.dept, kb_id)

    saved_path = save_upload(file)
    doc = create_document(
        session, kb_id=kb_id, title=file.filename or saved_path.name, source_uri=str(saved_path)
    )
    background_tasks.add_task(run_ingestion, doc.id, saved_path)
    return KBDocument(
        id=doc.id,
        kb_id=doc.kb_id,
        title=doc.title,
        source_uri=doc.source_uri,
        status=doc.status,
        chunk_count=doc.chunk_count,
        created_at=doc.created_at,
    )


@router.get("/list", response_model=KBDocumentList, summary="文档列表")
async def list_kb(
    page: int = 1,
    size: int = 20,
    session: Session = Depends(get_db),
    current: AuthUser = Depends(get_current_user),
) -> KBDocumentList:
    allowed = visible_kb_ids(session, current.role, current.dept)
    docs, total = list_documents(session, page=page, size=size)
    visible_docs = [d for d in docs if allowed is None or d.kb_id in allowed]
    items = [
        KBDocument(
            id=d.id,
            kb_id=d.kb_id,
            title=d.title,
            source_uri=d.source_uri,
            status=d.status,
            chunk_count=d.chunk_count,
            error=d.error,
            created_at=d.created_at,
        )
        for d in visible_docs
    ]
    return KBDocumentList(page=page, size=size, total=total, items=items)


@router.delete("/{doc_id}", summary="删除文档并清理向量")
async def delete_kb(
    doc_id: str,
    session: Session = Depends(get_db),
    current: AuthUser = Depends(get_current_user),
) -> dict:
    if current.role not in {"admin", "kb_admin"}:
        raise forbidden("仅知识库管理员可删除文档")
    doc: Document = get_document(session, doc_id)
    assert_kb_access(session, current.role, current.dept, doc.kb_id)
    return {"deleted": delete_document(session, doc_id)}
