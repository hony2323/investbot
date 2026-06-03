"""Safety guard: investbot must never contain trade-execution code paths.

This asserts the broker module (and the package broadly) does not call order-placement
APIs. Prose in docstrings is stripped before checking so documentation describing what we
do NOT do does not trip the test.
"""

from __future__ import annotations

import ast
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parents[1] / "investbot"

# Symbols that would indicate order execution via ib_insync.
FORBIDDEN_CALLS = {"placeOrder", "placeOrderAsync"}
FORBIDDEN_NAMES = {
    "Order",
    "MarketOrder",
    "LimitOrder",
    "StopOrder",
    "bracketOrder",
}


def _python_files() -> list[Path]:
    return list(PKG_ROOT.rglob("*.py"))


def _strip_docstrings_and_comments(source: str) -> ast.Module:
    return ast.parse(source)


def test_no_order_execution_symbols():
    offenders: list[str] = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            # Attribute calls like ib.placeOrder(...)
            if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_CALLS:
                offenders.append(f"{path.name}: .{node.attr}")
            # Direct name references like Order(...) or imports of Order
            if isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
                offenders.append(f"{path.name}: {node.id}")
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name in FORBIDDEN_NAMES or alias.name in FORBIDDEN_CALLS:
                        offenders.append(f"{path.name}: import {alias.name}")
    assert not offenders, f"Order-execution symbols found (investbot must not trade): {offenders}"


def test_ibkr_uses_only_read_methods():
    """The live path should reference read APIs, not execution ones."""
    src = (PKG_ROOT / "brokers" / "ibkr.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    called_attrs = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    # Sanity: we do read positions/accounts.
    assert "portfolio" in called_attrs or "positions" in called_attrs
    assert "accountSummary" in called_attrs
    # And we never place orders.
    assert called_attrs.isdisjoint(FORBIDDEN_CALLS)
