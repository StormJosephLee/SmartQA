"""联网搜索：tavily / serper，未配置时明确返回不可用（不臆造结果）。"""

from __future__ import annotations

from typing import Any

import httpx

from agents.tools.base import BaseTool, ToolContext, ToolResult
from core.config import get_settings

settings = get_settings()


class WebSearchTool(BaseTool):
    name = "web_search"
    description = "联网搜索：输入 query，返回最新网页摘要"

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        query = str(args.get("query") or args.get("q") or "").strip()
        if not query:
            return ToolResult(tool=self.name, args=args, ok=False, error="缺少 query")
        provider = settings.web_search_provider.lower()
        if provider == "none" or not settings.web_search_api_key:
            return ToolResult(
                tool=self.name,
                args={"query": query},
                ok=False,
                error="未配置 WEB_SEARCH_PROVIDER/API_KEY，联网搜索不可用",
            )

        if provider == "tavily":
            url = "https://api.tavily.com/search"
            payload = {"api_key": settings.web_search_api_key, "query": query, "max_results": 5}
        elif provider == "serper":
            url = "https://google.serper.dev/search"
            payload = {"q": query, "num": 5}  # header 携带 key
        else:
            return ToolResult(tool=self.name, args={"query": query}, ok=False, error=f"未知 provider: {provider}")

        headers = (
            {"X-API-KEY": settings.web_search_api_key}
            if provider == "serper"
            else {"Content-Type": "application/json"}
        )
        try:
            async with httpx.AsyncClient(timeout=settings.llm_timeout) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001
            return ToolResult(tool=self.name, args={"query": query}, ok=False, error=f"搜索失败: {exc}")

        items = []
        if provider == "tavily":
            items = [
                {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")}
                for r in data.get("results", [])
            ]
        else:
            items = [
                {"title": r.get("title", ""), "url": r.get("link", ""), "snippet": r.get("snippet", "")}
                for r in data.get("organic", [])
            ]
        text = "\n".join(f"[{i + 1}] {it['title']} ({it['url']})\n{it['snippet']}" for i, it in enumerate(items))
        return ToolResult(tool=self.name, args={"query": query}, output=text, payload={"results": items})
