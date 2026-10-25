"""Tool 节点：白名单 + 超时（agent_design.md#5 工具超时 >10s 跳过）。"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any

from agents.state import AgentState
from agents.tools import get_tool
from agents.tools.base import ToolContext
from core.config import cfg
from core.logging import get_logger, truncate

logger = get_logger(__name__)


def make_tool_node(ctx: ToolContext) -> Callable[[AgentState], Any]:
    async def tool_node(state: AgentState) -> dict:
        timeout = float(cfg("agent.tool_timeout", 10))
        name = state.get("tool_name", "")
        args = dict(state.get("tool_args") or {})
        if not args and state.get("sub_query"):
            args = {"query": state["sub_query"], "expr": state["sub_query"], "sql": state["sub_query"]}

        tool = get_tool(name)
        results = list(state.get("tool_results", []))
        evidence = list(state.get("evidence", []))
        trace = list(state.get("trace", []))

        if tool is None:
            logger.warning("tool.call rejected name=%s reason=not_in_whitelist", name)
            trace.append(f"tool:{name} -> 被白名单拒绝")
            return {"tool_results": results, "trace": trace}

        call_t0 = time.perf_counter()
        logger.info(
            "tool.call -> name=%s timeout=%.1fs args=%s",
            name,
            timeout,
            truncate(str(args)),
        )
        try:
            result = await asyncio.wait_for(tool.run(args, ctx), timeout=timeout)
        except TimeoutError:
            logger.warning("tool.call timeout name=%s after=%.1fs", name, timeout)
            result = None
            trace.append(f"tool:{name} -> 超时 {timeout}s，已跳过")
            results.append({"tool": name, "args": args, "output": "", "ok": False, "error": "timeout"})
        except Exception as exc:  # noqa: BLE001 工具异常不阻断主流程
            logger.warning(
                "tool.call failed name=%s cost=%.0fms: %s",
                name,
                (time.perf_counter() - call_t0) * 1000,
                exc,
            )
            trace.append(f"tool:{name} -> 异常，已跳过")
            results.append({"tool": name, "args": args, "output": "", "ok": False, "error": str(exc)[:200]})
        else:
            call_ms = (time.perf_counter() - call_t0) * 1000
            logger.info(
                "tool.call OK name=%s ok=%s chars=%d cost=%.0fms output=%s",
                name,
                result.ok,
                len(result.output or ""),
                call_ms,
                truncate(result.output or result.error or ""),
            )
            trace.append(f"tool:{name} -> ok={result.ok}")
            results.append(
                {
                    "tool": name,
                    "args": result.args,
                    "output": result.output,
                    "ok": result.ok,
                    "error": result.error,
                }
            )
            if name == "kb_search" and result.ok:
                payload = result.payload or {}
                seen = {e.get("id") for e in evidence}
                for item in payload.get("results", []):
                    if item.get("id") in seen:
                        continue
                    evidence.append(item)
                    seen.add(item.get("id"))

        return {"tool_results": results, "evidence": evidence[:8], "trace": trace}

    return tool_node
