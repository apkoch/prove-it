"""Code rules, checked as tests so they run everywhere the suite does."""

import ast
from pathlib import Path

import pytest

MONEY_CODE = Path(__file__).resolve().parents[1] / "splitter"


def is_float(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Name)
        and node.id == "float"
        or isinstance(node, ast.Constant)
        and isinstance(node.value, float)
        # int / int is a float
        or isinstance(node, ast.BinOp)
        and isinstance(node.op, ast.Div)
    )


def float_uses(source: str) -> list[int]:
    return sorted(node.lineno for node in ast.walk(ast.parse(source)) if is_float(node))


@pytest.mark.req("REQ-NFR-01")
def test_no_float_in_money_code():
    found = [
        f"{path.name}:{line}"
        for path in sorted(MONEY_CODE.rglob("*.py"))
        for line in float_uses(path.read_text())
    ]
    assert not found, f"float is banned in money code: {', '.join(found)}"
