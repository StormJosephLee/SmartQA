"""长期记忆管理接口（memory_design.md#6 用户可见、可控、可遗忘）。"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.deps import get_current_user, get_db
from core.errors import not_found
from db.models import LongTermMemory
from memory import long_term
from schemas.memory import (
    MemoryCreateRequest,
    MemoryItem,
    MemoryListResponse,
    MemoryMutationResponse,
)
from services.auth_service import AuthUser

router = APIRouter(prefix="/memory", tags=["memory"])


def _to_item(row: LongTermMemory) -> MemoryItem:
    return MemoryItem(
        id=row.id,
        kind=row.kind,
        content=row.content,
        pinned=bool(row.pinned),
        hit_count=int(row.hit_count or 0),
        source_id=row.source_id or "",
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("", response_model=MemoryListResponse, summary="列出我的长期记忆")
def list_memories(
    session: Session = Depends(get_db),
    current: AuthUser = Depends(get_current_user),
) -> MemoryListResponse:
    rows = long_term.list_memories(session, current.id)
    return MemoryListResponse(
        enabled=long_term.enabled(),
        total=len(rows),
        items=[_to_item(row) for row in rows],
    )


@router.post("", response_model=MemoryItem, summary="手动添加一条长期记忆")
def add_memory(
    req: MemoryCreateRequest,
    session: Session = Depends(get_db),
    current: AuthUser = Depends(get_current_user),
) -> MemoryItem:
    row = long_term.add_memory(session, current.id, req.content, req.kind, req.pinned)
    if row is None:
        kinds = ", ".join(long_term.allowed_kinds())
        raise HTTPException(status_code=400, detail=f"content 为空或 kind 非法，可选：{kinds}")
    return _to_item(row)


@router.delete("/{memory_id}", summary="删除单条长期记忆（被遗忘权）")
def delete_memory(
    memory_id: str,
    session: Session = Depends(get_db),
    current: AuthUser = Depends(get_current_user),
) -> dict:
    if not long_term.delete_memory(session, current.id, memory_id):
        raise not_found("记忆不存在或不属于当前用户")
    return {"deleted": True, "id": memory_id}


@router.delete("", response_model=MemoryMutationResponse, summary="清空我的全部长期记忆")
def clear_memories(
    session: Session = Depends(get_db),
    current: AuthUser = Depends(get_current_user),
) -> MemoryMutationResponse:
    return MemoryMutationResponse(cleared=long_term.clear_memories(session, current.id))
