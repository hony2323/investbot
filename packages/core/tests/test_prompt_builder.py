"""Prompt construction and tool schema fidelity."""

from __future__ import annotations

from investbot.analysis import prompt_builder as pb
from investbot.models.recommendation import Recommendation


def test_tool_schema_matches_model():
    schema = pb.recommendation_tool_schema()
    assert schema["name"] == pb.TOOL_NAME
    props = set(schema["input_schema"]["properties"].keys())
    assert props == set(Recommendation.model_fields.keys())


def test_system_prompt_has_persona_and_baselines(taste):
    sp = pb.system_prompt(taste, benchmark_etf="VOO")
    low = sp.lower()
    assert "conservative" in low
    assert "doing nothing" in low
    assert "VOO" in sp  # benchmark ETF injected
    assert "advisory only" in low
    # Taste rules injected.
    assert "Max single position" in sp
    assert "profitable software companies" in sp
    assert "meme stocks" in sp


def test_holding_prompt_includes_facts(sample_portfolio, taste):
    from investbot.analysis.risk import build_risk_report

    risk = build_risk_report(sample_portfolio, taste)
    pos = sample_portfolio.positions[0]
    prompt = pb.holding_user_prompt(pos, None, sample_portfolio, risk, "VOO")
    assert pos.ticker in prompt
    assert "weigh" in prompt.lower()
    assert "VOO" in prompt
