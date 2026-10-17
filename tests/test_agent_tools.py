import pytest

from agents.tools import REGISTRY, available_tools, get_tool
from agents.tools.base import ToolContext
from agents.tools.calculator import safe_eval
from agents.tools.db_query import _validate
from agents.tools.web_search import WebSearchTool


def test_calculator_basic():
    assert safe_eval("(12 + 8) * 3") == 60
    assert safe_eval("7 / 2") == 3.5


def test_calculator_rejects_dangerous_expr():
    with pytest.raises(ValueError):
        safe_eval("__import__('os').system('ls')")


def test_db_query_only_select():
    ok, reason, tables = _validate("SELECT * FROM v_employee_stats")
    assert ok and tables == ["v_employee_stats"]
    ok, reason, _ = _validate("DELETE FROM v_employee_stats")
    assert not ok


@pytest.mark.asyncio
async def test_web_search_disabled_without_provider():
    result = await WebSearchTool().run({"query": "今天天气"}, ToolContext())
    assert not result.ok
    assert "不可用" in result.error


def test_tool_registry_whitelist():
    assert set(REGISTRY) == {"kb_search", "web_search", "calculator", "db_query"}
    assert available_tools() != []
    assert get_tool("calculator") is not None
