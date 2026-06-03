"""Claude wrapper: validation, repair retry, and graceful failure — all offline."""

from __future__ import annotations

import pytest

from investbot.analysis.claude import ClaudeClient, ClaudeError
from investbot.analysis.risk import build_risk_report
from tests.conftest import FakeAnthropic, _default_tool_input


def _client(taste, fake) -> ClaudeClient:
    from investbot.models.recommendation import ClaudeConfig

    return ClaudeClient(taste, ClaudeConfig(), "VOO", client=fake)


def test_valid_tool_input_parses(taste, sample_portfolio):
    fake = FakeAnthropic(tool_inputs=[_default_tool_input(ticker="msft")])
    client = _client(taste, fake)
    risk = build_risk_report(sample_portfolio, taste)
    rec = client.recommend_for_holding(sample_portfolio.positions[0], None, sample_portfolio, risk)
    assert rec.action == "HOLD"
    assert rec.ticker == "MSFT"  # normalized + cross-checked against the holding


def test_bad_then_good_triggers_repair(taste, sample_portfolio):
    bad = _default_tool_input()
    bad["confidence"] = 1.5  # invalid -> first attempt fails
    good = _default_tool_input()
    fake = FakeAnthropic(tool_inputs=[bad, good])
    client = _client(taste, fake)
    risk = build_risk_report(sample_portfolio, taste)
    rec = client.recommend_for_holding(sample_portfolio.positions[0], None, sample_portfolio, risk)
    assert rec.confidence == 0.55
    # Two tool calls were made (original + repair).
    tool_calls = [c for c in fake.messages.calls if "tools" in c]
    assert len(tool_calls) == 2


def test_persistent_invalid_raises(taste, sample_portfolio):
    bad = _default_tool_input()
    bad["action"] = "YOLO"
    fake = FakeAnthropic(tool_inputs=[dict(bad), dict(bad)])
    client = _client(taste, fake)
    risk = build_risk_report(sample_portfolio, taste)
    with pytest.raises(ClaudeError):
        client.recommend_for_holding(sample_portfolio.positions[0], None, sample_portfolio, risk)


def test_missing_tool_block_raises(taste, sample_portfolio):
    fake = FakeAnthropic(missing_tool=True)
    client = _client(taste, fake)
    risk = build_risk_report(sample_portfolio, taste)
    with pytest.raises(ClaudeError):
        client.recommend_for_holding(sample_portfolio.positions[0], None, sample_portfolio, risk)


def test_memo_synthesis_returns_text(taste, sample_portfolio):
    fake = FakeAnthropic(memo_text="# Memo\nBottom line: stay diversified.")
    client = _client(taste, fake)
    risk = build_risk_report(sample_portfolio, taste)
    rec = client.recommend_for_holding(sample_portfolio.positions[0], None, sample_portfolio, risk)
    memo = client.synthesize_memo([rec], sample_portfolio, risk)
    assert "Bottom line" in memo


def test_system_prompt_is_cached(taste, sample_portfolio):
    fake = FakeAnthropic()
    client = _client(taste, fake)
    risk = build_risk_report(sample_portfolio, taste)
    client.recommend_for_holding(sample_portfolio.positions[0], None, sample_portfolio, risk)
    call = fake.messages.calls[0]
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert call["tool_choice"] == {"type": "tool", "name": "emit_recommendation"}
