"""认证服务：DB 用户优先，回退到 .env 配置的默认管理员。"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from core.config import get_settings
from core.security import create_access_token, hash_password, verify_password
from db.models import User
from db.session import SessionLocal

settings = get_settings()


@dataclass
class AuthUser:
    id: str
    name: str
    role: str
    dept: str


def _to_auth_user(user: User) -> AuthUser:
    return AuthUser(id=user.id, name=user.name, role=user.role, dept=user.dept or "")


def authenticate(username: str, password: str) -> AuthUser | None:
    with SessionLocal() as session:
        user = session.execute(select(User).where(User.name == username)).scalar_one_or_none()
        if user is not None:
            if not verify_password(password, user.password_hash):
                return None
            return _to_auth_user(user)

    # 未落库的默认管理员（便于本地联调）
    if (
        username == settings.default_admin_username
        and password == settings.default_admin_password
    ):
        return AuthUser(id="u_admin", name=username, role="admin", dept="")
    return None


def issue_token(user: AuthUser) -> tuple[str, int]:
    return create_access_token(user.name, role=user.role, dept=user.dept)


def find_by_name(username: str) -> AuthUser | None:
    with SessionLocal() as session:
        user = session.execute(select(User).where(User.name == username)).scalar_one_or_none()
        return _to_auth_user(user) if user else None


def ensure_user_hash(raw_password: str) -> str:
    return hash_password(raw_password)
