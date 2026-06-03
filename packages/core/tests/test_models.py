"""Pydantic model validation: computed fields, bounds, enums."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from investbot.models.portfolio import Portfolio, Position
from investbot.models.recommendation import Recommendation


def test_position_computed_fields():
    pos = Position(ticker="AAPL", quantity=10, avg_cost=100, market_price=150)
    assert pos.market_value == 1500
    assert pos.cost_basis == 1000
    assert pos.unrealized_pnl == 500
    assert pos.unrealized_pnl_pct == 50.0


def test_portfolio_weights_and_totals(sample_portfolio):
    assert sample_portfolio.total_value == pytest.approx(
        sample_portfolio.cash + sample_portfolio.invested_value
    )
    weight_sum = sum(p.weight_pct for p in sample_portfolio.positions)
    # Weights + cash share should be ~100%.
    assert weight_sum + sample_portfolio.cash_pct == pytest.approx(100, abs=0.2)


def test_portfolio_zero_value_no_crash():
    pf = Portfolio(cash=0, positions=[])
    assert pf.total_value == 0
    assert pf.cash_pct == 0.0


def test_recommendation_valid():
    rec = Recommendation(
        action="BUY", ticker="AAPL", confidence=0.7, time_horizon="2-5 years",
        reason="x", risks=["y"], what_would_change_my_mind="z",
        suggested_position_size="0-5%",
    )
    assert rec.action == "BUY"


def test_recommendation_rejects_bad_action():
    with pytest.raises(ValidationError):
        Recommendation(
            action="YOLO", ticker="AAPL", confidence=0.5, time_horizon="1y",
            reason="x", what_would_change_my_mind="z", suggested_position_size="0-5%",
        )


@pytest.mark.parametrize("conf", [-0.1, 1.5])
def test_recommendation_rejects_out_of_range_confidence(conf):
    with pytest.raises(ValidationError):
        Recommendation(
            action="HOLD", ticker="AAPL", confidence=conf, time_horizon="1y",
            reason="x", what_would_change_my_mind="z", suggested_position_size="0-5%",
        )
