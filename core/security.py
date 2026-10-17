"""JWT 签发/校验与口令哈希（security.md#1）。MVP：单管理员 + 配置用户。"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt

from core.config import get_settings


def hash_password(raw: str) -> str:
    return hashlib.sha256(f"smartqa::{raw}".encode()).hexdigest()


def verify_password(raw: str, hashed: str) -> bool:
    return hash_password(raw) == hashed


def create_access_token(subject: str, role: str = "user", dept: str = "") -> tuple[str, int]:
    settings = get_settings()
    expires_in = settings.jwt_ttl_hours * 3600
    expire = datetime.now(UTC) + timedelta(seconds=expires_in)
    payload = {"sub": subject, "role": role, "dept": dept, "exp": expire}
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    return token, expires_in


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except JWTError as exc:  # noqa: B904
        raise ValueError("token 无效或已过期") from exc
