"""数值计算：基于 AST 白名单求值，禁用 eval（安全要求）。"""

from __future__ import annotations

import ast
import operator
from typing import Any

from agents.tools.base import BaseTool, ToolContext, ToolResult

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_ALLOWED_NODES = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Add, ast.Sub, ast.Mult,
                  ast.Div, ast.FloorDiv, ast.Mod, ast.Pow, ast.USub, ast.UAdd)


def safe_eval(expr: str) -> float:
    tree = ast.parse(expr, mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ValueError(f"不允许的表达式节点: {type(node).__name__}")
        if isinstance(node, ast.Constant) and not isinstance(node.value, int | float):
            raise ValueError("仅允许数字常量")

    def _eval(node: ast.AST) -> float:
        if isinstance(node, ast.Constant):
            return float(node.value)
        if isinstance(node, ast.UnaryOp):
            value = _eval(node.operand)
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.BinOp):
            return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
        raise ValueError("无法解析的表达式")

    result = _eval(tree.body)
    if isinstance(result, float) and result.is_integer():
        return int(result)
    return result


class CalculatorTool(BaseTool):
    name = "calculator"
    description = "数值计算：输入算术表达式 expr，例如 (12+8)*3"

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        expr = str(args.get("expr") or args.get("expression") or "").strip()
        if not expr:
            return ToolResult(tool=self.name, args=args, ok=False, error="缺少 expr")
        try:
            value = safe_eval(expr)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(tool=self.name, args={"expr": expr}, ok=False, error=str(exc))
        return ToolResult(tool=self.name, args={"expr": expr}, output=f"{expr} = {value}")
