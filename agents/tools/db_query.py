"""只读 SQL 查询：仅允许 SELECT，且只能查白名单视图（agent_design.md#6）。"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from agents.tools.base import BaseTool, ToolContext, ToolResult
from core.config import get_settings

settings = get_settings()
MAX_ROWS = 200


def _validate(sql: str) -> tuple[bool, str, list[str]]:
    try:
        import sqlglot
        from sqlglot import exp
    except ImportError:  # 未安装时退化为关键字校验
        lowered = sql.strip().lower()
        if not lowered.startswith("select") or any(
            k in lowered for k in ("insert", "update", "delete", "drop", "alter", "create")
        ):
            return False, "仅允许 SELECT 查询", []
        return True, "", []

    try:
        parsed = sqlglot.parse_one(sql)
    except Exception as exc:  # noqa: BLE001
        return False, f"SQL 解析失败: {exc}", []

    if not isinstance(parsed, exp.Select):
        return False, "仅允许 SELECT 查询", []
    tables: list[str] = []
    for table in parsed.find_all(exp.Table):
        if table.name:
            tables.append(table.name)
        if table.db or table.catalog:
            return False, "不允许跨库查询", []
    return True, "", tables


class DBQueryTool(BaseTool):
    name = "db_query"
    description = "只读 SQL 查询：输入 sql，仅允许 SELECT 白名单视图"

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        sql = str(args.get("sql") or "").strip()
        if not sql:
            return ToolResult(tool=self.name, args=args, ok=False, error="缺少 sql")
        if not settings.readonly_views:
            return ToolResult(
                tool=self.name, args={"sql": sql}, ok=False, error="未配置 DB_READONLY_VIEWS，工具已禁用"
            )
        ok, reason, tables = _validate(sql)
        if not ok:
            return ToolResult(tool=self.name, args={"sql": sql}, ok=False, error=reason)
        illegal = [t for t in tables if t not in settings.readonly_views]
        if illegal:
            return ToolResult(
                tool=self.name,
                args={"sql": sql},
                ok=False,
                error=f"不允许查询对象: {illegal}，白名单={settings.readonly_views}",
            )
        if ctx.session is None:
            return ToolResult(tool=self.name, args={"sql": sql}, ok=False, error="缺少数据库会话")
        try:
            rows = ctx.session.execute(text(sql)).mappings().all()
        except Exception as exc:  # noqa: BLE001
            return ToolResult(tool=self.name, args={"sql": sql}, ok=False, error=f"执行失败: {exc}")
        data = [dict(r) for r in rows][:MAX_ROWS]
        payload = {"columns": list(data[0].keys()) if data else [], "rows": data, "count": len(data)}
        return ToolResult(
            tool=self.name,
            args={"sql": sql},
            output=json.dumps(payload, ensure_ascii=False)[:4000],
            payload=payload,
        )
