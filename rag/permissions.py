"""知识库可见性过滤（security.md#2 RBAC + rag_design.md#4 权限过滤）。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import KnowledgeBase


def visible_kb_ids(session: Session, role: str, dept: str = "") -> list[str] | None:
    """返回该用户可见的 kb_id 列表；None 表示不限制（admin / kb_admin）。"""
    if role in {"admin", "kb_admin"}:
        return None
    kbs = session.execute(select(KnowledgeBase)).scalars().all()
    if role == "guest":
        return [kb.id for kb in kbs if kb.visibility == "public"]
    # user：公开 + 本部门
    allow = {"public"}
    if dept:
        allow.add(f"dept:{dept}")
    return [kb.id for kb in kbs if kb.visibility in allow]


def assert_kb_access(session: Session, role: str, dept: str, kb_id: str) -> None:
    visible = visible_kb_ids(session, role, dept)
    if visible is not None and kb_id not in visible:
        from core.errors import forbidden

        raise forbidden("无权访问该知识库")
