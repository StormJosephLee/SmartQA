"""长期记忆 DTO（设计见 docs/memory_design.md#6）。"""

from datetime import datetime

from pydantic import BaseModel, Field


class MemoryItem(BaseModel):
    """一条长期记忆的对外形态。"""

    id: str
    kind: str
    content: str
    pinned: bool = False
    hit_count: int = 0
    source_id: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


class MemoryCreateRequest(BaseModel):
    """手动添加记忆；kind 需在 settings 的 allowed_kinds 白名单内。"""

    content: str = Field(min_length=1, max_length=500)
    kind: str = "fact"
    pinned: bool = False


class MemoryListResponse(BaseModel):
    enabled: bool = True
    total: int = 0
    items: list[MemoryItem] = Field(default_factory=list)


class MemoryMutationResponse(BaseModel):
    deleted: bool = False
    cleared: int = 0
