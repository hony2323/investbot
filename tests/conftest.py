"""Shared test fixtures: a sample portfolio, taste profile, config, and a fake Claude.

Everything runs offline. The fake Claude client mimics the minimal anthropic surface
(`messages.create` returning blocks with `.type`, `.name`, `.input`, `.text`).
"""

from __future__ import annotations

import json

import pytest

from investbot.analysis import prompt_builder as pb
from investbot.models.portfolio import Portfolio
from investbot.models.recommendation import AppConfig, TasteProfile


@pytest.fixture
def sample_portfolio_dict() -> dict:
    return {
        "account_id": "DU0000001",
        "as_of": "2026-06-03T00:00:00",
        "base_currency": "USD",
        "cash": 4000.0,  # ~4% -> below 5% min cash, triggers a warn
        "positions": [
            {"ticker": "MSFT", "name": "Microsoft", "quantity": 100, "avg_cost": 200,
             "market_price": 400, "sector": "Technology"},
            {"ticker": "CRWD", "name": "CrowdStrike", "quantity": 80, "avg_cost": 200,
             "market_price": 350, "sector": "Technology"},
            {"ticker": "NEE", "name": "NextEra", "quantity": 100, "avg_cost": 70,
             "market_price": 78, "sector": "Utilities"},
        ],
    }


@pytest.fixture
def sample_portfolio(sample_portfolio_dict) -> Portfolio:
    return Portfolio.model_validate(sample_portfolio_dict)


@pytest.fixture
def taste() -> TasteProfile:
    return TasteProfile.model_validate(
        {
            "risk": {
                "max_single_position_pct": 15,
                "max_sector_pct": 45,
                "min_cash_pct": 5,
                "allow_options": False,
                "allow_margin": False,
            },
            "preferences": {
                "likes": ["profitable software companies", "strong moats"],
                "avoids": ["meme stocks", "hype without revenue"],
            },
        }
    )


@pytest.fixture
def config(tmp_path, sample_portfolio_dict) -> AppConfig:
    """An AppConfig pointed at tmp_path so tests never touch real data/ output."""
    snap = tmp_path / "snapshots"
    memos = tmp_path / "memos"
    fixtures = tmp_path / "fixtures"
    for d in (snap, memos, fixtures):
        d.mkdir(parents=True, exist_ok=True)
    (fixtures / "sample_portfolio.json").write_text(json.dumps(sample_portfolio_dict))
    return AppConfig.model_validate(
        {
            "claude": {"model": "claude-opus-4-8"},
            "data": {
                "default_source": "mock",
                "snapshots_dir": str(snap),
                "memos_dir": str(memos),
                "fixtures_dir": str(fixtures),
                "recommendations_file": str(tmp_path / "recommendations.jsonl"),
            },
            "analysis": {"benchmark_etf": "VOO"},
        }
    )


# --- Fake Claude ----------------------------------------------------------

class _Block:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Resp:
    def __init__(self, content):
        self.content = content


class FakeMessages:
    """Configurable: yields scripted tool inputs, then a memo text block."""

    def __init__(self, tool_inputs=None, memo_text="# Memo\nBottom line: hold.", missing_tool=False):
        self._tool_inputs = list(tool_inputs or [])
        self._memo_text = memo_text
        self._missing_tool = missing_tool
        self.calls = []

    def create(self, **kw):
        self.calls.append(kw)
        if "tools" in kw:
            if self._missing_tool:
                return _Resp([_Block(type="text", text="no tool")])
            data = self._tool_inputs.pop(0) if self._tool_inputs else _default_tool_input()
            return _Resp([_Block(type="tool_use", name=pb.TOOL_NAME, input=data)])
        return _Resp([_Block(type="text", text=self._memo_text)])


class FakeAnthropic:
    def __init__(self, **kw):
        self.messages = FakeMessages(**kw)


def _default_tool_input(ticker="MSFT", action="HOLD"):
    return {
        "action": action,
        "ticker": ticker,
        "confidence": 0.55,
        "time_horizon": "2-5 years",
        "reason": "Durable franchise within risk limits.",
        "risks": ["valuation", "concentration"],
        "what_would_change_my_mind": "Deteriorating margins.",
        "suggested_position_size": "0-10%",
    }


@pytest.fixture
def fake_anthropic_factory():
    """Return a builder so tests can script tool inputs / memo text."""
    def _make(**kw):
        return FakeAnthropic(**kw)
    return _make
