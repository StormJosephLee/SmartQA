"""工具注册表与白名单（agent_design.md#6 工具权限白名单）。"""

from __future__ import annotations

from agents.tools.base import BaseTool, ToolContext, ToolResult  # noqa: F401
from agents.tools.calculator import CalculatorTool
from agents.tools.db_query import DBQueryTool
from agents.tools.kb_search import KBSearchTool
from agents.tools.web_search import WebSearchTool
from core.config import get_settings
from core.logging import get_logger

logger = get_logger(__name__)

REGISTRY: dict[str, BaseTool] = {
    tool.name: tool
    for tool in (KBSearchTool(), WebSearchTool(), CalculatorTool(), DBQueryTool())
}


def available_tools() -> list[str]:
    """settings.AGENT_ALLOWED_TOOLS 与注册表的交集。"""
    settings = get_settings()
    return [name for name in settings.allowed_tools if name in REGISTRY]


def tool_catalog() -> str:
    return "\n".join(f"- {name}: {REGISTRY[name].description}" for name in available_tools())


def get_tool(name: str) -> BaseTool | None:
    if name not in available_tools():
        logger.warning("tool %s not allowed or not found", name)
        return None
    return REGISTRY.get(name)
