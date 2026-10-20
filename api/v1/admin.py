from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.deps import get_current_user, get_db
from core.config import get_settings
from core.errors import forbidden
from db.models import ChatSession, Document, Message, User
from services.auth_service import AuthUser

router = APIRouter(prefix="/admin", tags=["admin"])
settings = get_settings()


@router.get("/stats", summary="运行概览")
async def stats(
    session: Session = Depends(get_db),
    current: AuthUser = Depends(get_current_user),
) -> dict:
    if current.role not in {"admin", "kb_admin"}:
        raise forbidden("仅管理员可查看统计")
    today = datetime.now(UTC) - timedelta(days=1)
    tokens_today = (
        session.execute(
            select(func.coalesce(func.sum(Message.tokens), 0)).where(Message.created_at >= today)
        ).scalar()
        or 0
    )
    return {
        "users": session.scalar(select(func.count(User.id))) or 0,
        "sessions": session.scalar(select(func.count(ChatSession.id))) or 0,
        "messages": session.scalar(select(func.count(Message.id))) or 0,
        "documents": session.scalar(select(func.count(Document.id))) or 0,
        "tokens_today": int(tokens_today),
    }


@router.get("/config", summary="运行期配置（不含密钥）")
async def runtime_config(current: AuthUser = Depends(get_current_user)) -> dict:
    if current.role not in {"admin", "kb_admin"}:
        raise forbidden("仅管理员可查看配置")
    return {
        "env": settings.app_env,
        "llm_model": settings.llm_model,
        "llm_fallback_model": settings.llm_fallback_model,
        "embedding_model": settings.embedding_model,
        "embedding_dim": settings.embedding_dim,
        "embedding_dimensions": settings.embedding_dimensions,
        "rerank_provider": settings.rerank_provider,
        "web_search_provider": settings.web_search_provider,
        "allowed_tools": settings.allowed_tools,
        "readonly_views": settings.readonly_views,
    }
