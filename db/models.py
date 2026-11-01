"""ORM 模型，对应 architecture.md#5 的 ER 图。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.config import get_settings
from db.base import Base

EMBEDDING_DIM = get_settings().embedding_dim


def _id() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(32), default="user")  # guest/user/kb_admin/admin
    dept: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    owner: Mapped[str] = mapped_column(String(64), default="")
    visibility: Mapped[str] = mapped_column(
        String(32), default="public"
    )  # public | dept:<name> | private
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    kb_id: Mapped[str] = mapped_column(String(64), ForeignKey("knowledge_bases.id"), index=True)
    title: Mapped[str] = mapped_column(String(256))
    source_uri: Mapped[str] = mapped_column(String(512), default="")
    status: Mapped[str] = mapped_column(
        String(32), default="pending"
    )  # pending | processing | ready | failed
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    doc_id: Mapped[str] = mapped_column(String(64), ForeignKey("documents.id"), index=True)
    kb_id: Mapped[str] = mapped_column(String(64), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text)
    embedding = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(256), default="新对话")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    session_id: Mapped[str] = mapped_column(String(64), ForeignKey("chat_sessions.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[list] = mapped_column(JSON, default=list)
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Citation(Base):
    __tablename__ = "citations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    message_id: Mapped[str] = mapped_column(String(64), ForeignKey("messages.id"), index=True)
    source: Mapped[str] = mapped_column(String(256))
    page: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    snippet: Mapped[str] = mapped_column(Text, default="")


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    message_id: Mapped[str] = mapped_column(String(64), ForeignKey("messages.id"), index=True)
    score: Mapped[int] = mapped_column(Integer, default=0)  # 1=👍 0=👎
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class LongTermMemory(Base):
    """长期记忆：跨会话留存的用户画像/偏好/事实/指令（memory_design.md#2）。"""

    __tablename__ = "long_term_memories"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    # profile=用户画像 / preference=偏好 / fact=事实 / instruction=长期指令
    kind: Mapped[str] = mapped_column(String(32), default="fact", index=True)
    content: Mapped[str] = mapped_column(Text)
    # 语义去重与检索用；向量化失败或未启用时为 NULL，此时退化为内容精确去重
    embedding = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    # 来源（会话/消息 id），便于追溯与审计
    source_id: Mapped[str] = mapped_column(String(64), default="")
    hit_count: Mapped[int] = mapped_column(Integer, default=0)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
