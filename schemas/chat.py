from pydantic import BaseModel, Field


class CitationItem(BaseModel):
    source: str
    page: int = 0
    score: float = 0.0
    snippet: str = ""


class ChatRequest(BaseModel):
    session_id: str | None = None
    user_id: str | None = None
    message: str
    stream: bool = False
    use_rag: bool = True
    use_agent: bool = False
    kb_ids: list[str] | None = None


class ChatResponse(BaseModel):
    message_id: str
    session_id: str
    answer: str
    citations: list[CitationItem] = Field(default_factory=list)
    tokens: int = 0
    latency_ms: int = 0
    trace: list[str] = Field(default_factory=list)
