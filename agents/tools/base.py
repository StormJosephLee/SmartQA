"""工具基类与执行上下文（agent_design.md#2 工具表）。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session


@dataclass
class ToolContext:
    """工具执行所需的请求级上下文（不进入 state，避免序列化问题）。"""

    session: Session | None = None
    kb_ids: list[str] | None = None
    role: str = "user"
    dept: str = ""


@dataclass
class ToolResult:
    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    output: str = ""
    ok: bool = True
    error: str = ""
    payload: dict[str, Any] = field(default_factory=dict)


class BaseTool(ABC):
    name: str = ""
    description: str = ""

    @abstractmethod
    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        """执行工具；异常由调用方统一捕获。"""
