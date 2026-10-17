"""建库：启用 pgvector 扩展并创建全部表。供 scripts/init_db.py 调用。"""

from __future__ import annotations

from sqlalchemy import text

from core.config import get_settings
from core.logging import get_logger
from core.security import hash_password
from db.base import Base
from db.models import Chunk, Citation, Document, Feedback, KnowledgeBase, Message, User  # noqa: F401
from db.session import SessionLocal, engine

logger = get_logger(__name__)


def ensure_default_data() -> None:
    settings = get_settings()
    with SessionLocal() as session:
        if not session.query(KnowledgeBase).first():
            session.add(
                KnowledgeBase(id="kb_default", name="默认知识库", owner="admin", visibility="public")
            )
        admin = session.query(User).filter_by(name=settings.default_admin_username).first()
        if not admin:
            session.add(
                User(
                    name=settings.default_admin_username,
                    password_hash=hash_password(settings.default_admin_password),
                    role="admin",
                    dept="",
                )
            )
        session.commit()


def init_db() -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(bind=engine)
    ensure_default_data()
    logger.info("database initialized")


if __name__ == "__main__":
    init_db()
