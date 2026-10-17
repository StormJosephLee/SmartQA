"""FastAPI 依赖：鉴权与 DB Session。"""

from __future__ import annotations

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from core.errors import unauthorized
from core.logging import get_logger
from core.security import decode_access_token
from db.session import get_db
from services.auth_service import AuthUser

logger = get_logger(__name__)
bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthUser:
    """除 /auth/* 与 /health 外，所有接口强制校验 JWT（FR-08）。"""
    if credentials is None or not credentials.credentials:
        raise unauthorized()
    try:
        payload = decode_access_token(credentials.credentials)
    except ValueError as exc:
        raise unauthorized(str(exc)) from exc
    return AuthUser(
        id=payload.get("sub", ""),
        name=payload.get("sub", ""),
        role=payload.get("role", "user"),
        dept=payload.get("dept", ""),
    )


def get_session() -> Session:  # 仅用于类型提示收敛，实际由 FastAPI 注入
    raise NotImplementedError


__all__ = ["get_current_user", "get_db", "get_session", "Depends"]
