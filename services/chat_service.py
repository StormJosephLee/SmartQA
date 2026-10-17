"""问答主链路：输入过滤 → 记忆 → Agent/RAG → 流式生成 → 输出过滤 → 持久化。

对应 architecture.md#4 请求生命周期与 dataflow.md 时序图。
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.graph import QAAgent
from agents.nodes.answer import build_direct_messages
from agents.tools.base import ToolContext
from core.logging import get_logger
from db.models import ChatSession, Citation, Message
from guardrails import input_filter, output_filter
from llm.chat import get_llm
from memory.short_term import get_memory
from observability.tracing import trace_span
from rag.permissions import visible_kb_ids
from rag.retriever import HybridRetriever
from schemas.chat import ChatRequest, ChatResponse, CitationItem
from services.auth_service import AuthUser

logger = get_logger(__name__)


def estimate_tokens(text: str) -> int:
    """无 tokenizer 依赖的粗估：约 3 字符 1 token。"""
    return max(1, len(text or "") // 3)


def sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@dataclass
class Prepared:
    session_id: str
    messages: list[dict[str, str]]
    citations: list[CitationItem] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)


class ChatService:
    def __init__(self, session: Session, user: AuthUser):
        self.session = session
        self.user = user
        self.memory = get_memory()

    # ---------- 上下文 ----------
    def _ensure_session(self, session_id: str | None, question: str) -> str:
        if session_id:
            exists = self.session.get(ChatSession, session_id)
            if exists is not None:
                return session_id
        new_session = ChatSession(
            id=uuid.uuid4().hex,
            user_id=self.user.id or self.user.name,
            title=(question[:30] or "新对话"),
        )
        self.session.add(new_session)
        self.session.commit()
        return new_session.id

    def _load_history(self, session_id: str) -> list[dict[str, str]]:
        history = self.memory.load(session_id)
        if history:
            return history
        rows = (
            self.session.execute(
                select(Message)
                .where(Message.session_id == session_id)
                .order_by(Message.created_at.desc())
                .limit(10)
            )
            .scalars()
            .all()
        )
        return [{"role": r.role, "content": r.content} for r in reversed(rows)]

    # ---------- 编排 ----------
    async def prepare(self, req: ChatRequest) -> Prepared:
        input_filter.check(req.message)
        session_id = self._ensure_session(req.session_id, req.message)
        history = self._load_history(session_id)
        kb_ids = req.kb_ids or visible_kb_ids(self.session, self.user.role, self.user.dept)

        with trace_span("chat.prepare", question=req.message[:100], use_agent=req.use_agent):
            if req.use_agent:
                ctx = ToolContext(
                    session=self.session, kb_ids=kb_ids, role=self.user.role, dept=self.user.dept
                )
                state = await QAAgent(ctx).run(req.message, history)
                prepared = Prepared(
                    session_id=session_id,
                    messages=state.get("answer_messages") or [],
                    citations=self._to_citations(state.get("evidence", [])),
                    trace=state.get("trace", []),
                )
            else:
                evidence: list[dict] = []
                trace: list[str] = []
                if req.use_rag:
                    chunks = await HybridRetriever(self.session).retrieve(req.message, kb_ids=kb_ids)
                    evidence = [
                        {
                            "content": c.content,
                            "source": c.source,
                            "page": c.page,
                            "score": float(c.score),
                        }
                        for c in chunks
                    ]
                    trace.append(f"rag -> {len(chunks)} hits")
                prepared = Prepared(
                    session_id=session_id,
                    messages=build_direct_messages(
                        {"question": req.message, "history": history, "evidence": evidence}
                    ),
                    citations=self._to_citations(evidence),
                    trace=trace,
                )

        if not prepared.messages:
            prepared.messages = [
                {"role": "system", "content": "你是 SmartQA，企业内部智能问答助手。"},
                {"role": "user", "content": req.message},
            ]
        return prepared

    @staticmethod
    def _to_citations(evidence: list[dict]) -> list[CitationItem]:
        return [
            CitationItem(
                source=str(e.get("source", "")),
                page=int(e.get("page", 0) or 0),
                score=float(e.get("score", 0.0) or 0.0),
                snippet=str(e.get("content", ""))[:200],
            )
            for e in evidence
        ]

    # ---------- 持久化 ----------
    def _persist(
        self,
        session_id: str,
        question: str,
        answer: str,
        citations: list[CitationItem],
        latency_ms: int,
    ) -> str:
        self.session.add(Message(session_id=session_id, role="user", content=question))
        assistant = Message(
            session_id=session_id,
            role="assistant",
            content=answer,
            citations=[c.model_dump() for c in citations],
            tokens=estimate_tokens(question) + estimate_tokens(answer),
            latency_ms=latency_ms,
        )
        self.session.add(assistant)
        self.session.flush()
        for item in citations:
            self.session.add(
                Citation(
                    message_id=assistant.id,
                    source=item.source,
                    page=item.page,
                    score=item.score,
                    snippet=item.snippet,
                )
            )
        self.session.commit()
        return assistant.id

    def _remember(self, session_id: str, question: str, answer: str) -> None:
        try:
            self.memory.append(session_id, "user", question)
            self.memory.append(session_id, "assistant", answer)
        except Exception as exc:  # noqa: BLE001 记忆失败不阻断问答
            logger.warning("memory save failed: %s", exc)

    # ---------- 非流式 ----------
    async def chat(self, req: ChatRequest) -> ChatResponse:
        start = time.perf_counter()
        prepared = await self.prepare(req)
        answer = await get_llm().complete(prepared.messages)
        answer = output_filter.check(answer)
        latency_ms = int((time.perf_counter() - start) * 1000)
        message_id = self._persist(
            prepared.session_id, req.message, answer, prepared.citations, latency_ms
        )
        self._remember(prepared.session_id, req.message, answer)
        return ChatResponse(
            message_id=message_id,
            session_id=prepared.session_id,
            answer=answer,
            citations=prepared.citations,
            tokens=estimate_tokens(req.message) + estimate_tokens(answer),
            latency_ms=latency_ms,
            trace=prepared.trace,
        )

    # ---------- 流式 ----------
    async def stream_events(self, req: ChatRequest) -> AsyncIterator[str]:
        start = time.perf_counter()
        prepared = await self.prepare(req)

        if prepared.citations:
            yield sse("citation", [c.model_dump() for c in prepared.citations])

        buffer: list[str] = []
        try:
            async for delta in get_llm().stream(prepared.messages):
                clean = output_filter.sanitize(delta)
                if not clean:
                    continue
                buffer.append(clean)
                yield sse("token", {"delta": clean})
        except Exception as exc:  # noqa: BLE001 流式中断也要给客户端明确事件
            logger.error("stream generation failed: %s", exc)
            yield sse("error", {"code": "LLM_UPSTREAM", "message": str(exc)[:200]})
            return

        answer = "".join(buffer)
        latency_ms = int((time.perf_counter() - start) * 1000)
        scan_result = output_filter.scan(answer)
        if not scan_result.safe:
            yield sse("filtered", {"reason": scan_result.reason})

        message_id = self._persist(
            prepared.session_id, req.message, answer, prepared.citations, latency_ms
        )
        self._remember(prepared.session_id, req.message, answer)
        yield sse(
            "done",
            {
                "message_id": message_id,
                "session_id": prepared.session_id,
                "tokens": estimate_tokens(req.message) + estimate_tokens(answer),
                "latency_ms": latency_ms,
                "trace": prepared.trace,
            },
        )
