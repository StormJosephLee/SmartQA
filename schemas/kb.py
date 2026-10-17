from datetime import datetime

from pydantic import BaseModel


class KBDocument(BaseModel):
    id: str
    kb_id: str
    title: str
    source_uri: str = ""
    status: str = "pending"
    chunk_count: int = 0
    error: str = ""
    created_at: datetime | None = None


class KBDocumentList(BaseModel):
    page: int
    size: int
    total: int
    items: list[KBDocument]
