from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from api.deps import get_current_user, get_db
from schemas.chat import ChatRequest, ChatResponse
from services.auth_service import AuthUser
from services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse, summary="单轮/多轮问答（非流式）")
async def chat(
    req: ChatRequest,
    session: Session = Depends(get_db),
    current: AuthUser = Depends(get_current_user),
) -> ChatResponse:
    return await ChatService(session, current).chat(req)


@router.post("/stream", summary="流式问答（SSE: citation/token/done）")
async def chat_stream(
    req: ChatRequest,
    session: Session = Depends(get_db),
    current: AuthUser = Depends(get_current_user),
) -> StreamingResponse:
    service = ChatService(session, current)
    return StreamingResponse(
        service.stream_events(req),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
