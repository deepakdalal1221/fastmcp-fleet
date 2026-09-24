from __future__ import annotations

import ast
import math
import operator as op
from typing import Annotated

from fastmcp import FastMCP
from mcp_common.errors import ValidationError
from pydantic import Field

_BIN_OPS = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.FloorDiv: op.floordiv,
    ast.Mod: op.mod,
    ast.Pow: op.pow,
}
_UNARY_OPS = {ast.UAdd: op.pos, ast.USub: op.neg}
_ALLOWED_FUNCS = {
    "sqrt": math.sqrt,
    "log": math.log,
    "log2": math.log2,
    "log10": math.log10,
    "exp": math.exp,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "abs": abs,
    "floor": math.floor,
    "ceil": math.ceil,
    "round": round,
    "min": min,
    "max": max,
}
_ALLOWED_NAMES = {"pi": math.pi, "e": math.e, "tau": math.tau, "inf": math.inf}


def _safe_eval(node: ast.AST) -> float:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValidationError("only numeric constants allowed")
    if isinstance(node, ast.Name):
        if node.id in _ALLOWED_NAMES:
            return _ALLOWED_NAMES[node.id]
        raise ValidationError(f"unknown name: {node.id}")
    if isinstance(node, ast.BinOp):
        return _BIN_OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp):
        return _UNARY_OPS[type(node.op)](_safe_eval(node.operand))
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_FUNCS:
            raise ValidationError("function not allowed")
        args = [_safe_eval(a) for a in node.args]
        return _ALLOWED_FUNCS[node.func.id](*args)
    raise ValidationError(f"unsupported expression node: {type(node).__name__}")


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool
    async def eval(
        expression: Annotated[str, Field(min_length=1, max_length=500)],
    ) -> dict:
        """Evaluate an arithmetic expression safely (no I/O, no imports)."""
        try:
            tree = ast.parse(expression, mode="eval")
        except SyntaxError as exc:
            raise ValidationError(f"parse error: {exc}") from exc
        value = _safe_eval(tree.body)
        return {"expression": expression, "value": value}

    @mcp.tool
    async def solve(
        a: Annotated[float, Field(description="coefficient a in ax+b=0")],
        b: Annotated[float, Field(description="constant b in ax+b=0")],
    ) -> dict:
        """Solve a linear equation ax + b = 0. Returns root or 'no unique solution'."""
        if a == 0:
            return {"a": a, "b": b, "solution": None, "note": "no unique solution (a=0)"}
        return {"a": a, "b": b, "solution": -b / a}
