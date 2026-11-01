"""长期记忆：跨会话留存的用户画像 / 偏好 / 事实 / 指令（memory_design.md）。

与短期记忆互补：

  短期（short_term）= 当前会话最近 N 轮，Redis，TTL 24h
  长期（本模块）    = 跨会话沉淀，Postgres + pgvector，按语义召回后注入 system prompt

写入：由 LLM 从每轮对话抽取，异步执行不阻塞主链路
读取：recall() 按当前问题做向量召回，取 inject_top_k 条
去重：内容完全一致 → 更新；向量距离低于阈值 → 覆盖（视为同一事实的新表述）
淘汰：超过 max_items_per_user 时移除「未置顶 + 最久未命中」的条目
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from core.config import cfg
from core.logging import get_logger, truncate
from core.prompts import prompt
from db.models import LongTermMemory
from llm.chat import get_llm
from llm.embedding import get_embedder

logger = get_logger(__name__)

_JSON_ARRAY = re.compile(r"\[.*\]", re.S)
_MAX_CONTENT_CHARS = 500
_MAX_EXTRACT_CHARS = 800

# 模板缺失时的兜底，保证功能不因配置缺失而失效
_DEFAULT_EXTRACT_TEMPLATE = (
    "你是记忆抽取器。从下面这轮对话中提取值得长期记住的用户信息。\n"
    "只输出 JSON 数组，每项形如 {\"kind\": \"fact\", \"content\": \"...\"}；"
    "kind 只能是 profile / preference / fact / instruction 之一。\n"
    "没有值得记住的内容就输出 []。不要输出其它内容。\n\n"
    "用户：{question}\n助手：{answer}\n\n输出 JSON 数组："
)

_DEFAULT_HEADER = (
    "以下是关于该用户的长期记忆，回答时请自然参考，但不要向用户逐条复述这些内容："
)


def enabled() -> bool:
    """长期记忆总开关。"""
    return bool(cfg("memory.long_term_enabled", True))


def allowed_kinds() -> list[str]:
    """允许写入的类别白名单。"""
    raw = cfg("memory.allowed_kinds", ["fact"]) or []
    return [str(k).strip() for k in raw]


async def _embed(text: str) -> list[float]:
    """向量化；失败返回空列表，调用方退化为精确去重 / 按时间排序。"""
    try:
        return await get_embedder().embed_query(text)
    except Exception as exc:  # noqa: BLE001 向量化失败不应阻断对话
        logger.warning("memory embed failed: %s", exc)
        return []


def render_context(memories: list[LongTermMemory] | None) -> str:
    """把召回的记忆渲染成注入 system prompt 的上下文文本。"""
    if not memories:
        return ""
    lines = [f"- [{m.kind}] {m.content}" for m in memories]
    # YAML 块标量自带尾部换行，strip 掉以免渲染出多余空行
    header = (prompt("memory", "inject_header") or _DEFAULT_HEADER).strip()
    return f"{header}\n" + "\n".join(lines)


def _parse_memories(raw: str) -> list[dict[str, str]]:
    """宽容解析 LLM 返回的 JSON 数组（容忍 ```json 代码块与前后废话）。"""
    try:
        cleaned = raw.strip().strip("`")
        cleaned = re.sub(r"^json", "", cleaned, flags=re.I).strip()
        match = _JSON_ARRAY.search(cleaned)
        if not match:
            return []
        data = json.loads(match.group(0))
    except Exception:  # noqa: BLE001 解析失败视为无可沉淀内容
        logger.warning("memory extract parse failed, raw=%s", truncate(raw, 200))
        return []
    if not isinstance(data, list):
        return []

    items: list[dict[str, str]] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        content = str(row.get("content") or "").strip()
        kind = str(row.get("kind") or "fact").strip().lower()
        if content:
            items.append({"content": content, "kind": kind})
    return items


async def extract_memories(question: str, answer: str) -> list[dict[str, str]]:
    """用 LLM 从一轮对话中抽取值得长期留存的记忆。"""
    if not bool(cfg("memory.extract_enabled", True)):
        return []
    template = prompt("memory", "extract_template") or _DEFAULT_EXTRACT_TEMPLATE
    content = template.format(
        question=truncate(question, _MAX_EXTRACT_CHARS),
        answer=truncate(answer, _MAX_EXTRACT_CHARS),
    )
    try:
        raw = await get_llm().complete([{"role": "user", "content": content}], temperature=0.0)
    except Exception as exc:  # noqa: BLE001 抽取失败不影响本轮作答
        logger.warning("memory extract failed: %s", exc)
        return []
    items = _parse_memories(raw)
    logger.info("memory extracted count=%d", len(items))
    return items


def _find_similar(session: Session, user_id: str, vector: list[float]) -> LongTermMemory | None:
    """找出语义高度重复的既有记忆；没有则返回 None。"""
    threshold = float(cfg("memory.dedupe_distance", 0.12))
    distance = LongTermMemory.embedding.cosine_distance(vector)
    row = (
        session.query(LongTermMemory, distance.label("distance"))
        .filter(LongTermMemory.user_id == user_id, LongTermMemory.embedding.isnot(None))
        .order_by(distance)
        .first()
    )
    if row is None:
        return None
    target, value = row[0], float(row[1] or 1.0)
    return target if value <= threshold else None


def _evict(session: Session, user_id: str) -> None:
    """超出上限时淘汰「未置顶 + 最久未命中」的条目。"""
    limit = int(cfg("memory.max_items_per_user", 200))
    total = (
        session.query(func.count(LongTermMemory.id))
        .filter(LongTermMemory.user_id == user_id)
        .scalar()
        or 0
    )
    if total <= limit:
        return
    victims = (
        session.query(LongTermMemory)
        .filter(LongTermMemory.user_id == user_id, LongTermMemory.pinned.is_(False))
        .order_by(LongTermMemory.hit_count.asc(), LongTermMemory.updated_at.asc())
        .limit(total - limit)
        .all()
    )
    for row in victims:
        session.delete(row)
    if victims:
        logger.info("memory evicted user=%s count=%d", user_id, len(victims))


async def consolidate(
    session: Session,
    user_id: str,
    items: list[dict[str, str]],
    source_id: str = "",
) -> int:
    """沉淀抽取结果：精确去重 → 语义去重 → 写入 → 淘汰。返回新增条数。"""
    kinds = allowed_kinds()
    written = 0
    now = datetime.now(UTC)

    for item in items:
        kind = str(item.get("kind") or "fact").strip().lower()
        content = str(item.get("content") or "").strip()[:_MAX_CONTENT_CHARS]
        if not content or kind not in kinds:
            continue

        exists = (
            session.query(LongTermMemory)
            .filter(LongTermMemory.user_id == user_id, LongTermMemory.content == content)
            .first()
        )
        if exists is not None:
            exists.updated_at = now
            exists.source_id = source_id or exists.source_id
            continue

        vector = await _embed(content)
        if vector:
            duplicate = _find_similar(session, user_id, vector)
            if duplicate is not None:
                duplicate.content = content
                duplicate.kind = kind
                duplicate.updated_at = now
                duplicate.source_id = source_id
                duplicate.embedding = vector
                continue

        session.add(
            LongTermMemory(
                user_id=user_id,
                kind=kind,
                content=content,
                embedding=vector or None,
                source_id=source_id,
            )
        )
        written += 1

    _evict(session, user_id)
    session.commit()
    if written:
        logger.info("memory consolidated user=%s written=%d", user_id, written)
    return written


async def recall(
    session: Session,
    user_id: str,
    query: str,
    top_k: int | None = None,
) -> list[LongTermMemory]:
    """按当前问题召回相关记忆：向量优先，向量不可用时退化为按更新时间。"""
    limit = int(top_k or cfg("memory.inject_top_k", 5))
    candidate_k = max(int(cfg("memory.recall_top_k", 20)), limit)
    stmt = session.query(LongTermMemory).filter(LongTermMemory.user_id == user_id)

    vector = await _embed(query)
    if vector:
        stmt = stmt.filter(LongTermMemory.embedding.isnot(None)).order_by(
            LongTermMemory.embedding.cosine_distance(vector)
        )
    else:
        stmt = stmt.order_by(LongTermMemory.updated_at.desc())

    rows = stmt.limit(candidate_k).all()
    picked = list(rows)[:limit]
    if not picked:
        return []

    # 命中即刷新热度：影响后续淘汰顺序（未命中的会被优先淘汰）
    now = datetime.now(UTC)
    for row in picked:
        row.hit_count = int(row.hit_count or 0) + 1
        row.updated_at = now
    session.commit()
    logger.info(
        "memory recall user=%s picked=%d/%d kinds=%s",
        user_id,
        len(picked),
        len(rows),
        ",".join(sorted({r.kind for r in picked})),
    )
    return picked


# ---------- 用户可见的管理操作（对应 /api/v1/memory 接口）----------


def list_memories(session: Session, user_id: str) -> list[LongTermMemory]:
    return (
        session.query(LongTermMemory)
        .filter(LongTermMemory.user_id == user_id)
        .order_by(LongTermMemory.pinned.desc(), LongTermMemory.updated_at.desc())
        .all()
    )


def add_memory(
    session: Session,
    user_id: str,
    content: str,
    kind: str = "fact",
    pinned: bool = False,
) -> LongTermMemory | None:
    """手动添加一条记忆；类别不在白名单内则拒绝。"""
    content = (content or "").strip()[:_MAX_CONTENT_CHARS]
    kind = (kind or "fact").strip().lower()
    if not content or kind not in allowed_kinds():
        return None
    row = LongTermMemory(user_id=user_id, kind=kind, content=content, pinned=pinned)
    session.add(row)
    session.commit()
    logger.info("memory added user=%s kind=%s", user_id, kind)
    return row


def delete_memory(session: Session, user_id: str, memory_id: str) -> bool:
    """删除单条记忆（用户被遗忘权）。只在本人范围内查找。"""
    row = session.query(LongTermMemory).filter_by(id=memory_id, user_id=user_id).first()
    if row is None:
        return False
    session.delete(row)
    session.commit()
    logger.info("memory deleted user=%s id=%s", user_id, memory_id)
    return True


def clear_memories(session: Session, user_id: str) -> int:
    """清空某用户的全部长期记忆，返回清除条数。"""
    stmt = session.query(LongTermMemory).filter_by(user_id=user_id)
    count = stmt.count()
    stmt.delete()
    session.commit()
    logger.info("memory cleared user=%s count=%d", user_id, count)
    return count
